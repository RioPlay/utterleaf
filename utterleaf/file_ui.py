"""An explicit local-file workflow, separate from ordinary dictation."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import queue
import sys
import threading
import unicodedata

from utterleaf import theme
from utterleaf.config import Config
from utterleaf.file_tracks import (
    export_destinations, export_transcripts, preview_file_transcripts, transcribe_tracks,
)
from utterleaf.file_inspection import current_file_signature, inspect_file
from utterleaf.transcript import TranscriptionCancelled


def _send(events, kind, value):
    try:
        events.put_nowait((kind, value))
    except queue.Full:
        try:
            events.get_nowait()
        except queue.Empty:
            pass
        events.put_nowait((kind, value))


def _inspect_work(path, cancel, events):
    try:
        value = inspect_file(path, cancel=cancel)
        _send(events, "cancelled", None) if cancel.is_set() else _send(events, "inspection", value)
    except TranscriptionCancelled:
        _send(events, "cancelled", None)
    except Exception as exc:
        _send(events, "cancelled", None) if cancel.is_set() else _send(events, "error", str(exc))


def _track_choice_label(track):
    title = " ".join((track.title or "Audio track").split())
    title = "".join(" " if unicodedata.category(char).startswith("C") else char for char in title)
    title = " ".join(title.split()).strip() or "Audio track"
    if len(title) > 24:
        title = title[:23].rstrip() + "…"
    label = f"{track.ordinal + 1}: {title}"
    details = []
    if track.sample_rate:
        details.append(f"{track.sample_rate / 1000:g} kHz")
    if track.channels:
        details.append(f"{track.channels} ch")
    if details:
        label += " (" + ", ".join(details) + ")"
    return label


def _work(path, cfg, audio_tracks, cancel, events, expected_signature=None, timing="relative"):
    # Only this bounded queue crosses threads. Workers never touch Tk widgets.
    try:
        if cancel.is_set():
            raise TranscriptionCancelled("File recognition cancelled")
        if expected_signature is not None and current_file_signature(path) != expected_signature:
            raise ValueError("The selected file changed. Inspect its tracks again.")
        result = transcribe_tracks(
            path, cfg, audio_tracks=audio_tracks, cancel=cancel, timing=timing,
            expected_signature=expected_signature,
            progress=lambda current, total, phase, amount: _send(
                events, "progress", (phase, amount, current, total),
            ),
        )
        if cancel.is_set():
            raise TranscriptionCancelled("File recognition cancelled")
        if expected_signature is not None and current_file_signature(path) != expected_signature:
            raise ValueError("The selected file changed. Inspect its tracks again.")
        _send(events, "cancelled", None) if cancel.is_set() else _send(events, "result", result)
    except TranscriptionCancelled:
        _send(events, "cancelled", None)
    except Exception as exc:
        _send(events, "cancelled", None) if cancel.is_set() else _send(events, "error", str(exc))


class FileWindow:
    def __init__(self, root, cfg: Config):
        global tk, filedialog, messagebox, ttk
        import tkinter as tk
        from tkinter import filedialog, messagebox, ttk

        self.root = root
        self.cfg = replace(cfg)
        self.closed = False
        self.busy = False
        self.operation = None
        self.result = None
        self.path = None
        self.inspected = None
        self.inspection_signature = None
        self._track_ordinals = {}
        self.cancel_event = threading.Event()
        self.events = queue.Queue(maxsize=8)
        self.poll_id = None
        self.activation_requests = threading.Event()
        theme.apply(root)
        root.title("Transcribe a file — Utterleaf")
        root.geometry("800x640")
        root.minsize(760, 560)
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.bind("<Escape>", lambda _event: self.cancel() if self.busy else self.close())
        page = ttk.Frame(root, padding=24)
        page.pack(fill="both", expand=True)
        page.columnconfigure(0, weight=1)
        page.rowconfigure(5, weight=1)
        heading = ttk.Frame(page)
        heading.grid(row=0, column=0, rowspan=3, sticky="ew")
        heading.columnconfigure(0, weight=1)
        ttk.Label(heading, text="Transcribe a file", style="Section.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(heading, text="Choose local audio, review the words, then export when ready.", wraplength=560).grid(row=1, column=0, sticky="w", pady=(8, 4))
        self.file_guidance = ttk.Label(
            heading,
            text="No duration limit · Processing stays on this computer · Installed models only\n"
                 "MP3, M4A and video: choose More formats to set up local decoding.",
            style="Hint.TLabel", wraplength=560,
        )
        self.file_guidance.grid(row=2, column=0, sticky="w")
        from PIL import ImageTk
        from utterleaf.brand import mascot_image
        self.mascot = ImageTk.PhotoImage(mascot_image("typing", size=80), master=root)
        ttk.Label(heading, image=self.mascot).grid(row=0, column=1, rowspan=3, padx=(12, 0))
        select = ttk.Frame(page)
        select.grid(row=3, column=0, sticky="ew", pady=16)
        select.columnconfigure(1, weight=1)
        self.choose_button = ttk.Button(select, text="Choose file…", command=self.choose)
        self.choose_button.grid(row=0, column=0, sticky="w")
        self.filename = tk.StringVar(value="No file selected")
        ttk.Label(select, textvariable=self.filename, wraplength=440).grid(row=0, column=1, sticky="w", padx=12)
        self.start_button = ttk.Button(select, text="Transcribe", style="Primary.TButton", command=self.start, state="disabled")
        self.start_button.grid(row=0, column=2)
        self.audio_track_label = ttk.Label(select, text="Audio tracks", underline=0)
        self.audio_track_label.grid(row=1, column=0, sticky="nw", pady=(10, 0))
        self._updating_tracks = False
        track_box = ttk.Frame(select)
        track_box.grid(row=1, column=1, sticky="ew", padx=12, pady=(10, 0))
        track_box.columnconfigure(0, weight=1)
        self.audio_track_input = tk.Listbox(
            track_box, height=1, selectmode=tk.EXTENDED, exportselection=False,
            activestyle="dotbox", relief="flat", highlightthickness=1,
            bg=theme.SURFACE_LOW, fg=theme.ON_SURFACE,
            selectbackground=theme.PRIMARY_CONTAINER, selectforeground=theme.ON_SURFACE,
            highlightbackground=theme.OUTLINE_VARIANT, highlightcolor=theme.PRIMARY,
        )
        track_scroll = ttk.Scrollbar(track_box, command=self.audio_track_input.yview)
        self.audio_track_input.configure(yscrollcommand=track_scroll.set)
        self.audio_track_input.grid(row=0, column=0, sticky="ew")
        track_scroll.grid(row=0, column=1, sticky="ns")
        self.audio_track_input.bind("<<ListboxSelect>>", lambda _event: self._job_options_changed())
        self.inspect_button = ttk.Button(select, text="Inspect tracks", command=self.inspect_tracks,
                                         state="disabled")
        self.inspect_button.grid(row=1, column=2, sticky="nw", padx=(8, 0), pady=(10, 0))
        root.bind("<Alt-a>", lambda _event: self.audio_track_input.focus_set(), add="+")
        self.audio_track_hint = ttk.Label(
            select,
            text="Select one or more audio streams, not stereo channels or speakers. "
                 f"{'Command-click' if sys.platform == 'darwin' else 'Ctrl-click'} "
                 "or Shift-click adds tracks.",
            style="Hint.TLabel", wraplength=440,
        )
        self.audio_track_hint.grid(row=2, column=1, columnspan=2, sticky="w",
                                   padx=12, pady=(4, 0))
        timing_line = ttk.Frame(select)
        timing_line.grid(row=3, column=0, columnspan=3, sticky="ew", pady=(10, 0))
        timing_line.columnconfigure(1, weight=1)
        self.recording_timestamps = tk.BooleanVar(value=False)
        self.timing_input = ttk.Checkbutton(timing_line, text="Keep recording timestamps",
                                            variable=self.recording_timestamps,
                                            command=self._job_options_changed, state="disabled")
        self.timing_input.grid(row=0, column=0, sticky="w")
        self.timing_hint = ttk.Label(timing_line, text="Choose a file to inspect its timing.",
                                     style="Hint.TLabel", wraplength=400)
        self.timing_hint.grid(row=0, column=1, sticky="w", padx=(12, 0))
        preview_heading = ttk.Frame(page)
        preview_heading.grid(row=4, column=0, sticky="ew", pady=(0, 8))
        preview_heading.columnconfigure(0, weight=1)
        ttk.Label(preview_heading, text="Transcript preview", style="Section.TLabel").grid(row=0, column=0, sticky="w")
        from utterleaf.settings import launch_settings
        self.model_button = ttk.Button(preview_heading, text="Model settings…", command=launch_settings)
        self.model_button.grid(row=0, column=1, padx=(0, 8))
        self.decoder_button = ttk.Button(preview_heading, text="More formats…", command=self.decoder_setup)
        self.decoder_button.grid(row=0, column=2)
        self.decoder_dialog = None
        preview_frame = ttk.Frame(page)
        preview_frame.grid(row=5, column=0, sticky="nsew")
        self.preview = tk.Text(preview_frame, wrap="word", height=10, state="disabled",
                               bg=theme.SURFACE_LOW, fg=theme.ON_SURFACE,
                               selectbackground=theme.PRIMARY_CONTAINER, selectforeground=theme.ON_SURFACE,
                               highlightbackground=theme.OUTLINE_VARIANT, highlightcolor=theme.PRIMARY,
                               insertbackground=theme.ON_SURFACE, padx=12, pady=12, relief="flat")
        scrollbar = ttk.Scrollbar(preview_frame, command=self.preview.yview)
        scrollbar.pack(side="right", fill="y")
        self.preview.configure(yscrollcommand=scrollbar.set)
        self.preview.pack(fill="both", expand=True)
        self.progress = ttk.Progressbar(page, maximum=1.0)
        self.progress.grid(row=6, column=0, sticky="ew", pady=(14, 8))
        self.status = tk.StringVar(value="Nothing is saved until you export. Closing discards this preview.")
        ttk.Label(page, textvariable=self.status, wraplength=700).grid(row=7, column=0, sticky="ew")
        actions = ttk.Frame(page)
        actions.grid(row=8, column=0, sticky="ew", pady=(16, 0))
        actions.columnconfigure(2, weight=1)
        self.cancel_button = ttk.Button(actions, text="Cancel", command=self.cancel, state="disabled")
        self.cancel_button.grid(row=0, column=0)
        self.discard_button = ttk.Button(actions, text="Discard", command=self.discard, state="disabled")
        self.discard_button.grid(row=0, column=1, padx=8)
        self.format = tk.StringVar(value="TXT")
        ttk.Label(actions, text="Format").grid(row=0, column=3, padx=8)
        ttk.Combobox(actions, textvariable=self.format, values=("TXT", "SRT", "VTT"), state="readonly", width=5).grid(row=0, column=4)
        self.export_button = ttk.Button(actions, text="Export…", command=self.export, state="disabled")
        self.export_button.grid(row=0, column=5, padx=8)
        ttk.Button(actions, text="Close", command=self.close).grid(row=0, column=6)
        self.poll_id = root.after(100, self.poll)
        self.choose_button.focus_set()

    def _show_tracks(self, tracks, *, selected=()):
        self._updating_tracks = True
        try:
            self.audio_track_input.configure(state=tk.NORMAL)
            self.audio_track_input.delete(0, "end")
            self._track_ordinals = {}
            labels = []
            for track in tracks:
                label = _track_choice_label(track)
                labels.append(label)
                self._track_ordinals[label] = track.ordinal
                self.audio_track_input.insert("end", label)
            self.audio_track_input.configure(height=min(3, max(2 if len(labels) > 1 else 1, len(labels))))
            wanted = set(selected)
            for index, label in enumerate(labels):
                if self._track_ordinals[label] in wanted:
                    self.audio_track_input.selection_set(index)
            if labels and not self.audio_track_input.curselection():
                self.audio_track_input.selection_set(0)
        finally:
            self._updating_tracks = False

    def _selected_track_numbers(self):
        numbers = []
        for index in self.audio_track_input.curselection():
            label = self.audio_track_input.get(index)
            try:
                numbers.append(self._track_ordinals[label] + 1)
            except KeyError:
                return ()
        return tuple(numbers)

    def _preview(self, text):
        self.preview.configure(state="normal")
        self.preview.delete("1.0", "end")
        self.preview.insert("1.0", text)
        self.preview.configure(state="disabled")

    def _controls(self):
        self.choose_button.configure(state="disabled" if self.busy else "normal")
        self.start_button.configure(state="normal" if self.path and self.inspected and not self.busy else "disabled")
        self.cancel_button.configure(state="normal" if self.busy and not self.cancel_event.is_set() else "disabled")
        self.discard_button.configure(state="normal" if self.result is not None else "disabled")
        self.export_button.configure(state="normal" if self.result is not None and not self.busy else "disabled")
        self.decoder_button.configure(state="disabled" if self.busy else "normal")
        self.model_button.configure(state="disabled" if self.busy else "normal")
        self.audio_track_input.configure(state=tk.DISABLED if self.busy else tk.NORMAL)
        self.inspect_button.configure(state="disabled" if self.busy or not self.path else "normal")
        self.timing_input.configure(state="normal" if not self.busy and self.inspected is not None
                                    and self.inspected.metadata.origin is not None else "disabled")
        self._timing_hint()

    def _timing_hint(self):
        metadata = self.inspected.metadata if self.inspected is not None else None
        if metadata is None:
            message = "Choose a file to inspect its timing."
        elif metadata.origin_kind == "pcm-sample-clock":
            message = "WAV times start at the beginning of the audio."
        elif metadata.origin is None:
            message = "Recording clock unavailable; times start at this track."
        elif not self.recording_timestamps.get():
            message = "Times start at this track; gaps are removed."
        elif metadata.origin_kind == "all-stream-starts":
            message = "Uses the earliest audio/video start; keeps gaps."
        else:
            message = "Keeps track offsets and pauses in the recording."
        self.timing_hint.configure(text=message)

    def _job_options_changed(self):
        if self._updating_tracks or self.busy or self.closed:
            return
        if self.result is not None:
            self.result = None
            self._preview("")
            self.status.set("Transcribe again to use the selected tracks and timing.")
        self._controls()

    def decoder_setup(self):
        if self.busy or self.closed:
            return
        if self.decoder_dialog is not None and self.decoder_dialog.winfo_exists():
            self.decoder_dialog.lift()
            return
        from utterleaf.file_decoder_ui import DecoderDialog
        self.decoder_dialog = DecoderDialog(self.root).root

    def choose(self):
        if self.busy:
            return
        path = filedialog.askopenfilename(parent=self.root, title="Choose local audio or video",
                                         filetypes=[("Audio and video", "*.wav *.mp3 *.m4a *.m4b *.aac *.flac *.ogg *.opus *.mp4 *.mov *.webm *.mkv"),
                                                    ("All files", "*.*")])
        if path:
            self.result = None
            self._preview("")
            self.path = Path(path)
            self.inspected = None
            self.inspection_signature = None
            self.recording_timestamps.set(False)
            self._show_tracks((), selected=())
            self.filename.set(self.path.name)
            self.status.set("Inspecting tracks…")
            self._controls()
            self._start_inspection()

    def inspect_tracks(self):
        if self.closed or self.busy or self.path is None:
            return
        self._start_inspection()

    def _start_inspection(self):
        self.busy = True
        self.operation = "inspection"
        self.cancel_event = threading.Event()
        self.events = queue.Queue(maxsize=8)
        self.status.set("Inspecting tracks…")
        self._controls()
        try:
            threading.Thread(target=_inspect_work, args=(self.path, self.cancel_event, self.events),
                             name="utterleaf-file-inspect", daemon=True).start()
        except Exception as exc:
            self.busy = False
            self.operation = None
            self.status.set("Could not start inspection.")
            self._controls()

    def start(self):
        if self.closed or self.busy or self.path is None:
            return
        if self.inspected is None or self.inspection_signature is None:
            self.status.set("Inspect tracks before starting recognition.")
            return
        audio_tracks = self._selected_track_numbers()
        if not audio_tracks:
            self.status.set("Choose at least one inspected audio track first.")
            self.audio_track_input.focus_set()
            return
        if self.recording_timestamps.get() and self.inspected.metadata.origin is None:
            self.status.set("Recording timestamps are unavailable for this file. Use track-relative timing.")
            return
        timing = "recording" if self.recording_timestamps.get() else "relative"
        self.result = None
        self._preview("")
        self.busy = True
        self.operation = "recognition"
        self.cancel_event = threading.Event()
        self.events = queue.Queue(maxsize=8)
        self.status.set("Opening the selected file…")
        self._controls()
        try:
            threading.Thread(target=_work, args=(self.path, self.cfg, audio_tracks,
                                                 self.cancel_event, self.events, self.inspection_signature, timing),
                             name="utterleaf-file", daemon=True).start()
        except Exception as exc:
            self.busy = False
            self.operation = None
            self.status.set("Could not start recognition.")
            self._controls()

    def cancel(self):
        if self.busy:
            self.cancel_event.set()
            if self.operation == "recognition":
                self.result = None
                self._preview("")
            if self.operation == "inspection":
                self.status.set("Cancelling track inspection… Existing preview is preserved.")
            else:
                self.status.set("Cancelling… The current model operation must finish first. Nothing will be saved.")
            self._controls()

    def discard(self):
        if self.busy:
            self.cancel()
            return
        self.result = None
        self._preview("")
        self.status.set("Preview discarded. Nothing was saved automatically.")
        self._controls()

    def poll(self):
        if self.closed:
            return
        if self.activation_requests.is_set():
            self.activation_requests.clear()
            from utterleaf.window_activation import raise_window
            raise_window(self.root)
        while True:
            try:
                kind, value = self.events.get_nowait()
            except queue.Empty:
                break
            if kind == "progress":
                if self.cancel_event.is_set():
                    continue
                phase, amount, *rest = value
                prefix = ""
                if len(rest) == 2 and rest[1] > 1:
                    prefix = f"Track {rest[0]} of {rest[1]}: "
                self.status.set(prefix + {"decoding": "Reading audio…", "loading": "Loading the installed model…",
                                 "timing": "Checking recording timestamps…",
                                 "recognizing": "Recognizing speech…", "complete": "Recognition complete."}.get(phase, phase))
                self.progress.stop()
                self.progress.configure(mode="indeterminate" if amount is None else "determinate")
                if amount is None:
                    self.progress.start(15)
                else:
                    self.progress["value"] = amount
            elif kind == "inspection":
                if self.cancel_event.is_set():
                    self.busy = False
                    self.operation = None
                    self.progress.stop()
                    self.status.set("Cancelled. Existing preview preserved.")
                    self._controls()
                    continue
                inspected = value
                unchanged = self.inspected is not None and inspected == self.inspected
                previous = self._selected_track_numbers()
                if not unchanged:
                    self.result = None
                    self._preview("")
                    self.recording_timestamps.set(inspected.metadata.origin is not None)
                    previous = ()
                self.inspected = inspected
                self.inspection_signature = inspected.signature
                self._show_tracks(
                    inspected.metadata.tracks,
                    selected=tuple(number - 1 for number in previous),
                )
                if inspected.metadata.tracks:
                    self.status.set("Tracks inspected. Choose one or more tracks, then transcribe.")
                self.busy = False
                self.operation = None
                self._controls()
            else:
                self.busy = False
                self.operation = None
                self.progress.stop()
                if self.cancel_event.is_set() or kind == "cancelled":
                    self.status.set("Cancelled. No transcript saved.")
                elif kind == "error":
                    self.status.set(value)
                elif kind == "result":
                    self.result = value
                    preview = preview_file_transcripts(value)
                    self._preview(preview)
                    self.status.set("Review the transcript, then choose an export format." if preview else "No speech recognized. You can discard or export the empty transcript.")
                self._controls()
        self.poll_id = self.root.after(100, self.poll)

    def export(self):
        if self.closed or self.busy or self.result is None:
            return
        format = self.format.get().lower()
        numbers = tuple(item.track.ordinal + 1 for item in self.result.tracks)
        selected = filedialog.asksaveasfilename(parent=self.root, title="Export transcript",
                                                defaultextension=f".{format}", confirmoverwrite=False,
                                                filetypes=[(format.upper(), f"*.{format}")])
        if not selected:
            return
        path = Path(selected)
        destinations = export_destinations(path, numbers)
        if self.path is not None:
            for destination in destinations:
                if destination.resolve() == self.path.resolve() or (
                    destination.exists() and self.path.exists() and destination.samefile(self.path)
                ):
                    self.status.set("Choose a different destination to preserve the original media file.")
                    return
        try:
            written = export_transcripts(self.result, path, format=format)
        except FileExistsError:
            existing = ", ".join(destination.name for destination in destinations if destination.exists())
            if not messagebox.askyesno("Replace transcript?", f"Replace {existing}?", parent=self.root):
                return
            try:
                written = export_transcripts(self.result, path, format=format, overwrite=True)
            except Exception as exc:
                self.status.set(f"Could not export: {exc}")
                return
        except Exception as exc:
            self.status.set(f"Could not export: {exc}")
            return
        names = ", ".join(item.name for item in written)
        self.status.set(f"Exported {format.upper()} to {names}.")

    def close(self):
        if self.closed:
            return
        self.closed = True
        self.cancel_event.set()
        self.result = None
        self.events = queue.Queue(maxsize=8)
        self._preview("")
        if self.poll_id is not None:
            self.root.after_cancel(self.poll_id)
        self.progress.stop()
        self.root.destroy()


def run(cfg: Config) -> int:
    import tkinter as tk
    from utterleaf.settings_instance import SettingsInstance
    from utterleaf.settings_ui import enable_dpi_awareness

    instance = SettingsInstance("files")
    requests = threading.Event()
    if not instance.acquire(requests.set):
        return 0
    try:
        enable_dpi_awareness()
        root = tk.Tk()
        window = FileWindow(root, cfg)
        window.activation_requests = requests
        root.mainloop()
        return 0
    finally:
        instance.close()


def run_files() -> int:
    from utterleaf.config import load

    return run(load())


def launch_files() -> None:
    from utterleaf.settings import _relaunch
    from utterleaf.settings_instance import activate

    if not activate("files"):
        _relaunch("--files")
