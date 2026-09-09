"""A lightweight, keyboard-accessible control center. No speech engine at import."""

from __future__ import annotations

import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from utterleaf import theme
from utterleaf.config import Config, load
from utterleaf.host import login_label, settings_blurb, ui_font, is_wayland
from utterleaf.polish import dictionary_text, polish_local
from utterleaf.settings import SYSTEM_DEFAULT, SettingsSaveError, apply_form, hotkey_presets
from utterleaf.startup import enabled as startup_enabled


class SettingsWindow:
    def __init__(self, root: tk.Tk, cfg: Config, *, background: bool = True):
        self.root, self.cfg = root, cfg
        self.events: queue.Queue = queue.Queue()
        self.closed = False
        self._page_reset = None
        self.saving = False
        self.mic_stop = threading.Event()
        self.pages: dict[str, ttk.Frame] = {}
        self.nav: dict[str, ttk.Button] = {}
        self.mascots = {}
        self.mascot_labels = {}
        self._mascot_heading_labels = set()
        self.appearance_guide = None
        self.report = ""
        self.vars = {}
        for key in ("hotkey", "mode", "model", "device", "language", "denoise", "microphone",
                    "beep", "indicator", "live_preview", "remove_fillers", "fix_corrections",
                    "restore_clipboard", "allow_network", "text_cleanup"):
            value = getattr(cfg, key)
            cls = tk.BooleanVar if isinstance(value, bool) else tk.StringVar
            self.vars[key] = cls(root, value=value)
        self.vars["microphone"].set(cfg.microphone or SYSTEM_DEFAULT)
        self.vars["start_at_login"] = tk.BooleanVar(root, value=startup_enabled())
        self.status = tk.StringVar(root, value="Your voice. Your device.")
        self.connection = tk.StringVar(root, value="Checking app…" if background else "App status unavailable")
        theme.apply(root)
        root.title("Utterleaf")
        root.minsize(760, 560)
        width = min(960, root.winfo_screenwidth() - 60)
        height = min(780, root.winfo_screenheight() - 90)
        root.geometry(f"{width}x{height}")
        root.columnconfigure(1, weight=1)
        root.rowconfigure(0, weight=1)
        try:
            from PIL import ImageTk
            self.icon = ImageTk.PhotoImage(theme.leaf_image(), master=root)
            root.iconphoto(True, self.icon)
        except Exception:
            pass

        sidebar = tk.Frame(root, bg=theme.SURFACE_LOW, width=190)
        sidebar.grid(row=0, column=0, sticky="nsew")
        sidebar.grid_propagate(False)
        tk.Label(sidebar, text="utterleaf", font=(ui_font(), 24, "bold"),
                 bg=theme.SURFACE_LOW, fg=theme.ON_SURFACE).pack(anchor="w", padx=22, pady=(28, 0))
        tk.Label(sidebar, text="LET IDEAS SPEAK.", font=(ui_font(), 8, "bold"),
                 bg=theme.SURFACE_LOW, fg=theme.ON_VARIANT).pack(anchor="w", padx=24, pady=(4, 22))
        for name in ("Dictation", "Vocabulary", "Voice commands", "Engine", "Help & diagnostics"):
            button = ttk.Button(sidebar, text=name, style="Nav.TButton",
                                command=lambda n=name: self.show_page(n))
            button.pack(fill="x", padx=12, pady=3)
            self.nav[name] = button
        tk.Label(sidebar, text="On-device dictation.\nNo account required.", justify="left",
                 font=(ui_font(), 9), fg=theme.ON_VARIANT, bg=theme.SURFACE_LOW,
                 wraplength=150).pack(side="bottom", anchor="w", padx=24, pady=18)

        content = ttk.Frame(root)
        content.grid(row=0, column=1, sticky="nsew")
        content.columnconfigure(0, weight=1)
        content.rowconfigure(0, weight=1)
        self.canvas = tk.Canvas(content, bg=theme.SURFACE, highlightthickness=0)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(content, orient="vertical", command=self.canvas.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.canvas.configure(yscrollcommand=scroll.set)
        self.body = ttk.Frame(self.canvas, padding=(30, 26, 30, 24))
        self.body.columnconfigure(0, weight=1)
        self.body.rowconfigure(0, weight=1)
        self.window_id = self.canvas.create_window(0, 0, window=self.body, anchor="nw")
        self.canvas.bind("<Configure>", self._resize)
        self.body.bind("<Configure>", lambda _e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        root.bind("<MouseWheel>", self._wheel, add="+")
        root.bind("<Button-4>", lambda e: self._wheel(e, -1), add="+")
        root.bind("<Button-5>", lambda e: self._wheel(e, 1), add="+")
        root.bind("<FocusIn>", self._reveal_focus, add="+")

        self._dictation()
        self._vocabulary()
        self._commands()
        self._engine()
        self._help()
        footer = ttk.Frame(root, padding=(20, 14))
        footer.grid(row=1, column=0, columnspan=2, sticky="ew")
        footer.columnconfigure(0, weight=1)
        ttk.Label(footer, textvariable=self.status, style="Hint.TLabel", wraplength=450).grid(row=0, column=0, sticky="w")
        ttk.Button(footer, text="Close", command=self.close).grid(row=0, column=1, padx=10)
        self.save_button = ttk.Button(footer, text="Save changes", style="Primary.TButton", command=self.save)
        self.save_button.grid(row=0, column=2)
        self.baseline = self._snapshot()
        for var in self.vars.values():
            var.trace_add("write", self._dirty)
        self.names.bind("<<Modified>>", self._names_changed)
        self.names.edit_modified(False)
        root.bind("<Control-s>", lambda _e: self.save())
        root.bind("<Command-s>", lambda _e: self.save())
        root.bind("<Escape>", lambda _e: self.close())
        root.protocol("WM_DELETE_WINDOW", self.close)
        self.show_page("Dictation")
        self._dirty()
        if background:
            self.refresh_mics()
            self._worker(self._connection_status, lambda value: self.connection.set(value))
        self.poll_id = root.after(80, self._poll)

    def _page(self, name, eyebrow, title, subtitle):
        frame = ttk.Frame(self.body)
        self.pages[name] = frame
        header = ttk.Frame(frame)
        header.pack(fill="x")
        header.columnconfigure(0, weight=1)
        words = ttk.Frame(header)
        words.grid(row=0, column=0, sticky="ew")
        eyebrow_label = ttk.Label(words, text=eyebrow.upper(), style="Eyebrow.TLabel", wraplength=560)
        eyebrow_label.pack(anchor="w")
        title_label = ttk.Label(words, text=title, style="Title.TLabel", wraplength=560)
        title_label.pack(anchor="w", pady=(6, 8))
        expression = {"Dictation": "default", "Vocabulary": "typing",
                      "Voice commands": "speaking", "Help & diagnostics": "thinking"}.get(name)
        if expression:
            label = ttk.Label(header, takefocus=False)
            label.grid(row=0, column=1, sticky="ne", padx=(12, 0))
            self.mascot_labels[name] = label
            if self._set_mascot(name, expression):
                self._mascot_heading_labels.update((eyebrow_label, title_label))
        if subtitle:
            ttk.Label(frame, text=subtitle, style="Hint.TLabel", wraplength=540).pack(anchor="w", pady=(0, 24))
        return frame

    def _set_mascot(self, page, expression):
        """Decorative only: instructions and microphone feedback stay in text."""
        from PIL import ImageTk
        from utterleaf.brand import mascot_image
        try:
            photo = ImageTk.PhotoImage(mascot_image(expression), master=self.root)
        except (OSError, tk.TclError):
            return False
        self.mascots[page] = photo
        self.mascot_labels[page].configure(image=photo)
        return True

    def _section(self, parent, title, hint=""):
        ttk.Separator(parent).pack(fill="x", pady=(10, 18))
        ttk.Label(parent, text=title, style="Section.TLabel").pack(anchor="w", pady=(0, 6))
        if hint:
            ttk.Label(parent, text=hint, style="Hint.TLabel", wraplength=520).pack(anchor="w", pady=(0, 12))

    def _choice(self, parent, label, key, values, *, editable=False):
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=6)
        row.columnconfigure(1, weight=1)
        ttk.Label(row, text=label, width=17).grid(row=0, column=0, sticky="w", padx=(0, 10))
        box = ttk.Combobox(row, textvariable=self.vars[key], values=values, width=24,
                           state="normal" if editable else "readonly")
        box.grid(row=0, column=1, sticky="ew")
        return box

    def _check(self, parent, title, key, hint=""):
        ttk.Checkbutton(parent, text=title, variable=self.vars[key]).pack(anchor="w", pady=(8, 2))
        if hint:
            ttk.Label(parent, text=hint, style="Hint.TLabel", wraplength=510).pack(anchor="w", padx=(24, 0), pady=(0, 4))

    def _text(self, parent, height=6):
        box = tk.Text(parent, height=height, wrap="word", undo=True, relief="flat",
                      bg=theme.SURFACE_LOW, fg=theme.ON_SURFACE, insertbackground=theme.PRIMARY,
                      highlightthickness=1, highlightbackground=theme.OUTLINE_VARIANT,
                      highlightcolor=theme.PRIMARY, padx=14, pady=12, font=(ui_font(), 11), width=30)
        box.pack(fill="x", pady=(6, 10))
        # Tab advances through the form; Return is always safe inside an editor.
        box.bind("<Tab>", lambda e: (e.widget.tk_focusNext().focus_set(), "break")[-1])
        box.bind("<Shift-Tab>", lambda e: (e.widget.tk_focusPrev().focus_set(), "break")[-1])
        return box

    def _dictation(self):
        p = self._page("Dictation", "On-device dictation", "Think it. Say it. Done.", "")
        card = tk.Frame(p, bg=theme.PRIMARY_CONTAINER, padx=20, pady=18)
        self.shortcut_card = card
        card.pack(fill="x", pady=(0, 12))
        self.shortcut_hint = tk.StringVar(self.root)
        tk.Label(card, textvariable=self.shortcut_hint, bg=theme.PRIMARY_CONTAINER,
                 fg=theme.ON_PRIMARY_CONTAINER, font=(ui_font(), 15, "bold"), wraplength=490,
                 justify="left").pack(anchor="w")
        self.shortcut_steps = tk.StringVar(self.root)
        tk.Label(card, textvariable=self.shortcut_steps,
                 bg=theme.PRIMARY_CONTAINER, fg=theme.ON_PRIMARY_CONTAINER,
                 font=(ui_font(), 10), wraplength=490, justify="left").pack(anchor="w", pady=(10, 0))
        self._choice(p, "Keyboard shortcut", "hotkey", [v for _, v in hotkey_presets() if v], editable=True)
        modes = ttk.Frame(p)
        modes.pack(fill="x", pady=(6, 12))
        ttk.Radiobutton(modes, text="Hold to talk", variable=self.vars["mode"], value="hold").pack(side="left", padx=(0, 24))
        ttk.Radiobutton(modes, text="Press to start / stop", variable=self.vars["mode"], value="toggle").pack(side="left")
        ttk.Label(p, text=f"Esc cancels a take. Stops automatically after {self.cfg.max_seconds:g} seconds.",
                  style="Hint.TLabel", wraplength=520).pack(anchor="w", pady=(0, 8))
        self._section(p, "Microphone", "Check that Utterleaf can hear you. Audio from this check is discarded.")
        self.mic_box = self._choice(p, "Input device", "microphone", [SYSTEM_DEFAULT])
        actions = ttk.Frame(p)
        actions.pack(fill="x", pady=8)
        self.mic_button = ttk.Button(actions, text="Test microphone", command=self.test_mic)
        self.mic_button.pack(side="left")
        self.refresh_button = ttk.Button(actions, text="Refresh devices", command=self.refresh_mics)
        self.refresh_button.pack(side="left", padx=8)
        self.mic_message = tk.StringVar(self.root, value="Ready for a quick, five-second check.")
        self.meter = ttk.Progressbar(p, maximum=100)
        self.meter.pack(fill="x", pady=(8, 6))
        ttk.Label(p, textvariable=self.mic_message, style="Hint.TLabel", wraplength=520).pack(anchor="w")
        self._section(p, "Make it feel right")
        self._check(p, "Play recording sounds", "beep")
        self._check(p, "Show the listening indicator", "indicator")
        self._check(p, "Show live captions", "live_preview", "Preview words while you speak. Uses additional processing power.")
        self._check(p, login_label(), "start_at_login")

    def _vocabulary(self):
        p = self._page("Vocabulary", "Words, your way", "A little more you.",
                       "Teach Utterleaf names, terms, and phrases you use every day.")
        self._check(p, "Clean up dictated text", "text_cleanup",
                    "Turn off to keep the model transcript unchanged. Vocabulary replacements and spoken commands "
                    "are also paused. Speech recognition can still make mistakes.")
        self._section(p, "Personal vocabulary", "One replacement per line: spoken = written. For example: utter leaf = Utterleaf")
        self.names = self._text(p, 8)
        self.names.insert("1.0", dictionary_text())
        self._section(p, "Text cleanup")
        self._check(p, "Remove filler words", "remove_fillers", "Clean up “um” and “uh” automatically.")
        self._check(p, "Follow spoken corrections", "fix_corrections", "Recognize corrections such as “no wait” and “I mean”.")
        self._section(p, "Try your cleanup", "Type a sample to preview your vocabulary and cleanup settings before saving.")
        self.sample = self._text(p, 3)
        self.sample.insert("1.0", "um I think we should try utter leaf")
        ttk.Button(p, text="Preview clean text", command=self.preview).pack(anchor="w", pady=(0, 10))
        self.preview_result = tk.StringVar(self.root, value="Your cleaned-up text will appear here.")
        ttk.Label(p, textvariable=self.preview_result, wraplength=520).pack(anchor="w", pady=8)

    def _commands(self):
        p = self._page("Voice commands", "Less editing. More flow.", "Let your voice do it.",
                       "Say a command as part of your dictation. These run locally, just like your speech model.")
        for title, description in (
            ("“New paragraph”", "Start a new paragraph. Say “new line” for a single line break."),
            ("“Scratch that”", "Discard this take. Said alone, it removes the last dictation when its text field can be verified."),
            ("“Make this shorter”", "Remove hedges and tighten the wording."),
            ("“Make it more professional”", "Expand slang and contractions with local text rules."),
            ("“Make a bulleted list …”", "Separate items with “bullet point” and “next bullet point”, or use “first”, “second”, and “third”. Say “end list” to return to prose. You can also ask for a numbered list."),
            ("“Comma” / “question mark”", "Add punctuation as you speak."),
        ):
            self._section(p, title, description)
        ttk.Label(p, text="Use edits immediately after dictating, in the same text field. If the field cannot be verified, "
                  "revised text is copied for you to replace manually. Your document is left alone.\n"
                  "Cleanup uses text rules; it does not generate new ideas or rewrite meaning.",
                  style="Hint.TLabel", wraplength=520).pack(anchor="w", pady=10)

    def _engine(self):
        p = self._page("Engine", "Local power, simple choices", "Find your balance.",
                       "The default model balances speed and accuracy. Smaller models use less memory and generally finish sooner.")
        self._section(p, "Speech model", "tiny: lightest  ·  base: faster  ·  small: balanced  ·  medium: larger\n"
                      "Changing models may require a one-time download. Custom model names and paths are supported.")
        self._choice(p, "Model", "model", ["tiny", "base", "small", "medium", "large-v3", "distil-small.en"], editable=True)
        self._choice(p, "Processing device", "device", ["auto", "cpu", "gpu", "npu"])
        ttk.Label(p, text="auto selects available acceleration. Unsupported selections fall back to a working device.",
                  style="Hint.TLabel", wraplength=520).pack(anchor="w", pady=8)
        self._choice(p, "Language", "language", ["en", "auto", "es", "fr", "de", "it", "pt", "ja", "zh"], editable=True)
        ttk.Label(p, text="Use auto to detect the language, or enter a language code. English-only models require English.",
                  style="Hint.TLabel", wraplength=520).pack(anchor="w", pady=8)
        self._choice(p, "Noise reduction", "denoise", ["auto", "on", "off"])
        self._section(p, "Privacy & clipboard", "Your microphone is released after each take. Audio is processed on this device "
                      "and is not saved to a recording history. The latest output has a two-minute recovery slot in memory. "
                      "Use Forget last dictation in the tray menu to clear it sooner. No account is required.")
        self._check(p, "Allow missing model downloads", "allow_network",
                    "Only model files are downloaded. Turn off to require an already installed model.")
        self._check(p, "Restore my clipboard after pasting", "restore_clipboard")

    def _help(self):
        p = self._page("Help & diagnostics", "A clear path forward", "Keep things running.",
                       "Check your setup and get a report when something needs attention.")
        ttk.Button(p, text="Icons & artwork…", command=self.show_appearance).pack(anchor="w", pady=(0, 14))
        ttk.Label(p, textvariable=self.connection, style="Section.TLabel").pack(anchor="w", pady=(0, 12))
        ttk.Label(p, text=settings_blurb(), style="Hint.TLabel", wraplength=520).pack(anchor="w", pady=(0, 14))
        self._section(p, "Quick checks", "No text? Click an editable text field before dictating.\n"
                      "Lost a result? Use Copy last dictation in the tray menu within two minutes.\n"
                      "No audio? Choose a microphone on the Dictation page and run a check.\n"
                      "First launch? Allow the speech model to finish downloading and loading.")
        self.diagnostic_button = ttk.Button(p, text="Check this device", command=self.diagnostics)
        self.diagnostic_button.pack(anchor="w", pady=10)
        self.diagnostic_text = self._text(p, 12)
        self.diagnostic_text.insert("1.0", "Your device report will appear here. Running a check does not download a model.")
        self.diagnostic_text.configure(state="disabled")
        self.export_button = ttk.Button(p, text="Save report…", command=self.export_report, state="disabled")
        self.export_button.pack(anchor="w", pady=(0, 8))
        self.cuda_button = ttk.Button(p, text="Set up NVIDIA GPU…", command=self.cuda_setup)
        self.cuda_button.pack(anchor="w")

    def show_appearance(self):
        if self.appearance_guide is not None and self.appearance_guide.root.winfo_exists():
            self.appearance_guide.root.lift()
            return
        from .appearance import AppearanceGuide
        self.appearance_guide = AppearanceGuide(self.root)

    def show_page(self, name):
        if name != "Dictation":
            self.mic_stop.set()
        for frame in self.pages.values():
            frame.grid_forget()
        self.pages[name].grid(row=0, column=0, sticky="nsew")
        for key, button in self.nav.items():
            button.configure(style="Selected.Nav.TButton" if key == name else "Nav.TButton")
        self.root.update_idletasks()
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        self.canvas.yview_moveto(0)
        # Finish geometry/focus events before fixing the new page at the top.
        if self._page_reset is not None:
            self.root.after_cancel(self._page_reset)
        self._page_reset = self.root.after_idle(self._scroll_top)

    def _scroll_top(self):
        self._page_reset = None
        self.canvas.yview_moveto(0)

    def _resize(self, event):
        self.canvas.itemconfigure(self.window_id, width=event.width)
        # Wrap copy to the actual content width, including high-DPI displays.
        def wrap(widget):
            for child in widget.winfo_children():
                if isinstance(child, (ttk.Label, tk.Label)) and int(child.cget("wraplength") or 0):
                    inset = 140 if child.master is self.shortcut_card else 90
                    if child in self._mascot_heading_labels:
                        inset += 116
                    child.configure(wraplength=max(180, event.width - inset))
                wrap(child)
        wrap(self.body)

    def _wheel(self, event, direction=None):
        if isinstance(event.widget, (tk.Text, ttk.Combobox)):
            return
        if self.canvas.bbox("all")[3] <= self.canvas.winfo_height():
            return
        direction = direction if direction is not None else (-1 if event.delta > 0 else 1)
        self.canvas.yview_scroll(direction * 3, "units")

    def _reveal_focus(self, event):
        widget = event.widget
        if not str(widget).startswith(str(self.body) + "."):
            return
        self.root.update_idletasks()
        top = widget.winfo_rooty() - self.canvas.winfo_rooty()
        bottom = top + widget.winfo_height()
        total = max(1, self.body.winfo_height())
        if top < 0:
            self.canvas.yview_moveto(self.canvas.yview()[0] + (top - 12) / total)
        elif bottom > self.canvas.winfo_height():
            self.canvas.yview_moveto(self.canvas.yview()[0] + (bottom - self.canvas.winfo_height() + 12) / total)

    def _snapshot(self):
        return {**{key: var.get() for key, var in self.vars.items()}, "names": self.names.get("1.0", "end-1c")}

    def _dirty(self, *_):
        dirty = self._snapshot() != self.baseline
        if not self.saving:
            self.save_button.configure(state="normal" if dirty else "disabled")
            self.status.set("Unsaved changes" if dirty else "All changes saved · Dictation stays on this device")
        verb = "Hold" if self.vars["mode"].get() == "hold" else "Press"
        self.shortcut_hint.set(
            "Use your desktop shortcut to start / stop"
            if is_wayland()
            else f"{verb}  {self.vars['hotkey'].get().replace('+', ' + ').title()}  to talk"
        )
        self.shortcut_steps.set(
            "Click a text field. Press your shortcut, wait for Listening, then speak. Press again to paste."
            if is_wayland() or self.vars["mode"].get() == "toggle"
            else "Click a text field. Hold your shortcut, wait for Listening, then speak. Release to paste."
        )

    def _names_changed(self, _event):
        if self.names.edit_modified():
            self.names.edit_modified(False)
            self._dirty()

    def _worker(self, action, done):
        def work():
            try:
                value = action()
            except Exception as exc:
                value = exc
            self.events.put((done, value))
        threading.Thread(target=work, daemon=True).start()

    def _poll(self):
        if self.closed:
            return
        for _ in range(60):
            try:
                callback, value = self.events.get_nowait()
            except queue.Empty:
                break
            callback(value)
        self.poll_id = self.root.after(80, self._poll)

    @staticmethod
    def _connection_status():
        from utterleaf import ipc
        return "Utterleaf is running in your tray" if ipc.send("ping") == "ok" else "Utterleaf is not running · Start the app to dictate"

    def refresh_mics(self):
        self.refresh_button.configure(state="disabled")
        saved = self.vars["microphone"].get()
        def query():
            from utterleaf.audio import list_input_names
            return list_input_names()
        def done(result):
            self.refresh_button.configure(state="normal")
            if isinstance(result, Exception):
                self.mic_message.set(f"Could not list microphones: {result}")
                return
            values = list(dict.fromkeys([SYSTEM_DEFAULT, *([saved] if saved else []), *result]))
            self.mic_box.configure(values=values)
            if not result:
                self.mic_message.set("No microphones found. Connect a microphone, then refresh.")
        self._worker(query, done)

    def test_mic(self):
        if str(self.mic_button.cget("text")) == "Stop check":
            self.mic_stop.set()
            return
        device = self.vars["microphone"].get()
        self.mic_stop.clear()
        self.mic_button.configure(text="Stop check")
        self._set_mascot("Dictation", "thinking")
        self.mic_message.set("Opening your microphone…")
        def check():
            import numpy as np
            from utterleaf.audio import Recorder
            recorder = Recorder(device="" if device == SYSTEM_DEFAULT else device)
            peak = 0.0
            try:
                recorder.start()
                self.events.put((lambda _: self._mic_check_listening(), None))
                for _ in range(50):
                    if self.mic_stop.wait(0.1):
                        break
                    audio = recorder.snapshot(max_seconds=0.15)
                    rms = float(np.sqrt(np.mean(audio * audio))) if audio.size else 0.0
                    peak = max(peak, rms)
                    self.events.put((lambda v: self.meter.configure(value=v), min(100, rms * 700)))
            finally:
                recorder.close()
            return peak
        def done(result):
            self.mic_button.configure(text="Test microphone")
            self.meter.configure(value=0)
            if isinstance(result, Exception):
                self._set_mascot("Dictation", "error")
                self.mic_message.set(f"Could not open the microphone: {result}")
            elif self.mic_stop.is_set():
                self._set_mascot("Dictation", "default")
                self.mic_message.set("Microphone check stopped.")
            else:
                self._set_mascot("Dictation", "success" if result > 0.003 else "thinking")
                self.mic_message.set("Audio detected. You’re ready to dictate." if result > 0.003
                                     else "Very little audio detected. Check your input device and microphone level.")
        self._worker(check, done)

    def _mic_check_listening(self):
        self._set_mascot("Dictation", "listening")
        self.mic_message.set("Speak now… checking for five seconds.")

    def preview(self):
        pairs = []
        for line in self.names.get("1.0", "end-1c").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                spoken, written = line.split("=", 1)
                if spoken.strip() and written.strip():
                    pairs.append((spoken.strip(), written.strip()))
        pairs.sort(key=lambda item: len(item[0]), reverse=True)
        result = polish_local(self.sample.get("1.0", "end-1c"), vocab=pairs,
                              remove_fillers=self.vars["remove_fillers"].get(),
                              fix_corrections=self.vars["fix_corrections"].get(),
                              text_cleanup=self.vars["text_cleanup"].get())
        self.preview_result.set(result.text or "No text to keep.")

    def diagnostics(self):
        self.diagnostic_button.configure(state="disabled", text="Checking device…")
        def report():
            from utterleaf.hardware import generate_diagnostic_report
            return generate_diagnostic_report(load())
        def done(result):
            self.diagnostic_button.configure(state="normal", text="Check this device")
            self.report = "" if isinstance(result, Exception) else result
            self.diagnostic_text.configure(state="normal")
            self.diagnostic_text.delete("1.0", "end")
            self.diagnostic_text.insert("1.0", f"Could not complete check: {result}" if isinstance(result, Exception) else result)
            self.diagnostic_text.configure(state="disabled")
            self.export_button.configure(state="normal" if self.report else "disabled")
        self._worker(report, done)

    def cuda_setup(self):
        self.cuda_button.configure(state="disabled", text="Checking…")
        def steps():
            from utterleaf.hardware import cuda_setup_plan
            return "\n".join(cuda_setup_plan())
        def done(result):
            self.cuda_button.configure(state="normal", text="Set up NVIDIA GPU…")
            self.report = "" if isinstance(result, Exception) else result
            self.diagnostic_text.configure(state="normal")
            self.diagnostic_text.delete("1.0", "end")
            self.diagnostic_text.insert("1.0", f"Could not check: {result}" if isinstance(result, Exception) else result)
            self.diagnostic_text.configure(state="disabled")
            self.export_button.configure(state="normal" if self.report else "disabled")
        self._worker(steps, done)

    def export_report(self):
        from pathlib import Path
        path = filedialog.asksaveasfilename(parent=self.root, title="Save device report", defaultextension=".txt",
                                          initialfile="Utterleaf diagnostics.txt", filetypes=[("Text file", "*.txt")])
        if path:
            try:
                Path(path).write_text(self.report, encoding="utf-8")
            except OSError as exc:
                messagebox.showerror("Could not save report", str(exc), parent=self.root)

    def save(self):
        if self.saving:
            return
        snapshot = self._snapshot()
        self.saving = True
        self.save_button.configure(state="disabled")
        self.status.set("Saving changes…")
        def commit():
            from utterleaf import ipc
            try:
                cfg = apply_form(load(), **snapshot)
            except SettingsSaveError as exc:
                if exc.saved:
                    ipc.send("reload")
                raise
            return cfg, ipc.send("reload")
        def done(result):
            self.saving = False
            if isinstance(result, Exception):
                self._dirty()
                self.status.set(
                    "Some changes saved · Review the error and retry Save"
                    if isinstance(result, SettingsSaveError) and result.saved
                    else "Could not finish saving. Review the error and try again."
                )
                messagebox.showerror("Could not save changes", str(result), parent=self.root)
                return
            self.cfg, reply = result
            self.baseline = snapshot
            self._dirty()
            if self._snapshot() == snapshot:
                self.status.set("Changes saved" if reply == "ok" else "Saved · Start Utterleaf to use these settings")
        self._worker(commit, done)

    def close(self):
        if self.saving:
            self.status.set("Finishing your save…")
            return
        if self._snapshot() != self.baseline:
            if not messagebox.askyesno("Discard unsaved changes?", "Close without saving your changes?", parent=self.root):
                return
        self.closed = True
        self.mic_stop.set()
        self.root.after_cancel(self.poll_id)
        if self._page_reset is not None:
            self.root.after_cancel(self._page_reset)
        self.root.destroy()


def enable_dpi_awareness():
    import sys
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except (AttributeError, OSError):
            pass


def run() -> int:
    enable_dpi_awareness()
    root = tk.Tk()
    SettingsWindow(root, load())
    root.mainloop()
    return 0
