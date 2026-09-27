"""An explicit local-file workflow, separate from ordinary dictation."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import queue
import threading

from utterleaf import theme
from utterleaf.config import Config
from utterleaf.file_transcription import transcribe_file
from utterleaf.transcript import TranscriptionCancelled, export_transcript
from utterleaf.ui_layout import ActionRow, ScrollableContent, readonly_preview, wrapped_label
from utterleaf.ui_feedback import RecoveryFeedback


def _work(path, cfg, audio_track, cancel, events):
    # Only this bounded queue crosses threads. Workers never touch Tk widgets.
    def send(kind, value):
        try:
            events.put_nowait((kind, value))
        except queue.Full:
            try:
                events.get_nowait()
            except queue.Empty:
                pass
            events.put_nowait((kind, value))

    try:
        result = transcribe_file(path, cfg, audio_track=audio_track, cancel=cancel,
                                 progress=lambda phase, amount: send("progress", (phase, amount)))
        send("cancelled", None) if cancel.is_set() else send("result", result)
    except TranscriptionCancelled:
        send("cancelled", None)
    except Exception as exc:
        send("cancelled", None) if cancel.is_set() else send("error", str(exc))


class FileWindow:
    def __init__(self, root, cfg: Config):
        global tk, filedialog, messagebox, ttk
        import tkinter as tk
        from tkinter import filedialog, messagebox, ttk

        self.root = root
        self.cfg = replace(cfg)
        self.closed = False
        self.busy = False
        self.result = None
        self.path = None
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
        root.columnconfigure(0, weight=1)
        root.rowconfigure(0, weight=1)
        self.content = ScrollableContent(root, padding=24)
        self.content.grid(row=0, column=0, sticky="nsew")
        page = self.content.body
        page.columnconfigure(0, weight=1)
        page.rowconfigure(5, weight=1)
        heading = ttk.Frame(page)
        heading.grid(row=0, column=0, rowspan=3, sticky="ew")
        heading.columnconfigure(0, weight=1)
        wrapped_label(heading, text="Transcribe a file", style="Section.TLabel").grid(row=0, column=0, sticky="ew")
        wrapped_label(heading, text="Choose local audio, review the words, then export when ready.").grid(row=1, column=0, sticky="ew", pady=(8, 4))
        self.file_guidance = wrapped_label(
            heading,
            text="No duration limit · Processing stays on this computer · Installed models only\n"
                 "MP3, M4A and video: choose More formats to set up local decoding.",
            style="Hint.TLabel",
        )
        self.file_guidance.grid(row=2, column=0, sticky="ew")
        from PIL import ImageTk
        from utterleaf.brand import mascot_image
        self.mascot = ImageTk.PhotoImage(mascot_image("typing", size=80), master=root)
        ttk.Label(heading, image=self.mascot).grid(row=0, column=1, rowspan=3, padx=(12, 0))
        select = ttk.Frame(page)
        select.grid(row=3, column=0, sticky="ew", pady=16)
        select.columnconfigure(1, weight=1)
        file_actions = ActionRow(select)
        file_actions.grid(row=0, column=0, columnspan=2, sticky="ew")
        self.choose_button = file_actions.add(ttk.Button(file_actions, text="Choose file…", command=self.choose))
        self.filename = tk.StringVar(value="No file selected")
        wrapped_label(select, textvariable=self.filename).grid(row=1, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        self.start_button = file_actions.add(ttk.Button(file_actions, text="Transcribe", style="Primary.TButton", command=self.start, state="disabled"))
        self.audio_track_label = ttk.Label(select, text="Audio track", underline=0)
        self.audio_track_label.grid(row=2, column=0, sticky="w", pady=(10, 0))
        self.audio_track = tk.StringVar(value="1")
        track_style = ttk.Style(root)
        track_style.configure("File.TSpinbox", fieldbackground=theme.SURFACE_LOW,
                              background=theme.SURFACE_LOW, foreground=theme.ON_SURFACE,
                              arrowcolor=theme.ON_VARIANT, bordercolor=theme.OUTLINE_VARIANT,
                              lightcolor=theme.OUTLINE_VARIANT, darkcolor=theme.OUTLINE_VARIANT,
                              padding=4)
        track_style.map("File.TSpinbox", bordercolor=[("focus", theme.PRIMARY)],
                        lightcolor=[("focus", theme.PRIMARY)], darkcolor=[("focus", theme.PRIMARY)],
                        foreground=[("disabled", theme.OUTLINE)])
        self.audio_track_input = ttk.Spinbox(select, from_=1, to=256, increment=1,
                                              textvariable=self.audio_track, width=6,
                                              style="File.TSpinbox")
        self.audio_track_input.grid(row=2, column=1, sticky="w", padx=12, pady=(10, 0))
        root.bind("<Alt-a>", lambda _event: self.audio_track_input.focus_set(), add="+")
        self.audio_track_hint = wrapped_label(
            select,
            text="A track is a separate audio stream, not a stereo channel. "
                 "Utterleaf does not identify speakers.",
            style="Hint.TLabel",
        )
        self.audio_track_hint.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(4, 0))
        preview_heading = ttk.Frame(page)
        preview_heading.grid(row=4, column=0, sticky="ew", pady=(0, 8))
        preview_heading.columnconfigure(0, weight=1)
        wrapped_label(preview_heading, text="Transcript preview", style="Section.TLabel").grid(row=0, column=0, sticky="ew")
        preview_actions = ActionRow(preview_heading)
        preview_actions.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        from utterleaf.settings import launch_settings
        self.model_button = preview_actions.add(ttk.Button(preview_actions, text="Model settings…", command=launch_settings))
        self.decoder_button = preview_actions.add(ttk.Button(preview_actions, text="More formats…", command=self.decoder_setup))
        self.decoder_dialog = None
        preview_frame = ttk.Frame(page)
        preview_frame.grid(row=5, column=0, sticky="nsew")
        self.preview = tk.Text(preview_frame, wrap="word", width=1, height=8, state="disabled",
                               bg=theme.SURFACE_LOW, fg=theme.ON_SURFACE,
                               selectbackground=theme.PRIMARY_CONTAINER, selectforeground=theme.ON_SURFACE,
                               highlightbackground=theme.OUTLINE_VARIANT, highlightcolor=theme.PRIMARY,
                               insertbackground=theme.ON_SURFACE, padx=12, pady=12, relief="flat")
        scrollbar = ttk.Scrollbar(preview_frame, command=self.preview.yview)
        scrollbar.pack(side="right", fill="y")
        self.preview.configure(yscrollcommand=scrollbar.set)
        self.preview.pack(fill="both", expand=True)
        readonly_preview(self.preview)
        self.progress = ttk.Progressbar(page, maximum=1.0)
        self.progress.grid(row=6, column=0, sticky="ew", pady=(14, 8))
        self.status = tk.StringVar(value="Nothing is saved until you export. Closing discards this preview.")
        self.feedback = RecoveryFeedback(page, self.status)
        self.feedback.grid(row=7, column=0, sticky="ew")
        actions = self.actions = ActionRow(root)
        actions.grid(row=1, column=0, sticky="ew", padx=24, pady=(12, 20))
        self.cancel_button = ttk.Button(actions, text="Cancel", command=self.cancel, state="disabled")
        actions.add(self.cancel_button)
        self.discard_button = ttk.Button(actions, text="Discard", command=self.discard, state="disabled")
        actions.add(self.discard_button)
        self.format = tk.StringVar(value="TXT")
        format_group = ttk.Frame(actions)
        ttk.Label(format_group, text="Format").pack(side="left", padx=(0, 8))
        ttk.Combobox(format_group, textvariable=self.format, values=("TXT", "SRT", "VTT"), state="readonly", width=5).pack(side="left")
        actions.add(format_group)
        self.export_button = ttk.Button(actions, text="Export…", command=self.export, state="disabled")
        actions.add(self.export_button)
        actions.add(ttk.Button(actions, text="Close", command=self.close))
        self.poll_id = root.after(100, self.poll)
        self.choose_button.focus_set()

    def _preview(self, text):
        self.preview.configure(state="normal")
        self.preview.delete("1.0", "end")
        self.preview.insert("1.0", text)
        self.preview.mark_set("insert", "1.0")
        self.preview.configure(state="disabled")

    def _controls(self):
        self.choose_button.configure(state="disabled" if self.busy else "normal")
        self.start_button.configure(state="normal" if self.path and not self.busy else "disabled")
        self.cancel_button.configure(state="normal" if self.busy and not self.cancel_event.is_set() else "disabled")
        self.discard_button.configure(state="normal" if self.result is not None else "disabled")
        self.export_button.configure(state="normal" if self.result is not None and not self.busy else "disabled")
        self.decoder_button.configure(state="disabled" if self.busy else "normal")
        self.model_button.configure(state="disabled" if self.busy else "normal")
        self.audio_track_input.configure(state="disabled" if self.busy else "normal")

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
            self.discard()
            self.path = Path(path)
            self.filename.set(self.path.name)
            self.status.set("Ready. Recognition uses installed models and stays on this computer.")
            self._controls()

    def start(self):
        if self.closed or self.busy or self.path is None:
            return
        try:
            audio_track = int(self.audio_track.get())
        except ValueError:
            audio_track = 0
        if not 1 <= audio_track <= 256:
            self.status.set("Audio track must be a whole number from 1 to 256.")
            self.audio_track_input.focus_set()
            return
        self.discard()
        self.busy = True
        self.cancel_event = threading.Event()
        self.events = queue.Queue(maxsize=8)
        self.status.set("Opening the selected file…")
        self._controls()
        threading.Thread(target=_work, args=(self.path, self.cfg, audio_track - 1,
                                             self.cancel_event, self.events),
                         name="utterleaf-file", daemon=True).start()

    def cancel(self):
        if self.busy:
            self.cancel_event.set()
            self.result = None
            self._preview("")
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
                phase, amount = value
                self.status.set({"decoding": "Reading audio…", "loading": "Loading the installed model…",
                                 "recognizing": "Recognizing speech…", "complete": "Recognition complete."}.get(phase, phase))
                self.progress.stop()
                self.progress.configure(mode="indeterminate" if amount is None else "determinate")
                if amount is None:
                    self.progress.start(15)
                else:
                    self.progress["value"] = amount
            else:
                self.busy = False
                self.progress.stop()
                if self.cancel_event.is_set() or kind == "cancelled":
                    self.status.set("Cancelled. No transcript saved.")
                elif kind == "error":
                    self.feedback.error(
                        "Couldn't transcribe this file",
                        "No transcript is available to export.",
                        "Check the audio track, Model settings or More formats, then choose Transcribe to retry.",
                        value,
                    )
                    self.content.reveal(self.feedback)
                elif kind == "result":
                    self.result = value
                    self._preview(value.text)
                    self.status.set("Review the transcript, then choose an export format." if value.text else "No speech recognized. You can discard or export the empty transcript.")
                self._controls()
        self.poll_id = self.root.after(100, self.poll)

    def export(self):
        if self.closed or self.busy or self.result is None:
            return
        format = self.format.get().lower()
        selected = filedialog.asksaveasfilename(parent=self.root, title="Export transcript",
                                                defaultextension=f".{format}", confirmoverwrite=False,
                                                filetypes=[(format.upper(), f"*.{format}")])
        if not selected:
            return
        path = Path(selected)
        try:
            if self.path is not None and (path.resolve() == self.path.resolve() or
                                         (path.exists() and self.path.exists() and path.samefile(self.path))):
                self.status.set("Choose a different destination to preserve the original media file.")
                return
        except Exception as exc:
            self._export_error(exc)
            return
        try:
            export_transcript(self.result, path, format=format)
        except FileExistsError:
            if not messagebox.askyesno("Replace transcript?", f"Replace {path.name}?", parent=self.root):
                return
            try:
                export_transcript(self.result, path, format=format, overwrite=True)
            except Exception as exc:
                self._export_error(exc)
                return
        except Exception as exc:
            self._export_error(exc)
            return
        self.status.set(f"Exported {format.upper()} to {path.name}.")

    def _export_error(self, error):
        self.feedback.error(
            "Couldn't export transcript",
            "Your preview is still available.",
            "Check the destination file, then choose Export and select a writable location to retry.",
            error,
        )
        self.content.reveal(self.feedback)

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
