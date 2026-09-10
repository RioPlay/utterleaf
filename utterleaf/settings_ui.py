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
from utterleaf.settings import SYSTEM_DEFAULT, FormValidationError, SettingsSaveError, apply_form, hotkey_presets
from utterleaf.startup import enabled as startup_enabled


class SettingsWindow:
    def __init__(self, root: tk.Tk, cfg: Config, *, background: bool = True):
        self.root, self.cfg = root, cfg
        self.events: queue.Queue = queue.Queue()
        self.closed = False
        self._page_reset = None
        self.saving = False
        self.model_downloading = False
        self.model_download_cancel = threading.Event()
        self._reset_pending = False
        self.mic_stop = threading.Event()
        self.pages: dict[str, ttk.Frame] = {}
        self.nav: dict[str, ttk.Button] = {}
        self.mascots = {}
        self.mascot_labels = {}
        self._mascot_heading_labels = set()
        self.appearance_guide = None
        self.report = ""
        self.vars = {}
        self.fields = {}
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
        root.title("Utterleaf · Settings")
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
        from importlib.resources import files
        from PIL import Image, ImageTk
        with files("utterleaf").joinpath("assets", "wordmark-inverse.png").open("rb") as stream:
            with Image.open(stream) as source:
                logo = source.convert("RGBA")
        logo.thumbnail((154, 46), Image.Resampling.LANCZOS)
        self.wordmark = ImageTk.PhotoImage(logo, master=root)
        tk.Label(sidebar, image=self.wordmark, bg=theme.SURFACE_LOW,
                 takefocus=False).pack(anchor="w", padx=18, pady=(28, 30))
        for name in ("Dictation", "Vocabulary", "Voice commands", "Engine", "Help & diagnostics"):
            label = {"Engine": "Speech & privacy", "Help & diagnostics": "Help"}.get(name, name)
            button = ttk.Button(sidebar, text=label, style="Nav.TButton",
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
        self.canvas = tk.Canvas(content, bg=theme.SURFACE_LOW, highlightthickness=0)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(content, orient="vertical", command=self.canvas.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.canvas.configure(yscrollcommand=scroll.set)
        self.body = ttk.Frame(self.canvas, style="Page.TFrame", padding=(26, 26, 26, 24))
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
        self.footer_status = ttk.Label(footer, textvariable=self.status, style="Hint.TLabel", wraplength=350)
        self.footer_status.grid(row=0, column=0, sticky="w")
        self.close_button = ttk.Button(footer, text="Close", command=self.close)
        self.close_button.grid(row=0, column=1, padx=10)
        self.save_button = ttk.Button(footer, text="Save changes", style="Primary.TButton", command=self.save)
        self.save_button.grid(row=0, column=2)
        footer.bind("<Configure>", self._resize_footer)
        self.baseline = self._snapshot()
        for var in self.vars.values():
            var.trace_add("write", self._dirty)
        for key in ("model", "language", "device"):
            self.vars[key].trace_add("write", self.refresh_model_status)
        self.refresh_model_status()
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
        frame = ttk.Frame(self.body, style="Page.TFrame")
        self.pages[name] = frame
        header = ttk.Frame(frame, style="Page.TFrame")
        header.pack(fill="x", pady=(0, 10))
        header.columnconfigure(0, weight=1)
        words = ttk.Frame(header, style="Page.TFrame")
        words.grid(row=0, column=0, sticky="ew")
        eyebrow_label = ttk.Label(words, text=eyebrow.upper(), style="Eyebrow.TLabel", wraplength=560)
        eyebrow_label.pack(anchor="w")
        title_label = ttk.Label(words, text=title, style="Title.TLabel", wraplength=560)
        title_label.pack(anchor="w", pady=(6, 8))
        expression = {"Dictation": "default", "Vocabulary": "typing",
                      "Voice commands": "speaking", "Help & diagnostics": "thinking"}.get(name)
        if expression:
            label = ttk.Label(header, style="Page.TLabel", takefocus=False)
            label.grid(row=0, column=1, sticky="ne", padx=(12, 0))
            self.mascot_labels[name] = label
            if self._set_mascot(name, expression):
                self._mascot_heading_labels.update((eyebrow_label, title_label))
        if subtitle:
            ttk.Label(frame, text=subtitle, style="Subtitle.TLabel", wraplength=540).pack(anchor="w", pady=(0, 18))
        return frame

    def _set_mascot(self, page, expression):
        """Decorative only: instructions and microphone feedback stay in text."""
        from PIL import ImageTk
        from utterleaf.brand import mascot_image
        try:
            photo = ImageTk.PhotoImage(mascot_image(expression, size=80), master=self.root)
        except (OSError, tk.TclError):
            return False
        self.mascots[page] = photo
        self.mascot_labels[page].configure(image=photo)
        return True

    def _section(self, parent, title, hint=""):
        border = tk.Frame(parent, bg=theme.SURFACE, highlightthickness=1,
                          highlightbackground=theme.OUTLINE_VARIANT)
        border.pack(fill="x", pady=(0, 14))
        panel = ttk.Frame(border, padding=16)
        panel.pack(fill="x")
        ttk.Label(panel, text=title, style="Section.TLabel").pack(anchor="w", pady=(0, 6))
        if hint:
            ttk.Label(panel, text=hint, style="Hint.TLabel", wraplength=520).pack(anchor="w", pady=(0, 8))
        return panel

    def _choice(self, parent, label, key, values, *, editable=False, labels=None):
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=6)
        row.columnconfigure(1, weight=1)
        ttk.Label(row, text=label, width=17).grid(row=0, column=0, sticky="w", padx=(0, 10))
        display = self.vars[key]
        if labels:
            display = tk.StringVar(self.root, value=labels.get(self.vars[key].get(), self.vars[key].get()))
            self.vars[key].trace_add("write", lambda *_: display.set(labels.get(self.vars[key].get(), self.vars[key].get())))
        box = ttk.Combobox(row, textvariable=display, values=list(labels.values()) if labels else values, width=24,
                           state="normal" if editable else "readonly")
        if labels:
            reverse = {value: key for key, value in labels.items()}
            box.bind("<<ComboboxSelected>>", lambda _: self.vars[key].set(reverse[display.get()]))
        box.grid(row=0, column=1, sticky="ew")
        self.fields[key] = box
        return box

    def _check(self, parent, title, key, hint=""):
        button = ttk.Checkbutton(parent, text=title, variable=self.vars[key])
        button.pack(anchor="w", pady=(8, 2))
        if hint:
            ttk.Label(parent, text=hint, style="Hint.TLabel", wraplength=510).pack(anchor="w", padx=(24, 0), pady=(0, 4))
        return button

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
        page = self._page("Dictation", "Settings", "Dictation", "")
        p = page
        card = tk.Frame(p, bg=theme.PRIMARY_CONTAINER, padx=16, pady=12)
        self.shortcut_card = card
        card.pack(fill="x", pady=(0, 12))
        self.shortcut_hint = tk.StringVar(self.root)
        tk.Label(card, textvariable=self.shortcut_hint, bg=theme.PRIMARY_CONTAINER,
                 fg=theme.ON_PRIMARY_CONTAINER, font=(ui_font(), 13, "bold"), wraplength=490,
                 justify="left").pack(anchor="w")
        self.shortcut_steps = tk.StringVar(self.root)
        tk.Label(card, textvariable=self.shortcut_steps,
                 bg=theme.PRIMARY_CONTAINER, fg=theme.ON_PRIMARY_CONTAINER,
                 font=(ui_font(), 10), wraplength=490, justify="left").pack(anchor="w", pady=(10, 0))
        p = self._section(page, "Your shortcut")
        self.hotkey_box = self._choice(p, "Keyboard shortcut", "hotkey", [v for _, v in hotkey_presets() if v], editable=True)
        if is_wayland():
            self.hotkey_box.configure(state="disabled")
            ttk.Label(p, text="Set your shortcut in desktop keyboard settings to the executable path followed by --toggle.",
                      style="Hint.TLabel", wraplength=520).pack(anchor="w", pady=(0, 8))
        modes = ttk.Frame(p)
        modes.pack(fill="x", pady=(6, 12))
        mode_state = "disabled" if is_wayland() else "normal"
        ttk.Radiobutton(modes, text="Hold to talk", variable=self.vars["mode"], value="hold", state=mode_state).pack(side="left", padx=(0, 24))
        ttk.Radiobutton(modes, text="Press to start / stop", variable=self.vars["mode"], value="toggle", state=mode_state).pack(side="left")
        self.limit_hint = tk.StringVar(self.root)
        ttk.Label(p, textvariable=self.limit_hint,
                  style="Hint.TLabel", wraplength=520).pack(anchor="w", pady=(0, 8))
        p = self._section(page, "Microphone", "Check your input. Test audio is discarded.")
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
        p = self._section(page, "Recording feedback", "Keep things quiet, or add a little guidance while you speak.")
        ttk.Radiobutton(p, text="Tray icon only", variable=self.vars["indicator"], value=False).pack(anchor="w", pady=4)
        ttk.Radiobutton(p, text="Tray + floating indicator", variable=self.vars["indicator"], value=True).pack(anchor="w", pady=4)
        ttk.Label(p, text="The floating indicator includes your remaining recording time.",
                  style="Hint.TLabel", wraplength=510).pack(anchor="w", pady=(0, 4))
        self.preview_toggle = self._check(p, "Preview dictation while recording", "live_preview",
                                         "Optional draft words while you speak. Uses additional processing power.")
        self._check(p, "Play start / stop sounds", "beep")
        p = self._section(page, "Startup")
        self._check(p, login_label(), "start_at_login")

    def _vocabulary(self):
        page = self._page("Vocabulary", "Settings", "Vocabulary",
                       "Teach Utterleaf names, terms, and phrases you use every day.")
        p = self._section(page, "Your words")
        self._check(p, "Clean up dictated text", "text_cleanup",
                    "Turn off to keep the model transcript unchanged. Vocabulary replacements and spoken commands "
                    "are also paused. Speech recognition can still make mistakes.")
        p = self._section(page, "Personal vocabulary", "One replacement per line: spoken = written. For example: utter leaf = Utterleaf")
        self.names = self._text(p, 8)
        self.fields["names"] = self.names
        self.names.insert("1.0", dictionary_text())
        p = self._section(page, "Text cleanup")
        self._check(p, "Remove filler words", "remove_fillers", "Clean up “um” and “uh” automatically.")
        self._check(p, "Follow spoken corrections", "fix_corrections", "Recognize corrections such as “no wait” and “I mean”.")
        p = self._section(page, "Try it out", "Preview your vocabulary and cleanup before saving.")
        self.sample = self._text(p, 3)
        self.sample.insert("1.0", "um I think we should try utter leaf")
        ttk.Button(p, text="Preview clean text", command=self.preview).pack(anchor="w", pady=(0, 10))
        self.preview_result = tk.StringVar(self.root, value="Your cleaned-up text will appear here.")
        ttk.Label(p, textvariable=self.preview_result, wraplength=520).pack(anchor="w", pady=8)

    def _commands(self):
        p = self._page("Voice commands", "Reference", "Voice commands",
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
        self._section(p, "“Scratch that, [replacement]”", "Replace the previous dictated entry with your new words. Pauses inside “scratch, that” are accepted.")
        ttk.Label(p, text="Use edits within two minutes, in the same unchanged text field. Automatic replacement requires a verified entry. "
                  "If a correction cannot be applied, follow the status message: select the old entry, use Copy last dictation, and paste.\n"
                  "Cleanup uses text rules; it does not generate new ideas or rewrite meaning.",
                  style="Subtitle.TLabel", wraplength=520).pack(anchor="w", pady=10)

    def _engine(self):
        page = self._page("Engine", "Settings", "Speech & privacy",
                       "The default model balances speed and accuracy. Smaller models use less memory and generally finish sooner.")
        p = self._section(page, "Model & installation", "tiny: lightest  ·  base: faster  ·  small: balanced  ·  medium: larger\n"
                      "Choose a model and language, then check its local installation. Downloading does not save other edits.")
        self._choice(p, "Model", "model", ["tiny", "base", "small", "medium", "large-v3", "distil-small.en"], editable=True)
        self._choice(p, "Language", "language", ["en", "auto", "es", "fr", "de", "it", "pt", "ja", "zh"], editable=True)
        ttk.Label(p, text="Use auto to detect the language, or enter a language code. English-only models require English.",
                  style="Hint.TLabel", wraplength=520).pack(anchor="w", pady=8)
        self.model_status = tk.StringVar(self.root)
        ttk.Label(p, textvariable=self.model_status, wraplength=520).pack(anchor="w", pady=(8, 4))
        self.model_action_status = tk.StringVar(self.root)
        ttk.Label(p, textvariable=self.model_action_status, style="Hint.TLabel", wraplength=520).pack(anchor="w", pady=4)
        actions = ttk.Frame(p)
        actions.pack(anchor="w", pady=(6, 8))
        self.model_download_button = ttk.Button(actions, text="Download selected model…", command=self.download_model)
        self.model_download_button.pack(side="left")
        self.model_cancel_button = ttk.Button(actions, text="Cancel download", command=self.cancel_model_download, state="disabled")
        self.model_cancel_button.pack(side="left", padx=8)
        ttk.Button(p, text="Refresh model status", command=self.refresh_model_status).pack(anchor="w")
        p = self._section(page, "Processing", "Device selection changes how speech is processed; it does not install hardware support.")
        self._choice(p, "Processing device", "device", [], labels={"auto": "Automatic", "cpu": "CPU", "gpu": "NVIDIA GPU", "npu": "NPU"})
        ttk.Label(p, text="Automatic selects available acceleration and may need a separate NPU model. "
                  "Choose CPU for the most portable setup and file transcription. Check hardware support under Help.",
                  style="Hint.TLabel", wraplength=520).pack(anchor="w", pady=8)
        self._choice(p, "Noise reduction", "denoise", [], labels={"auto": "Automatic", "on": "On", "off": "Off"})
        p = self._section(page, "Privacy & clipboard", "Your microphone is released after each take. Audio is processed on this device "
                      "and is not saved to a recording history. The latest output has a two-minute recovery slot in memory. "
                      "Use Forget last dictation in the tray menu to clear it sooner. No account is required.")
        self._check(p, "Allow missing model downloads", "allow_network",
                    "Only model files are downloaded. Turn off to require an already installed model.")
        self._check(p, "Restore my clipboard after pasting", "restore_clipboard")

    def _selected_model(self):
        from dataclasses import replace
        from utterleaf.model_setup import model_name
        cfg = replace(self.cfg, model=self.vars["model"].get(), language=self.vars["language"].get())
        return model_name(cfg), "openvino" if self.vars["device"].get() == "npu" else "ctranslate2"

    def refresh_model_status(self, *_):
        from utterleaf.model_setup import inspect_model
        name, backend = self._selected_model()
        state = inspect_model(name, backend)
        engine = "NPU / OpenVINO" if backend == "openvino" else "CPU / NVIDIA"
        messages = {"installed": "Installed — required files found locally. Loading has not been tested.",
                    "missing": "Missing — download this model before using it offline.",
                    "incomplete": "Incomplete — required files are missing or invalid. Download to finish setup.",
                    "unsupported": "Guided setup is unavailable for this model/device. Choose a listed model or CPU."}
        self.model_status.set(f"{name or 'No model selected'} · {engine}\n{messages[state.state]}")
        self.model_download_button.configure(state="normal" if not self.model_downloading and state.state in {"missing", "incomplete"} else "disabled")

    def download_model(self):
        if self.model_downloading or self.closed:
            return
        from utterleaf.model_setup import inspect_model, run_download
        name, backend = self._selected_model()
        if inspect_model(name, backend).state not in {"missing", "incomplete"}:
            self.refresh_model_status()
            return
        engine = "NPU / OpenVINO" if backend == "openvino" else "CPU / NVIDIA"
        if not messagebox.askyesno("Download this speech model?",
            f"Download {name} for {engine} from Hugging Face now?\n\n"
            "This may use hundreds of MB or several GB of data and disk space. Only required missing or invalid files are fetched.\n\n"
            "This permits this download once. Your ongoing network preference and unsaved settings stay unchanged.", parent=self.root):
            return
        self.model_downloading = True
        self.model_download_cancel = threading.Event()
        cancel = self.model_download_cancel
        self.model_action_status.set(f"Downloading {name}… Keep this window open; Cancel stops the download.")
        self.model_cancel_button.configure(state="normal")
        self.refresh_model_status()
        def done(result):
            if self.closed:
                return
            self.model_downloading = False
            self.model_cancel_button.configure(state="disabled")
            self.refresh_model_status()
            if cancel.is_set():
                self.model_action_status.set("Download cancelled. Partial files are kept so you can retry.")
            elif isinstance(result, Exception):
                self.model_action_status.set(str(result))
            else:
                self.model_action_status.set(f"{name} installed. Save changes to use a changed selection; reopen file transcription to reload its settings.")
        # Keep the cancellation/reaping worker alive when closing the last Tk window.
        self._worker(lambda: run_download(name, backend, cancel=cancel), done, daemon=False)

    def cancel_model_download(self):
        self.model_download_cancel.set()
        self.model_cancel_button.configure(state="disabled")
        self.model_action_status.set("Cancelling model download…")

    def _help(self):
        page = self._page("Help & diagnostics", "Support", "Help",
                         "Recover your words, check your setup, or start fresh.")
        p = self._section(page, "App status")
        ttk.Label(p, textvariable=self.connection, wraplength=520).pack(anchor="w", pady=(0, 12))
        ttk.Label(p, text=settings_blurb(), style="Hint.TLabel", wraplength=520).pack(anchor="w", pady=(0, 14))
        p = self._section(page, "Quick checks", "No text? Click an editable text field before dictating.\n"
                      "Lost a result? Use Copy last dictation in the tray menu within two minutes.\n"
                      "No audio? Choose a microphone on the Dictation page and run a check.\n"
                      "First launch? Allow the speech model to finish downloading and loading.")
        p = self._section(page, "A fresh start", "Restore preferences without removing your vocabulary or models.")
        self.reset_button = ttk.Button(p, text="Restore default settings…", command=self.restore_defaults)
        self.reset_button.pack(anchor="w", pady=(10, 4))
        p = self._section(page, "Local backup", "Review and export portable preferences and vocabulary, or inspect a selected backup before applying it.")
        ttk.Button(p, text="Export backup…", command=lambda: self.show_backup(False)).pack(anchor="w", pady=4)
        ttk.Button(p, text="Import backup…", command=lambda: self.show_backup(True)).pack(anchor="w", pady=4)
        p = self._section(page, "Device report", "Check your setup without downloading a model. Review the report before sharing it.")
        self.diagnostic_button = ttk.Button(p, text="Check this device", command=self.diagnostics)
        self.diagnostic_button.pack(anchor="w", pady=10)
        self.diagnostic_text = self._text(p, 12)
        self.diagnostic_text.insert("1.0", "Your device report will appear here. Running a check does not download a model.")
        self.diagnostic_text.configure(state="disabled")
        self.export_button = ttk.Button(p, text="Save report…", command=self.export_report, state="disabled")
        self.export_button.pack(anchor="w", pady=(0, 8))
        self.cuda_button = ttk.Button(p, text="Set up NVIDIA GPU…", command=self.cuda_setup)
        self.cuda_button.pack(anchor="w")
        p = self._section(page, "Meet Utterling", "Your local companion. Explore the artwork and export icons for light or dark backgrounds.")
        ttk.Button(p, text="Icons & artwork…", command=self.show_appearance).pack(anchor="w", pady=(4, 0))

    def show_appearance(self):
        if self.appearance_guide is not None and self.appearance_guide.root.winfo_exists():
            self.appearance_guide.root.lift()
            return
        from .appearance import AppearanceGuide
        self.appearance_guide = AppearanceGuide(self.root)

    def show_backup(self, importing=False):
        if self.saving:
            return
        if self._reset_pending or self._snapshot() != self.baseline:
            messagebox.showinfo("Save your current edits first", "Save changes or reopen Settings before reviewing a backup.", parent=self.root)
            return
        from pathlib import Path
        from utterleaf.backup_store import read_backup, read_current
        from utterleaf.backup_ui import BackupDialog
        try:
            plan = None
            if importing:
                name = filedialog.askopenfilename(parent=self.root, title="Select a backup to inspect", filetypes=[("JSON backup", "*.json")])
                if not name:
                    return
                plan = read_backup(Path(name))
            cfg, vocabulary = read_current()
            self.backup_dialog = BackupDialog(self.root, cfg, vocabulary, plan=plan, on_applied=self._backup_applied)
        except Exception:
            messagebox.showerror("Backup unavailable", "The selected backup or current settings could not be read safely. No changes saved.", parent=self.root)

    def _backup_applied(self, values):
        self.cfg = values.config
        for key, var in self.vars.items():
            if key != "start_at_login":
                value = getattr(self.cfg, key)
                var.set(value or SYSTEM_DEFAULT if key == "microphone" else value)
        self.names.delete("1.0", "end")
        self.names.insert("1.0", values.vocabulary_text)
        self.names.edit_modified(False)
        self.baseline = self._snapshot()
        self._dirty()
        from utterleaf import ipc
        self._worker(lambda: ipc.send("reload"), lambda result: self.status.set(
            "Backup imported · app reloaded" if result == "ok" else "Backup imported · restart the dictation app to use the saved settings"))

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
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        self.canvas.yview_moveto(0)

    def _resize(self, event):
        self.canvas.itemconfigure(self.window_id, width=event.width)
        # Wrap copy to the actual content width, including high-DPI displays.
        def wrap(widget):
            for child in widget.winfo_children():
                if isinstance(child, (ttk.Label, tk.Label)) and int(child.cget("wraplength") or 0):
                    inset = 140 if child.master is self.shortcut_card else 104
                    if child in self._mascot_heading_labels:
                        inset += 92
                    child.configure(wraplength=max(180, event.width - inset))
                wrap(child)
        wrap(self.body)

    def _resize_footer(self, event):
        available = event.width - self.close_button.winfo_reqwidth() - self.save_button.winfo_reqwidth() - 68
        self.footer_status.configure(wraplength=max(120, min(450, available)))

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

    def restore_defaults(self):
        if self.saving:
            return
        if not messagebox.askyesno(
            "Restore default settings?",
            "Restore app defaults, including advanced settings?\n\n"
            "This selects the system microphone, automatic hardware, English, and the small model; "
            "and turns off start at login and the floating indicator.\n\n"
            "Your download and clipboard preferences are kept, along with vocabulary and models. "
            "Nothing changes on disk until you choose Save changes.",
            parent=self.root,
        ):
            return
        defaults = Config()
        privacy = {key: self.vars[key].get() for key in ("allow_network", "restore_clipboard")}
        self._reset_pending = True
        self.mic_stop.set()
        for key, var in self.vars.items():
            value = privacy[key] if key in privacy else False if key == "start_at_login" else getattr(defaults, key)
            var.set(SYSTEM_DEFAULT if key == "microphone" else value)
        self._dirty()
        self.status.set("Defaults ready to review · Save changes to apply")

    def _dirty(self, *_):
        self.preview_toggle.configure(state="normal" if self.vars["indicator"].get() else "disabled")
        dirty = self._reset_pending or self._snapshot() != self.baseline
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
            else "Click a text field. Hold until Listening, speak, then release to paste."
        )
        limit = Config().max_seconds if self._reset_pending else self.cfg.max_seconds
        self.limit_hint.set(
            ("Desktop shortcut toggles recording; global Esc is unavailable. " if is_wayland() else "Esc cancels a take. ")
            + f"Stops automatically after {limit:g} seconds."
        )

    def _names_changed(self, _event):
        if self.names.edit_modified():
            self.names.edit_modified(False)
            self._dirty()

    def _worker(self, action, done, *, daemon=True):
        def work():
            try:
                value = action()
            except Exception as exc:
                value = exc
            self.events.put((done, value))
        threading.Thread(target=work, daemon=daemon).start()

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
            elif self.vars["microphone"].get() not in ("", SYSTEM_DEFAULT, *result):
                self.mic_message.set("Selected microphone is unavailable. Reconnect it or choose another input and Save.")
            else:
                self.mic_message.set("Devices refreshed. Choose an input, then Test microphone. Save to apply changes.")
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
            from utterleaf.audio import Recorder, MicrophoneCaptureInterrupted
            recorder = Recorder(device="" if device == SYSTEM_DEFAULT else device)
            peak = 0.0
            try:
                recorder.start()
                self.events.put((lambda _: self._mic_check_listening(), None))
                for _ in range(50):
                    if self.mic_stop.wait(0.1):
                        break
                    if recorder.capture_error():
                        raise MicrophoneCaptureInterrupted()
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
                from utterleaf.audio import microphone_error_hint
                self.mic_message.set(microphone_error_hint(result))
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
        reset_pending = self._reset_pending
        self.saving = True
        self.save_button.configure(state="disabled")
        self.reset_button.configure(state="disabled")
        self.status.set("Saving changes…")
        def commit():
            from utterleaf import ipc
            try:
                cfg = apply_form(Config() if reset_pending else load(), **snapshot)
            except SettingsSaveError as exc:
                if exc.saved:
                    ipc.send("reload")
                raise
            return cfg, ipc.send("reload")
        def done(result):
            self.saving = False
            self.reset_button.configure(state="normal")
            if isinstance(result, Exception):
                self._dirty()
                if isinstance(result, FormValidationError):
                    self._show_invalid_field(result)
                    return
                self.status.set(
                    "Some changes saved · Review the error and retry Save"
                    if isinstance(result, SettingsSaveError) and result.saved
                    else "Could not finish saving. Review the error and try again."
                )
                messagebox.showerror("Could not save changes", str(result), parent=self.root)
                return
            self.cfg, reply = result
            self._reset_pending = False
            self.baseline = snapshot
            self._dirty()
            if self._snapshot() == snapshot:
                self.status.set("Saved · Quit and reopen Utterleaf to apply this update" if reply == "restart-required"
                                else "Changes saved" if reply == "ok" else "Saved · Start Utterleaf to use these settings")
        self._worker(commit, done)

    def _show_invalid_field(self, error):
        page = ("Vocabulary" if error.field == "names" else "Dictation"
                if error.field in {"hotkey", "mode"} else "Engine")
        self.show_page(page)
        if self._page_reset is not None:
            self.root.after_cancel(self._page_reset)
            self._page_reset = None
        field = self.fields.get(error.field)
        self.status.set(str(error))
        messagebox.showerror("Check your settings", str(error), parent=self.root)
        if field is not None:
            field.focus_set()
            if isinstance(field, tk.Text):
                line = error.line or 1
                field.tag_remove("sel", "1.0", "end")
                field.tag_add("sel", f"{line}.0", f"{line}.end")
                field.mark_set("insert", f"{line}.0")
                field.see(f"{line}.0")
            else:
                field.selection_range(0, "end")
            from types import SimpleNamespace
            self._reveal_focus(SimpleNamespace(widget=field))

    def close(self):
        if self.saving:
            self.status.set("Finishing your save…")
            return
        if self._reset_pending or self._snapshot() != self.baseline:
            if not messagebox.askyesno("Discard unsaved changes?", "Close without saving your changes?", parent=self.root):
                return
        self.closed = True
        self.model_download_cancel.set()
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
    from utterleaf.settings_instance import SettingsInstance

    requests = threading.Event()
    instance = SettingsInstance()
    if not instance.acquire(requests.set):
        return 0
    root = None
    try:
        enable_dpi_awareness()
        root = tk.Tk()
        window = SettingsWindow(root, load())

        def poll_activation():
            if window.closed:
                return
            if requests.is_set():
                requests.clear()
                from utterleaf.window_activation import raise_window
                raise_window(root)
            root.after(100, poll_activation)

        poll_activation()
        root.mainloop()
    finally:
        instance.close()
        if root is not None:
            try:
                root.destroy()
            except tk.TclError:
                pass
    return 0
