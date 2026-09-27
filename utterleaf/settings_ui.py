"""A lightweight, keyboard-accessible control center. No speech engine at import."""

from __future__ import annotations

from dataclasses import dataclass
import queue
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from types import SimpleNamespace

from utterleaf import theme
from utterleaf.config import Config, load
from utterleaf.host import login_label, settings_blurb, ui_font, is_wayland
from utterleaf.model_presentation import model_display_name, model_purpose
from utterleaf.polish import dictionary_text, polish_local
from utterleaf.save_presentation import save_failure
from utterleaf.settings import SYSTEM_DEFAULT, FormValidationError, SettingsSaveError, apply_form, hotkey_presets
from utterleaf.startup import enabled as startup_enabled
from utterleaf.ui_feedback import RecoveryFeedback, technical_details


# Keep paragraphs readable on wide desktops; scale with the native text size.
MAX_PAGE_WIDTH = 860


@dataclass(frozen=True)
class _SearchTarget:
    key: str
    label: str
    page: str
    page_label: str
    section: str
    widget: tk.Misc
    terms: str


@dataclass(frozen=True)
class _SaveOutcome:
    config: Config | None = None
    error: Exception | None = None
    reply: str | None = None
    reload_error: Exception | None = None


# Search only product terminology, never the value of a preference or editor.
_SEARCH_ALIASES = {
    "page:Help & diagnostics": "help diagnostics troubleshoot recovery backup defaults keyboard shortcuts",
    "page:Voice commands": "reference spoken commands punctuation editing",
    "hotkey": "keyboard shortcut keys",
    "mode": "activation hold toggle push talk start stop",
    "microphone": "microphone mic audio input device",
    "output_format": "output style prose markdown formatting",
    "speech_end_enabled": "automatic stop silence pause detection",
    "speech_end_pause_seconds": "automatic stop silence duration delay",
    "speech_end_insert": "automatic insert review confirmation",
    "indicator": "tray floating indicator overlay pill feedback",
    "live_preview": "live preview draft words",
    "beep": "beep sound audio recording feedback",
    "start_at_login": "startup start login launch boot",
    "text_cleanup": "cleanup clean raw transcript verbatim",
    "names": "personal vocabulary dictionary names replacement spelling",
    "remove_fillers": "filler words um uh",
    "fix_corrections": "correction spoken undo",
    "model": "speech recognition model offline",
    "language": "language multilingual english",
    "device": "processing hardware cpu gpu npu acceleration",
    "denoise": "audio noise reduction processing",
    "allow_network": "privacy network internet downloads offline",
    "restore_clipboard": "privacy clipboard text handling restore",
}


class SettingsWindow:
    def __init__(self, root: tk.Tk, cfg: Config, *, background: bool = True):
        self.root, self.cfg = root, cfg
        self.events: queue.Queue = queue.Queue()
        self.closed = False
        self._page_reset = None
        self.saving = False
        self._save_operation = None
        self._save_details = ""
        self.checking_connection = False
        self._connection_operation = None
        self.refreshing_mics = False
        self.checking_mic = False
        self.error_details = {}
        self.model_downloading = False
        self._model_download_operation = None
        self.model_download_cancel = threading.Event()
        self._reset_pending = False
        self._resetting_feedback = False
        self.mic_stop = threading.Event()
        self.pages: dict[str, ttk.Frame] = {}
        self.nav: dict[str, ttk.Button] = {}
        self.mascots = {}
        self.mascot_labels = {}
        self._mascot_heading_labels = set()
        self._column_labels = set()
        self.appearance_guide = None
        self.obs_pairing_dialog = None
        self.report = ""
        self._report_operation = None
        self._exporting_report = False
        self.vars = {}
        self.fields = {}
        self.search_targets: dict[str, _SearchTarget] = {}
        self._search_pages = {}
        self._search_sections = {}
        self.search_matches = []
        self.search_open = False
        self._search_previous_focus = None
        self.search_query = tk.StringVar(root)
        self.search_status = tk.StringVar(root)
        self.search_detail = tk.StringVar(root)
        for key in ("hotkey", "mode", "model", "device", "language", "denoise", "microphone",
                    "beep", "indicator", "live_preview", "remove_fillers", "fix_corrections",
                    "restore_clipboard", "allow_network", "text_cleanup", "output_format",
                    "speech_end_enabled", "speech_end_pause_seconds", "speech_end_insert"):
            value = getattr(cfg, key)
            cls = tk.BooleanVar if isinstance(value, bool) else tk.StringVar
            self.vars[key] = cls(root, value=value)
        self.vars["microphone"].set(cfg.microphone or SYSTEM_DEFAULT)
        self.vars["start_at_login"] = tk.BooleanVar(root, value=startup_enabled())
        self.status = tk.StringVar(root, value="Your voice. Your device.")
        self.connection = tk.StringVar(root, value="Checking app…" if background else "App status unavailable")
        self.model_summary = tk.StringVar(root)
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
        wordmark_label = tk.Label(sidebar, image=self.wordmark, bg=theme.SURFACE_LOW,
                                  takefocus=False)
        wordmark_label.pack(anchor="w", padx=18, pady=(20, 22))
        for name in ("Dictation", "Vocabulary", "Voice commands", "Engine", "Help & diagnostics"):
            label = {"Engine": "Speech & privacy", "Help & diagnostics": "Help"}.get(name, name)
            button = ttk.Button(sidebar, text=label, style="Nav.TButton", padding=(16, 8),
                                command=lambda n=name: self.show_page(n))
            button.pack(fill="x", padx=12, pady=3)
            self.nav[name] = button
        self.privacy_label = tk.Label(sidebar, text="Local dictation.\nNo account.", justify="left",
                 font=(ui_font(), 9), fg=theme.ON_VARIANT, bg=theme.SURFACE_LOW,
                 wraplength=150)
        self.privacy_label.pack(side="bottom", anchor="w", padx=24, pady=12)
        def wrap_privacy(event):
            width = max(1, event.width - 52)
            if int(self.privacy_label.cget("wraplength")) != width:
                self.privacy_label.configure(wraplength=width)
            # Keep navigation intact at large text sizes. This optional tagline
            # must fit in full; privacy controls and disclosures remain on-page.
            required = (wordmark_label.winfo_reqheight() + 42
                        + sum(button.winfo_reqheight() + 6 for button in self.nav.values())
                        + self.privacy_label.winfo_reqheight() + 24)
            if event.height >= required:
                if not self.privacy_label.winfo_manager():
                    self.privacy_label.pack(side="bottom", anchor="w", padx=24, pady=12)
            elif self.privacy_label.winfo_manager():
                self.privacy_label.pack_forget()
        sidebar.bind("<Configure>", wrap_privacy)

        content = ttk.Frame(root)
        content.grid(row=0, column=1, sticky="nsew")
        content.columnconfigure(0, weight=1)
        content.rowconfigure(1, weight=1)
        search_toolbar = ttk.Frame(content, style="Page.TFrame", padding=(26, 8, 26, 0))
        self._search_toolbar = search_toolbar
        search_toolbar.grid(row=0, column=0, columnspan=2, sticky="ew")
        self.search_button = ttk.Button(search_toolbar, text="Find setting…", command=self.open_search)
        self.search_button.pack(anchor="e")
        self.canvas = tk.Canvas(content, bg=theme.SURFACE_LOW, highlightthickness=0)
        self.canvas.grid(row=1, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(content, orient="vertical", command=self.canvas.yview)
        scroll.grid(row=1, column=1, sticky="ns")
        self._content_scroll = scroll
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
        # Toplevel bindings run after Text's native cursor movement, including
        # held-key repeats. Widget KeyRelease remains a fallback for consumed keys.
        root.bind("<KeyPress>", self._reveal_text_cursor, add="+")
        for key, movement in (("Prior", "up"), ("Next", "down"),
                              ("Home", "top"), ("End", "bottom")):
            root.bind(f"<{key}>", lambda event, move=movement: self._scroll_page(event, move), add="+")

        self._dictation()
        self._vocabulary()
        self._commands()
        self._engine()
        self._help()
        self._build_search(content)
        footer = ttk.Frame(root, padding=(20, 14))
        footer.grid(row=1, column=0, columnspan=2, sticky="ew")
        footer.columnconfigure(0, weight=1)
        self.footer_status = ttk.Label(footer, textvariable=self.status, style="Hint.TLabel", wraplength=350)
        self.footer_status.grid(row=0, column=0, sticky="w")
        self.close_button = ttk.Button(footer, text="Close", command=self.close)
        self.close_button.grid(row=0, column=1, padx=10)
        self.save_button = ttk.Button(footer, text="Save changes", style="Primary.TButton", command=self.save)
        self.save_button.grid(row=0, column=2)
        self.save_details_button = ttk.Button(footer, text="Save details…", command=self.show_save_details)
        self.save_details_button.grid(row=1, column=0, columnspan=3, sticky="w", pady=(8, 0))
        self.save_details_button.grid_remove()
        footer.bind("<Configure>", self._resize_footer)
        self.baseline = self._snapshot()
        for var in self.vars.values():
            var.trace_add("write", self._dirty)
        for key in ("model", "language", "device"):
            self.vars[key].trace_add("write", self.refresh_model_status)
        self.vars["microphone"].trace_add("write", self._microphone_changed)
        self.refresh_model_status()
        self.names.bind("<<Modified>>", self._names_changed)
        self.names.edit_modified(False)
        root.bind("<Control-s>", lambda _e: self.save())
        root.bind("<Command-s>", lambda _e: self.save())
        root.bind("<Escape>", lambda _e: self.close())
        navigation_modifier = "Command" if sys.platform == "darwin" else "Alt"
        for index, name in enumerate(self.nav, start=1):
            root.bind(f"<{navigation_modifier}-Key-{index}>",
                      lambda _e, page=name: self.navigate(page))
        root.bind("<F1>", lambda _e: self.navigate("Help & diagnostics"))
        # A per-window tag runs before native editor bindings. A toplevel-only
        # Ctrl+F handler would first move Text's caret on some Tk platforms.
        self._search_bindtag = f"UtterleafSearch:{root}"
        self._search_shortcut = "<Command-f>" if sys.platform == "darwin" else "<Control-f>"
        root.bind_class(self._search_bindtag, self._search_shortcut, self.open_search)
        root.bind_class(self._search_bindtag, "<Escape>", self._search_escape)
        def search_bindings(widget):
            widget.bindtags((self._search_bindtag, *widget.bindtags()))
            for child in widget.winfo_children():
                search_bindings(child)
        search_bindings(root)
        root.protocol("WM_DELETE_WINDOW", self.close)
        self.show_page("Dictation")
        self._dirty()
        if background:
            self.refresh_mics()
            self.refresh_connection()
        self.poll_id = root.after(80, self._poll)

    def _register_search(self, key, label, widget, *, page=None, section="", terms=""):
        owner = widget
        while page is None and owner is not None:
            if not section:
                section = self._search_sections.get(owner, "")
            if owner in self._search_pages:
                page = self._search_pages[owner][0]
                break
            owner = owner.master
        if page is None:
            raise ValueError("A search target must belong to a Settings page")
        page_label = str(self.nav[page].cget("text"))
        words = " ".join((label, page_label, section, terms, _SEARCH_ALIASES.get(key, "")))
        self.search_targets[key] = _SearchTarget(
            key, label, page, page_label, section, widget, words.casefold(),
        )

    def _build_search(self, content):
        self.search_panel = ttk.Frame(content, style="Page.TFrame", padding=(26, 12, 26, 16))
        panel = self.search_panel
        panel.columnconfigure(0, weight=1)
        panel.rowconfigure(3, weight=1)
        ttk.Label(panel, text="Find a setting", style="Section.TLabel").grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 6))
        self.search_entry = ttk.Entry(panel, textvariable=self.search_query, width=12,
                                      exportselection=False)
        self.search_entry.grid(row=1, column=0, sticky="ew")
        self.search_close_button = ttk.Button(panel, text="Back", command=self.close_search)
        self.search_close_button.grid(row=1, column=1, padx=(10, 0))

        def wrapped(variable, row):
            label = ttk.Label(panel, textvariable=variable, style="Hint.TLabel",
                              width=1, wraplength=1, justify="left")
            label.grid(row=row, column=0, columnspan=2, sticky="ew", pady=6)
            label.bind("<Configure>", lambda event: label.configure(
                wraplength=max(1, event.width - 4)))
            return label

        self.search_status_label = wrapped(self.search_status, 2)
        results = ttk.Frame(panel)
        results.grid(row=3, column=0, columnspan=2, sticky="nsew")
        results.columnconfigure(0, weight=1)
        results.rowconfigure(0, weight=1)
        self.search_results = tk.Listbox(
            results, width=1, height=3, font=(ui_font(), 11), exportselection=False,
            bg=theme.SURFACE_LOW, fg=theme.ON_SURFACE,
            selectbackground=theme.PRIMARY_CONTAINER, selectforeground=theme.ON_PRIMARY_CONTAINER,
            highlightcolor=theme.PRIMARY, highlightbackground=theme.OUTLINE_VARIANT,
            highlightthickness=1, relief="flat", activestyle="dotbox",
        )
        self.search_results.grid(row=0, column=0, sticky="nsew")
        vertical = ttk.Scrollbar(results, command=self.search_results.yview)
        vertical.grid(row=0, column=1, sticky="ns")
        horizontal = ttk.Scrollbar(results, orient="horizontal", command=self.search_results.xview)
        horizontal.grid(row=1, column=0, columnspan=2, sticky="ew")
        self.search_results.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        self.search_detail_label = wrapped(self.search_detail, 4)
        self.search_open_button = ttk.Button(panel, text="Open setting", state="disabled",
                                              command=self._activate_search_result)
        self.search_open_button.grid(row=5, column=0, columnspan=2, sticky="e", pady=(4, 0))
        self.search_results.bind("<<ListboxSelect>>", self._search_selection)
        self.search_results.bind("<Return>", self._activate_search_result)
        self.search_results.bind("<Double-Button-1>", self._activate_search_result)
        self.search_entry.bind("<Return>", self._activate_search_result)
        self.search_entry.bind("<Down>", lambda _e: self._enter_search_results(False))
        self.search_entry.bind("<Up>", lambda _e: self._enter_search_results(True))
        self.search_query.trace_add("write", self._update_search)
        self._update_search()

    def open_search(self, event=None):
        if self.closed or (event is not None and event.widget.winfo_toplevel() != self.root):
            return
        if not self.search_open:
            self._search_previous_focus = self.root.focus_get()
            self.search_open = True
            self._search_toolbar.grid_remove()
            self.canvas.grid_remove()
            self._content_scroll.grid_remove()
            self.search_panel.grid(row=1, column=0, columnspan=2, sticky="nsew")
        self.search_entry.focus_set()
        self.search_entry.selection_range(0, "end")
        return "break"

    def close_search(self, event=None, *, restore_focus=True):
        if self.closed or not self.search_open:
            return "break"
        self.search_open = False
        self.search_panel.grid_remove()
        self._search_toolbar.grid()
        self.canvas.grid()
        self._content_scroll.grid()
        self.search_query.set("")
        previous, self._search_previous_focus = self._search_previous_focus, None
        if restore_focus:
            self.root.update_idletasks()
            # Embedded canvas descendants remap after this callback returns.
            # Their temporary unmapped state must not discard the editor focus.
            if (previous is None or not previous.winfo_exists()
                    or previous.winfo_toplevel() != self.root
                    or ("state" in previous.keys() and str(previous.cget("state")) == "disabled")):
                previous = self.nav[self._current_page]
            previous.focus_set()
        return "break"

    def _search_escape(self, event):
        if self.search_open and event.widget.winfo_toplevel() == self.root:
            return self.close_search()

    def _update_search(self, *_):
        if self.closed:
            return
        tokens = self.search_query.get()[:256].casefold().split()
        self.search_matches = [target for target in self.search_targets.values()
                               if tokens and all(token in target.terms for token in tokens)]
        self.search_results.delete(0, "end")
        for target in self.search_matches:
            self.search_results.insert("end", target.label)
        if self.search_matches:
            self.search_results.selection_set(0)
            self.search_results.activate(0)
            count = len(self.search_matches)
            self.search_status.set(f"{count} result" + ("s" if count != 1 else ""))
        else:
            self.search_status.set("Type a setting name, such as microphone or privacy." if not tokens
                                   else "No matching settings. Try a shorter term.")
        self._search_selection()

    def _search_destination(self, target):
        widget = target.widget
        if str(widget.cget("state")) != "disabled":
            return widget, ""
        if target.key in {"speech_end_pause_seconds", "speech_end_insert"}:
            return self.speech_end_toggle, "Enable Stop after speech first."
        if target.key == "live_preview":
            return self.indicator_toggle, "Enable the floating indicator first."
        if target.key in {"hotkey", "mode"} and is_wayland():
            return self.nav[target.page], "Set this shortcut in your desktop settings on Wayland."
        if target.key == "microphone" and self.checking_mic:
            return self.mic_button, "Finish the microphone check first."
        return self.nav[target.page], "This setting is temporarily unavailable. Finish the current operation first."

    def _search_selection(self, _event=None):
        selected = self.search_results.curselection()
        if not selected or selected[0] >= len(self.search_matches):
            self.search_detail.set("")
            self.search_open_button.configure(state="disabled")
            return
        target = self.search_matches[selected[0]]
        _, hint = self._search_destination(target)
        location = target.page_label + (f" · {target.section}" if target.section else "")
        self.search_detail.set(f"{target.label}\n{location}" + (f"\n{hint}" if hint else ""))
        self.search_open_button.configure(state="normal")

    def _enter_search_results(self, last):
        if self.search_matches:
            index = len(self.search_matches) - 1 if last else 0
            self.search_results.selection_clear(0, "end")
            self.search_results.selection_set(index)
            self.search_results.activate(index)
            self.search_results.see(index)
            self.search_results.focus_set()
            self._search_selection()
        return "break"

    def _activate_search_result(self, _event=None):
        selected = self.search_results.curselection()
        if self.closed or not self.search_open or not selected or selected[0] >= len(self.search_matches):
            return "break"
        target = self.search_matches[selected[0]]
        self.close_search(restore_focus=False)
        self.show_page(target.page)
        if self._page_reset is not None:
            self.root.after_cancel(self._page_reset)
            self._page_reset = None
        self.root.update_idletasks()
        widget, hint = self._search_destination(target)
        widget.focus_set()
        self._reveal_focus(SimpleNamespace(widget=widget))
        if hint:
            self.status.set(hint)
        return "break"

    def _page(self, name, eyebrow, title, subtitle):
        frame = ttk.Frame(self.body, style="Page.TFrame")
        self.pages[name] = frame
        self._search_pages[frame] = (name, title)
        self._register_search(f"page:{name}", title, self.nav[name], page=name,
                              section="Page", terms=subtitle)
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
        self._search_sections[panel] = title
        panel.pack(fill="x")
        ttk.Label(panel, text=title, style="Section.TLabel").pack(anchor="w", pady=(0, 6))
        if hint:
            ttk.Label(panel, text=hint, style="Hint.TLabel", wraplength=520).pack(anchor="w", pady=(0, 8))
        return panel

    def _details_button(self, parent, title):
        button = ttk.Button(parent, text="Details…", state="disabled")
        self.error_details[button] = ""

        def show():
            details = self.error_details[button]
            if not self.closed and details:
                messagebox.showinfo(title,
                    "Technical details may include device names or local paths. Review before sharing.\n\n"
                    + details, parent=self.root)

        button.configure(command=show)
        return button

    def _set_error_details(self, button, error=None):
        # Keep only bounded plain text, not an exception/traceback or a log file.
        raw = "" if error is None else f"{type(error).__name__}: {error}"
        text = "".join(char for char in raw[:2000] if char.isprintable() or char in "\n\t")
        if len(raw) > 2000:
            text += "\n[Details shortened]"
        self.error_details[button] = text
        button.configure(state="normal" if text else "disabled")
        if text:
            button.pack(anchor="w", pady=(6, 0))
        else:
            button.pack_forget()

    def _choice(self, parent, label, key, values, *, editable=False, labels=None):
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=6)
        row.columnconfigure(1, weight=1)
        caption = ttk.Label(row, text=label, width=17)
        caption.grid(row=0, column=0, sticky="w", padx=(0, 10))
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
        stacked = None

        def arrange(event):
            nonlocal stacked
            narrow = event.width < caption.winfo_reqwidth() + box.winfo_reqwidth() + 10
            if event.width <= 1 or narrow == stacked:
                return
            stacked = narrow
            caption.grid_configure(columnspan=2 if narrow else 1,
                                   padx=0 if narrow else (0, 10),
                                   pady=(0, 4) if narrow else 0)
            box.grid_configure(row=1 if narrow else 0, column=0 if narrow else 1,
                               columnspan=2 if narrow else 1)

        row.bind("<Configure>", arrange)
        self.fields[key] = box
        self._register_search(key, label, box)
        return box

    def _compact_choice(self, parent, label, key, values, *, editable=False):
        """A stacked choice for the compact, two-column Dictation overview."""
        ttk.Label(parent, text=label).pack(anchor="w", pady=(2, 4))
        box = ttk.Combobox(
            parent,
            textvariable=self.vars[key],
            values=list(values), width=12,
            state="normal" if editable else "readonly",
        )
        box.pack(fill="x", pady=(0, 4))
        self.fields[key] = box
        self._register_search(key, label, box)
        return box

    def _column_hint(self, parent, text="", *, textvariable=None):
        # Hint text takes the width assigned by its controls. Its wrapped text
        # must not request a new column width and feed back into Configure.
        label = ttk.Label(parent, text=text, textvariable=textvariable,
                          style="Hint.TLabel", width=1, wraplength=180, justify="left")
        label.pack(fill="x", pady=(2, 0))
        self._column_labels.add(label)
        def wrap_hint(event):
            # Leave room for the label's border inside the allocated width.
            width = max(1, event.width - 4)
            if event.width > 1 and int(label.cget("wraplength")) != width:
                label.configure(wraplength=width)
        label.bind("<Configure>", wrap_hint)
        return label

    def _check(self, parent, title, key, hint=""):
        button = ttk.Checkbutton(parent, text=title, variable=self.vars[key])
        button.pack(anchor="w", pady=(8, 2))
        self._register_search(key, title, button, terms=hint)
        if hint:
            label = self._column_hint(parent, hint)
            label.pack_configure(padx=(24, 0), pady=(0, 4))
        return button

    def _text(self, parent, height=6):
        box = tk.Text(parent, height=height, wrap="word", undo=True, relief="flat", takefocus=True,
                      bg=theme.SURFACE_LOW, fg=theme.ON_SURFACE, insertbackground=theme.PRIMARY,
                      highlightthickness=1, highlightbackground=theme.OUTLINE_VARIANT,
                      highlightcolor=theme.PRIMARY, padx=14, pady=12, font=(ui_font(), 11), width=30)
        box.pack(fill="x", pady=(6, 10))
        # Tab advances through the form; Return is always safe inside an editor.
        box.bind("<Tab>", lambda e: (e.widget.tk_focusNext().focus_set(), "break")[-1])
        box.bind("<Shift-Tab>", lambda e: (e.widget.tk_focusPrev().focus_set(), "break")[-1])
        box.bind("<KeyRelease>", self._reveal_text_cursor, add="+")
        box.bind("<ButtonRelease-1>", self._reveal_text_cursor, add="+")
        return box

    def _dictation(self):
        page = self._page("Dictation", "Settings", "Dictation", "")
        summary = ttk.Frame(page, style="Page.TFrame")
        summary.pack(fill="x", pady=(0, 12))
        summary.columnconfigure(0, weight=1)
        summary_rows = []
        for row, title, variable, label, action in (
            (0, "App · applied settings · last check", self.connection, "Refresh status", self.refresh_connection),
            (1, "Selected speech model · draft / local files", self.model_summary, "Manage model…",
             lambda: self.navigate("Engine")),
        ):
            words = ttk.Frame(summary, style="Page.TFrame")
            words.grid(row=row, column=0, sticky="ew", padx=(0, 12), pady=(0, 8))
            heading = self._column_hint(words, title)
            heading.configure(style="Page.TLabel")
            detail = self._column_hint(words, textvariable=variable)
            detail.configure(style="Subtitle.TLabel")
            button = ttk.Button(summary, text=label, command=action)
            button.grid(row=row, column=1, sticky="e", pady=(0, 8))
            summary_rows.append((words, button))
            if row == 0:
                self.connection_button = button
            else:
                self.model_manage_button = button
        summary_stacked = None

        def arrange_summary(event):
            nonlocal summary_stacked
            # Keep a readable text column; larger text uses a full-width row.
            minimum_text = round(260 * self.root.winfo_fpixels("1i") / 96)
            narrow = event.width < minimum_text + max(button.winfo_reqwidth()
                                                     for _, button in summary_rows) + 12
            if event.width <= 1 or narrow == summary_stacked:
                return
            summary_stacked = narrow
            for row, (words, button) in enumerate(summary_rows):
                words.grid_configure(row=row * 2 if narrow else row, column=0,
                                     columnspan=2 if narrow else 1,
                                     padx=0 if narrow else (0, 12))
                button.grid_configure(row=row * 2 + 1 if narrow else row,
                                      column=0 if narrow else 1, sticky="w" if narrow else "e",
                                      pady=(0, 12) if narrow else (0, 8))

        summary.bind("<Configure>", arrange_summary)
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

        overview = ttk.Frame(page, style="Page.TFrame")
        overview.pack(fill="x")
        self.dictation_overview = overview
        shortcut = ttk.Frame(overview, style="Page.TFrame")
        microphone = ttk.Frame(overview, style="Page.TFrame")

        p = self._section(shortcut, "Shortcut")
        p.configure(padding=12)
        self.hotkey_box = self._compact_choice(
            p, "Keyboard shortcut", "hotkey",
            [v for _, v in hotkey_presets() if v], editable=True,
        )
        mode_state = "disabled" if is_wayland() else "normal"
        self.hold_mode = ttk.Radiobutton(
            p, text="Hold to talk", variable=self.vars["mode"],
            value="hold", state=mode_state,
        )
        self.hold_mode.pack(anchor="w", pady=(6, 2))
        self.toggle_mode = ttk.Radiobutton(
            p, text="Press to start / stop", variable=self.vars["mode"],
            value="toggle", state=mode_state,
        )
        self.toggle_mode.pack(anchor="w", pady=2)
        self._register_search("mode", "Hold to talk / press to start or stop", self.hold_mode)
        if is_wayland():
            self.hotkey_box.configure(state="disabled")
            self._column_hint(p, "Set a desktop keyboard shortcut to the executable path followed by --toggle.")

        p = self._section(microphone, "Microphone")
        p.configure(padding=12)
        self.mic_box = self._compact_choice(p, "Input device", "microphone", [SYSTEM_DEFAULT])
        actions = ttk.Frame(p)
        actions.pack(fill="x", pady=(6, 4))
        self.mic_button = ttk.Button(actions, text="Test", width=5, command=self.test_mic)
        self.mic_button.pack(side="left")
        self.refresh_button = ttk.Button(actions, text="Refresh", width=7, command=self.refresh_mics)
        self.refresh_button.pack(side="left", padx=(6, 0))
        self.mic_message = tk.StringVar(self.root, value="Five-second check. Audio is discarded.")
        self.meter = ttk.Progressbar(p, maximum=100)
        self.meter.pack(fill="x", pady=(4, 4))
        self._column_hint(p, textvariable=self.mic_message)
        self.mic_details_button = self._details_button(p, "Microphone check details")

        column_state = None

        def arrange_columns(event):
            nonlocal column_state
            # Use the controls' requested width, not an assumed DPI percentage.
            column_min = max(self.toggle_mode.winfo_reqwidth(), actions.winfo_reqwidth()) + 28
            two_columns = event.width >= 2 * column_min + 14
            if two_columns == column_state:
                return
            column_state = two_columns
            overview.columnconfigure(0, weight=1, uniform="dictation" if two_columns else "")
            overview.columnconfigure(1, weight=1 if two_columns else 0,
                                     uniform="dictation" if two_columns else "")
            shortcut.grid(row=0, column=0, sticky="nsew", padx=(0, 7) if two_columns else 0)
            microphone.grid(row=0 if two_columns else 1, column=1 if two_columns else 0,
                            sticky="nsew", padx=(7, 0) if two_columns else 0)

        overview.bind("<Configure>", arrange_columns)
        shortcut.grid(row=0, column=0, sticky="nsew")
        microphone.grid(row=0, column=1, sticky="nsew")

        output = ttk.Frame(page, padding=(12, 4))
        output.pack(fill="x", pady=(0, 4))
        ttk.Label(output, text="Output style").pack(anchor="w")
        output_modes = ttk.Frame(output)
        output_modes.pack(anchor="w", pady=(4, 0))
        self.output_format_control = ttk.Radiobutton(
            output_modes, text="Prose", variable=self.vars["output_format"], value="prose"
        )
        self.output_format_control.pack(side="left", padx=(0, 18))
        self.markdown_control = ttk.Radiobutton(
            output_modes, text="Markdown", variable=self.vars["output_format"], value="markdown"
        )
        self.markdown_control.pack(side="left")
        self.fields["output_format"] = self.output_format_control
        self._register_search("output_format", "Output style", self.output_format_control, section="Output style")

        p = self._section(page, "Stop after speech")
        self.speech_end_toggle = self._check(
            p, "Stop after speech and a pause", "speech_end_enabled",
            "Only during a take you start. It never opens the microphone or starts another take. "
            "Manual stop and Esc remain available. Quiet speech, noise, and thinking pauses can affect detection.",
        )
        self.speech_end_pause = self._choice(p, "Pause (seconds)", "speech_end_pause_seconds", ["0.5", "0.8", "1.2", "1.8", "2.5", "3.0"])
        self.speech_end_insert_toggle = self._check(
            p, "Insert immediately after automatic stop", "speech_end_insert",
            "Off by default. When off, or when the original field cannot be verified, a review window lets you copy, insert, or discard the text.",
        )
        ttk.Label(p, text="Uses only the reviewed detector bundled with an installed local speech engine. If it is unavailable, recording continues until you stop it manually.",
                  style="Hint.TLabel", wraplength=510).pack(anchor="w", pady=(2, 6))

        p = self._section(page, "Recording feedback", "Keep things quiet, or add guidance while you speak.")
        self.limit_hint = tk.StringVar(self.root)
        ttk.Label(p, textvariable=self.limit_hint, style="Hint.TLabel", wraplength=510).pack(fill="x", pady=(0, 6))
        tray_only = ttk.Radiobutton(p, text="Tray icon only", variable=self.vars["indicator"], value=False)
        tray_only.pack(anchor="w", pady=4)
        self.indicator_toggle = ttk.Radiobutton(p, text="Tray + floating indicator", variable=self.vars["indicator"], value=True)
        self.indicator_toggle.pack(anchor="w", pady=4)
        self._register_search("indicator", "Tray + floating indicator", self.indicator_toggle,
                              terms=str(tray_only.cget("text")))
        ttk.Label(p, text="The floating indicator shows recording state and guidance.",
                  style="Hint.TLabel", wraplength=510).pack(anchor="w", pady=(0, 4))
        self.preview_toggle = self._check(p, "Preview dictation while recording", "live_preview",
                                         "Optional draft words while you speak. Uses additional processing power.")
        self._check(p, "Play start / stop sounds", "beep")
        self.feedback_reset_button = ttk.Button(
            p, text="Reset Recording feedback…", command=self.reset_recording_feedback)
        self.feedback_reset_button.pack(anchor="w", pady=(8, 0))
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
        self._register_search("names", "Personal vocabulary", self.names)
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
                       "Choose the speech model and privacy settings used for local dictation.")
        p = self._section(page, "Model & installation",
                      "Choose a model and language, then check its local installation. "
                      "Save changes applies your selection; downloading does not save other edits.")
        self._choice(p, "Model", "model", ["tiny", "base", "small", "medium", "large-v3", "distil-small.en"], editable=True)
        self._choice(p, "Language", "language", ["en", "auto", "es", "fr", "de", "it", "pt", "ja", "zh"], editable=True)
        ttk.Label(p, text="Use auto to detect the language, or enter a language code. English-only models require English.",
                  style="Hint.TLabel", wraplength=520).pack(anchor="w", pady=8)
        self.model_status = tk.StringVar(self.root)
        ttk.Label(p, textvariable=self.model_status, wraplength=520).pack(anchor="w", pady=(8, 4))
        self.model_action_status = tk.StringVar(self.root)
        ttk.Label(p, textvariable=self.model_action_status, style="Hint.TLabel", wraplength=520).pack(anchor="w", pady=4)
        actions = ttk.Frame(p)
        actions.pack(fill="x", pady=(6, 8))
        self.model_download_button = ttk.Button(actions, text="Download selected model…", command=self.download_model)
        self.model_download_button.grid(row=0, column=0, sticky="w")
        self.model_cancel_button = ttk.Button(actions, text="Cancel download", command=self.cancel_model_download, state="disabled")
        self.model_cancel_button.grid(row=0, column=1, sticky="w", padx=(8, 0))
        stacked = None

        def arrange_actions(event):
            nonlocal stacked
            narrow = event.width < (self.model_download_button.winfo_reqwidth()
                                    + self.model_cancel_button.winfo_reqwidth() + 8)
            if event.width <= 1 or narrow == stacked:
                return
            stacked = narrow
            self.model_cancel_button.grid_configure(row=1 if narrow else 0,
                column=0 if narrow else 1, padx=0 if narrow else (8, 0),
                pady=(8, 0) if narrow else 0)

        actions.bind("<Configure>", arrange_actions)
        ttk.Button(p, text="Refresh model status", command=self.refresh_model_status).pack(anchor="w")
        self.model_info_button = ttk.Button(p, text="Model details…", command=self.show_model_details)
        self.model_info_button.pack(anchor="w", pady=(6, 0))
        self.model_details_button = self._details_button(p, "Model download details")
        self.model_details_button.configure(text="Download error details…")
        p = self._section(page, "Processing", "Device selection changes how speech is processed; it does not install hardware support.")
        self._choice(p, "Processing device", "device", [], labels={"auto": "Automatic", "cpu": "CPU", "gpu": "NVIDIA GPU", "npu": "NPU"})
        ttk.Label(p, text="Automatic selects available acceleration and may need a separate NPU model. "
                  "Choose CPU for the most portable setup and file transcription. Check hardware support under Help.",
                  style="Hint.TLabel", wraplength=520).pack(anchor="w", pady=8)
        self._choice(p, "Noise reduction", "denoise", [], labels={"auto": "Automatic", "on": "On", "off": "Off"})
        p = self._section(page, "Local model files", "Browse guided installations without loading a speech model.")
        from utterleaf.model_inventory_ui import ModelInventoryPanel
        self.model_inventory = ModelInventoryPanel(p, worker=lambda work, done: self._worker(work, done),
            selection_reason=self._inventory_selection_reason, select_model=self._use_inventory_model,
            is_closed=lambda: self.closed)
        self.model_inventory.pack(fill="x")
        p = self._section(page, "Privacy & clipboard", "Your microphone is released after each take. Audio is processed on this device "
                      "and is not saved to a recording history. The latest output has a two-minute recovery slot in memory. "
                      "Use Forget last dictation in the tray menu to clear it sooner. No account is required.")
        self._check(p, "Allow missing model downloads", "allow_network",
                    "Off by default. Install with Download selected model, or turn this on to fetch a missing selection automatically.")
        self._check(p, "Restore my clipboard after pasting", "restore_clipboard")
        if sys.platform == "win32":
            p = self._section(page, "OBS pairing", "Manage the private pairing saved for this Windows user. Live OBS transcription is still in development.")
            ttk.Button(p, text="Manage OBS pairing…", command=self.show_obs_pairing).pack(anchor="w")

    def show_obs_pairing(self):
        if sys.platform != "win32" or self.closed:
            return
        if self.obs_pairing_dialog is not None and not self.obs_pairing_dialog.closed:
            self.obs_pairing_dialog.root.lift()
            self.obs_pairing_dialog.close_button.focus_set()
            return
        from utterleaf.obs_pairing_ui import ObsPairingDialog
        self.obs_pairing_dialog = ObsPairingDialog(self.root)

    def _selected_model(self):
        from dataclasses import replace
        from utterleaf.model_setup import model_name
        cfg = replace(self.cfg, model=self.vars["model"].get(), language=self.vars["language"].get())
        return model_name(cfg), "openvino" if self.vars["device"].get() == "npu" else "ctranslate2"

    def _inventory_selection_reason(self, entry):
        """Never change language or hardware implicitly to match a local row."""
        from dataclasses import replace
        from utterleaf.model_setup import model_name
        if self.closed:
            return "Settings is closing."
        if entry.state not in {"installed", "incomplete"}:
            return "Refresh local list to check these files before choosing this model."
        device, language = self.vars["device"].get(), self.vars["language"].get()
        if device not in {"auto", "cpu", "gpu", "npu"}:
            return "Choose a listed Processing device first."
        if entry.backend == "openvino" and device != "npu":
            return "Choose NPU under Processing device to use this installation."
        if entry.backend == "ctranslate2" and device == "npu":
            return "Choose CPU, NVIDIA GPU or Automatic under Processing device to use this installation."
        if not language.strip() or language != language.strip():
            return "Enter a Language without leading or trailing spaces first."
        if entry.name.endswith(".en") and language.lower() not in {"en", "english", "auto"}:
            return "This model recognizes English only. Choose en or auto under Language first."
        cfg = replace(self.cfg, model=entry.name, language=language)
        if model_name(cfg) != entry.name:
            return "Language is set to English, which selects the English-only model. Choose auto or another language to use this multilingual installation."
        return None

    def _use_inventory_model(self, entry):
        if self._inventory_selection_reason(entry) is None:
            self.vars["model"].set(entry.name)

    def refresh_model_status(self, *_):
        from utterleaf.model_setup import inspect_model
        name, backend = self._selected_model()
        state = inspect_model(name, backend)
        self.model_availability = state
        messages = {"installed": "Installed — required files found locally. Loading has not been tested.",
                    "missing": "Missing — download this model before using it offline.",
                    "incomplete": "Incomplete — required files are missing or invalid. Download to finish setup.",
                    "unsupported": "Guided setup is unavailable for this model/device. Choose a listed model or CPU."}
        display = model_display_name(name)
        self.model_status.set(f"{display}\n{model_purpose(name)}\n{messages[state.state]}")
        summary = {"installed": "Installed files · loading not checked",
                   "missing": "Install needed", "incomplete": "Repair needed",
                   "unsupported": "Choose a supported model and device"}
        self.model_summary.set(f"{display} · {summary[state.state]}")
        self.model_download_button.configure(state="normal" if not self.model_downloading and state.state in {"missing", "incomplete"} else "disabled")
        self.model_inventory.preferences_changed()

    def show_model_details(self):
        """Describe the inspected draft without rescanning, loading, or saving."""
        if self.closed:
            return
        state = self.model_availability

        def plain(value, limit):
            raw = str(value)
            result = "".join(char for char in raw[:limit] if char.isprintable())
            return result + ("… [shortened]" if len(raw) > limit else "")

        folder = plain(state.path, 1000) if state.path is not None else "No managed location for this selection"
        missing = plain(", ".join(state.missing), 600) if state.missing else "None reported"
        messagebox.showinfo("Selected speech model details",
            "These details describe the last local file check for your current selection, which may be unsaved. "
            "Local paths may identify your account; review before sharing.\n\n"
            f"Model: {model_display_name(state.name)}\n"
            f"Identifier: {plain(state.name, 256) or '(empty)'}\n"
            f"Backend: {plain(state.backend, 80)}\n"
            f"File status: {plain(state.state, 80)}\n"
            f"Expected local folder: {folder}\n"
            f"Missing or invalid required files: {missing}\n\n"
            "This is a local file check, not a successful model load. "
            "Automatic processing may use a separate NPU installation.", parent=self.root)

    def _current_model_download(self, operation):
        if self.closed or self._model_download_operation is not operation:
            return False
        try:
            return bool(self.root.winfo_exists())
        except tk.TclError:
            return False

    def download_model(self):
        if self.model_downloading or self.closed or self._model_download_operation is not None:
            return
        from utterleaf.model_setup import inspect_model, run_download
        name, backend = self._selected_model()
        if inspect_model(name, backend).state not in {"missing", "incomplete"}:
            self.refresh_model_status()
            return
        engine = "NPU / OpenVINO" if backend == "openvino" else "CPU / NVIDIA"
        display = model_display_name(name)
        # Reserve before the native modal dialog, whose nested event loop can
        # deliver another invocation or close Settings before returning.
        operation = self._model_download_operation = object()
        try:
            confirmed = messagebox.askyesno("Download this speech model?",
                f"Download {display} for {engine} from Hugging Face now?\n\n"
                "This may use hundreds of MB or several GB of data and disk space. Only required missing or invalid files are fetched.\n\n"
                "This permits this download once. Your ongoing network preference and unsaved settings stay unchanged.", parent=self.root)
        except Exception as exc:
            if self._current_model_download(operation):
                self._model_download_operation = None
                self.model_action_status.set("Download confirmation could not open. No download was started. Try Download again.")
                self._set_error_details(self.model_details_button, exc)
            return
        if not self._current_model_download(operation):
            return
        if not confirmed:
            self._model_download_operation = None
            return
        self.model_downloading = True
        self._set_error_details(self.model_details_button)
        self.model_download_cancel = threading.Event()
        cancel = self.model_download_cancel
        self.model_action_status.set(f"Downloading {display}… Keep this window open; Cancel stops the download.")
        self.model_cancel_button.configure(state="normal")
        self.refresh_model_status()
        def done(result, *, started=True):
            if not self._current_model_download(operation):
                return
            self._model_download_operation = None
            self.model_downloading = False
            self.model_cancel_button.configure(state="disabled")
            self.refresh_model_status()
            # Successful completion is authoritative even if Cancel was clicked
            # after the worker returned but before this queued callback ran.
            if not started:
                self.model_action_status.set("Model download could not start. No download was started. Select Download selected model to retry.")
                self._set_error_details(self.model_details_button, result)
            elif result is None:
                self.model_action_status.set(f"{display} installed. Save changes to use a changed selection; reopen file transcription to reload its settings.")
            elif cancel.is_set():
                self.model_action_status.set("Download cancelled. Partial files are kept so you can retry.")
            else:
                self.model_action_status.set(
                    f"Download of {display} did not finish. This model may not be available offline. "
                    "Check your connection and free disk space, then retry the download.")
                self._set_error_details(self.model_details_button, result)
        # Keep the cancellation/reaping worker alive when closing the last Tk window.
        try:
            self._worker(lambda: run_download(name, backend, cancel=cancel), done, daemon=False)
        except Exception as exc:
            cancel.set()
            done(exc, started=False)

    def cancel_model_download(self):
        if self.closed or not self.model_downloading:
            return
        self.model_download_cancel.set()
        self.model_cancel_button.configure(state="disabled")
        self.model_action_status.set("Cancelling model download…")

    def _help(self):
        page = self._page("Help & diagnostics", "Support", "Help",
                         "Recover your words, check your setup, or start fresh.")
        p = self._section(page, "App status · last check")
        ttk.Label(p, textvariable=self.connection, wraplength=520).pack(anchor="w", pady=(0, 12))
        ttk.Label(p, text=settings_blurb(), style="Hint.TLabel", wraplength=520).pack(anchor="w", pady=(0, 14))
        p = self._section(page, "Quick checks", "No text? Click an editable text field before dictating.\n"
                      "Lost a result? Use Copy last dictation in the tray menu within two minutes.\n"
                      "No audio? Choose a microphone on the Dictation page and run a check.\n"
                      "First launch? Open Speech & privacy and choose Download selected model.")
        modifier = "Command" if sys.platform == "darwin" else "Alt"
        save_modifier = "Command" if sys.platform == "darwin" else "Ctrl"
        self._section(page, "Keyboard shortcuts",
                      f"{modifier}+1–5: open the five pages in sidebar order.\n"
                      f"{save_modifier}+S: save changes.  Esc: close, with a discard check.\n"
                      f"{save_modifier}+F: find a setting. Enter: open a search result. Esc: dismiss search first.\n"
                      "F1: Help.  Tab / Shift+Tab: move between controls.\n"
                      "Page Up/Down: scroll the page. Home/End: page top/bottom.\n"
                      "Use page scrolling from the sidebar or a button; text fields keep their editing keys.\n"
                      "These shortcuts apply only in Settings. Your dictation shortcut is set on Dictation.")
        p = self._section(page, "A fresh start", "Restore preferences without removing your vocabulary or models.")
        self.reset_button = ttk.Button(p, text="Restore defaults…", command=self.restore_defaults)
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
        self.report_status = tk.StringVar(self.root)
        self.report_feedback = RecoveryFeedback(p, self.report_status)
        # A pointer press must not scroll its own release target out of reach.
        self.report_feedback.details_button.bind(
            "<FocusIn>", lambda event: None if event.widget.instate(["pressed"])
            else self._reveal_report_feedback(), add="+")
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

    def navigate(self, name):
        """Window-local navigation leaves staged preferences untouched."""
        self.show_page(name)
        self.nav[name].focus_set()
        return "break"

    def show_page(self, name):
        if self.search_open:
            self.close_search(restore_focus=False)
        self._current_page = name
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
        scale = self.root.winfo_fpixels("1i") / 96
        width = min(event.width, round(MAX_PAGE_WIDTH * scale))
        self.canvas.itemconfigure(self.window_id, width=width)
        self.canvas.coords(self.window_id, max(0, (event.width - width) // 2), 0)
        # Wrap copy to the actual content width, including high-DPI displays.
        def wrap(widget):
            for child in widget.winfo_children():
                if (isinstance(child, (ttk.Label, tk.Label))
                        and int(child.cget("wraplength") or 0) and child not in self._column_labels):
                    inset = 140 if child.master is self.shortcut_card else 104
                    if child in self._mascot_heading_labels:
                        inset += 92
                    child.configure(wraplength=max(180, width - inset))
                wrap(child)
        wrap(self.body)

    def _resize_footer(self, event):
        available = event.width - self.close_button.winfo_reqwidth() - self.save_button.winfo_reqwidth() - 68
        self.footer_status.configure(wraplength=max(120, min(450, available)))

    @staticmethod
    def _is_focus_control(widget):
        """Ignore FocusIn propagation through frames and other containers."""
        if isinstance(widget, (tk.Entry, tk.Text, ttk.Combobox, ttk.Entry)):
            return True
        return widget.winfo_class() in {
            "Button", "TButton", "TCheckbutton", "TRadiobutton", "TScale", "TSpinbox",
        }

    def _wheel(self, event, direction=None):
        if self.search_open or isinstance(event.widget, (tk.Text, ttk.Combobox, tk.Listbox)):
            return
        if self.canvas.bbox("all")[3] <= self.canvas.winfo_height():
            return
        direction = direction if direction is not None else (-1 if event.delta > 0 else 1)
        self.canvas.yview_scroll(direction * 3, "units")

    def _scroll_page(self, event, movement):
        """Read long pages without taking native keys from editors or pickers."""
        if self.closed or self.search_open or event.widget.winfo_toplevel() != self.root:
            return
        # These specific bindings take precedence over the generic KeyPress one.
        self._reveal_text_cursor(event)
        # Lock keys are not shortcuts. On Aqua, Mod2 is Option, not Num Lock.
        lock_mask = 0x0002 if self.root.tk.call("tk", "windowingsystem") == "aqua" else 0x0012
        if event.state & ~lock_mask:
            return
        if event.widget.winfo_class() not in {
            "Tk", "Toplevel", "Frame", "TFrame", "Canvas", "Label", "TLabel",
            "Button", "TButton", "Checkbutton", "TCheckbutton",
            "Radiobutton", "TRadiobutton", "TScrollbar",
        }:
            return
        bounds = self.canvas.bbox("all")
        if not bounds or bounds[3] - bounds[1] <= self.canvas.winfo_height():
            return
        # Explicit scrolling takes precedence over a queued new-page reset.
        if self._page_reset is not None:
            self.root.after_cancel(self._page_reset)
            self._page_reset = None
        if movement == "top":
            self.canvas.yview_moveto(0)
        elif movement == "bottom":
            self.canvas.yview_moveto(1)
        else:
            self.canvas.yview_scroll(-1 if movement == "up" else 1, "pages")
        return "break"

    def _reveal_text_cursor(self, event):
        """Follow only local input in a focused editor too tall for the page."""
        if self.closed or self.root.focus_get() != event.widget:
            return
        if (isinstance(event.widget, tk.Text)
                and event.widget.winfo_height() > self.canvas.winfo_height()):
            self._reveal_focus(event)

    def _reveal_focus(self, event):
        if self.closed:
            return
        widget = event.widget
        if (not str(widget).startswith(str(self.body) + ".") or
                not widget.winfo_ismapped() or not self._is_focus_control(widget)):
            return
        self.root.update_idletasks()
        top = widget.winfo_rooty() - self.canvas.winfo_rooty()
        bottom = top + widget.winfo_height()
        viewport = self.canvas.winfo_height()
        if isinstance(widget, tk.Text) and widget.winfo_height() > viewport:
            # The whole editor cannot fit. Reveal the insertion/validation line
            # instead, preserving its selection and native text scrolling.
            widget.see("insert")
            self.root.update_idletasks()
            line = widget.dlineinfo("insert")
            if line is None:
                return
            top += line[1]
            bottom = top + line[3]
        bounds = self.canvas.bbox("all") or (0, 0, 0, viewport)
        region_height = max(viewport, bounds[3] - bounds[1])
        scrollable = max(0, region_height - viewport)
        if not scrollable:
            return
        current = self.canvas.yview()[0] * region_height
        if top < 0:
            target = current + top - 12
        elif bottom > viewport:
            target = current + bottom - viewport + 12
        else:
            return
        self.canvas.yview_moveto(max(0, min(scrollable, target)) / region_height)

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

    def reset_recording_feedback(self):
        """Stage only this section's defaults; never broaden into global reset."""
        if self.closed or self.saving or self._resetting_feedback:
            return
        self._resetting_feedback = True
        try:
            try:
                focus = self.root.focus_get()
            except tk.TclError:
                focus = None
            confirmed = messagebox.askyesno(
                "Reset Recording feedback?",
                "Reset the floating indicator, live preview, and start / stop sounds "
                "to their defaults?\n\nOther unsaved edits stay as they are. "
                "Save changes saves all pending edits.",
                parent=self.root,
            )
        finally:
            self._resetting_feedback = False
        if not confirmed:
            if focus is not None and not self.closed:
                try:
                    focus.focus_set()
                except tk.TclError:
                    pass
            return
        if self.closed or self.saving:
            return
        before = self._snapshot()
        defaults = Config()
        for key in ("indicator", "live_preview", "beep"):
            self.vars[key].set(getattr(defaults, key))
        self._dirty()
        if focus is self.preview_toggle and self.preview_toggle.instate(["disabled"]):
            self.feedback_reset_button.focus_set()
        if self._snapshot() != before:
            self.status.set("Recording feedback defaults ready · Save changes to apply")

    def _dirty(self, *_):
        self.preview_toggle.configure(state="normal" if self.vars["indicator"].get() else "disabled")
        endpoint_state = "normal" if self.vars["speech_end_enabled"].get() else "disabled"
        self.speech_end_pause.configure(state="readonly" if endpoint_state == "normal" else "disabled")
        self.speech_end_insert_toggle.configure(state=endpoint_state)
        dirty = self._reset_pending or self._snapshot() != self.baseline
        if not self.saving:
            self.save_button.configure(state="normal" if dirty else "disabled")
            self._clear_save_details()
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
        self.limit_hint.set(
            ("Desktop shortcut toggles recording; global Esc is unavailable. " if is_wayland() else "Esc cancels a take. ")
            + "No recording countdown. Temporary local audio is removed after processing or cancellation."
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
        from utterleaf.app_status import snapshot_message, status_message
        reply = ipc.send("status-detail", exact_reply=True)
        if reply == "unknown":
            # Only an explicit older authenticated server can negotiate v1.
            return (status_message(ipc.send("status")) +
                    "\nLoaded model details unavailable in this version.")
        message = snapshot_message(reply)
        if message is not None:
            return message
        if reply in (None, "restart-required"):
            return status_message(reply)
        return "Could not read app status · restart Utterleaf, then retry"

    def refresh_connection(self):
        """One bounded app snapshot; never open audio or load a model here."""
        if self.closed or self.checking_connection:
            return
        operation = object()
        self._connection_operation = operation
        self.checking_connection = True
        self.connection_button.configure(state="disabled")
        self.connection.set("Checking app…")

        def done(result, *, started=True):
            if self.closed or self._connection_operation is not operation:
                return
            try:
                if not self.root.winfo_exists():
                    return
            except tk.TclError:
                return
            self._connection_operation = None
            self.checking_connection = False
            self.connection_button.configure(state="normal")
            self.connection.set("App status check could not start · Refresh status to retry" if not started else
                                "Could not check the app · Refresh status to retry"
                                if isinstance(result, Exception) else result)

        try:
            self._worker(self._connection_status, done)
        except Exception as exc:
            done(exc, started=False)

    def refresh_mics(self):
        if self.closed or self.refreshing_mics or self.checking_mic:
            return
        self.refreshing_mics = True
        self.refresh_button.configure(state="disabled")
        self.mic_button.configure(state="disabled")
        self._set_error_details(self.mic_details_button)
        self.mic_message.set("Refreshing microphones…")
        def query():
            from utterleaf.audio import list_input_names
            return list_input_names()
        def done(result, *, started=True):
            if self.closed:
                return
            self.refreshing_mics = False
            self.refresh_button.configure(state="normal")
            self.mic_button.configure(state="normal")
            if isinstance(result, Exception):
                self.mic_message.set(
                    "Could not refresh microphones. The device list may be out of date. "
                    "Check microphone access, then select Refresh to retry." if started else
                    "Microphone refresh could not start. The device list was not checked. Select Refresh to retry."
                )
                self._set_error_details(self.mic_details_button, result)
                return
            saved = self.vars["microphone"].get()
            values = list(dict.fromkeys([SYSTEM_DEFAULT, *([saved] if saved else []), *result]))
            self.mic_box.configure(values=values)
            if not result:
                self.mic_message.set("No microphones found. Connect a microphone, then refresh.")
            elif self.vars["microphone"].get() not in ("", SYSTEM_DEFAULT, *result):
                self.mic_message.set("Selected microphone is unavailable. Reconnect it or choose another input and Save.")
            else:
                self.mic_message.set("Devices refreshed. Choose an input, then select Test. Save to apply changes.")
        try:
            self._worker(query, done)
        except Exception as exc:
            done(exc, started=False)

    def _microphone_changed(self, *_):
        if self.closed:
            return
        if self.checking_mic:
            self.mic_stop.set()
        self._set_error_details(self.mic_details_button)
        self.meter.configure(value=0)
        self._set_mascot("Dictation", "default")
        self.mic_message.set("Input changed. Select Test to check it; Save to apply.")

    def test_mic(self):
        if self.closed or self.refreshing_mics:
            return
        if self.checking_mic:
            self.mic_stop.set()
            self.mic_message.set("Stopping microphone check…")
            return
        device = self.vars["microphone"].get()
        self.checking_mic = True
        self.mic_stop.clear()
        self._set_error_details(self.mic_details_button)
        self.mic_button.configure(text="Stop")
        self.refresh_button.configure(state="disabled")
        self.mic_box.configure(state="disabled")
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
                    self.events.put((self._mic_check_level, min(100, rms * 700)))
            finally:
                recorder.close()
            return peak
        def done(result, *, started=True):
            if self.closed:
                return
            self.checking_mic = False
            self.mic_button.configure(text="Test")
            self.refresh_button.configure(state="normal")
            self.mic_box.configure(state="readonly")
            self.meter.configure(value=0)
            if device != self.vars["microphone"].get():
                self._microphone_changed()
            elif isinstance(result, Exception):
                self._set_mascot("Dictation", "error")
                if started:
                    from utterleaf.audio import microphone_error_hint
                    self.mic_message.set(microphone_error_hint(result))
                else:
                    self.mic_message.set(
                        "Microphone check could not start. This check recorded no audio. Select Test to retry."
                    )
                self._set_error_details(self.mic_details_button, result)
            elif self.mic_stop.is_set():
                self._set_mascot("Dictation", "default")
                self.mic_message.set("Microphone check stopped.")
            else:
                self._set_mascot("Dictation", "success" if result > 0.003 else "thinking")
                self.mic_message.set("Audio detected. Microphone check passed; speech model not tested." if result > 0.003
                                     else "Very little audio detected. Check your input device and microphone level.")
        try:
            self._worker(check, done)
        except Exception as exc:
            done(exc, started=False)

    def _mic_check_listening(self):
        if self.closed or not self.checking_mic or self.mic_stop.is_set():
            return
        self._set_mascot("Dictation", "listening")
        self.mic_message.set("Speak now… checking for five seconds.")

    def _mic_check_level(self, value):
        if not self.closed and self.checking_mic and not self.mic_stop.is_set():
            self.meter.configure(value=value)

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
                              text_cleanup=self.vars["text_cleanup"].get(),
                              output_format=self.vars["output_format"].get())
        self.preview_result.set(result.text or "No text to keep.")

    def diagnostics(self):
        def report():
            from utterleaf.hardware import generate_diagnostic_report
            return generate_diagnostic_report(load())
        self._run_report_check(report, "device")

    def cuda_setup(self):
        def steps():
            from utterleaf.hardware import cuda_setup_plan
            return "\n".join(cuda_setup_plan())
        self._run_report_check(steps, "gpu")

    def _report_controls(self):
        kind = self._report_operation[0] if self._report_operation is not None else None
        busy = kind is not None or self._exporting_report
        self.diagnostic_button.configure(state="disabled" if busy else "normal",
                                         text="Checking device…" if kind == "device" else "Check this device")
        self.cuda_button.configure(state="disabled" if busy else "normal",
                                   text="Checking…" if kind == "gpu" else "Set up NVIDIA GPU…")
        self.export_button.configure(state="normal" if self.report and not self._exporting_report else "disabled")

    def _reveal_report_feedback(self):
        """Reveal the complete local recovery message without moving focus/pages."""
        if self.closed:
            return
        self.report_feedback.pack(before=self.diagnostic_text, fill="x", pady=(0, 8))
        self.root.update_idletasks()
        if self.closed or not self.report_feedback.winfo_ismapped():
            return
        if self._page_reset is not None:
            self.root.after_cancel(self._page_reset)
            self._page_reset = None
        top = self.report_feedback.winfo_rooty() - self.canvas.winfo_rooty()
        bottom = top + self.report_feedback.winfo_height()
        viewport = self.canvas.winfo_height()
        bounds = self.canvas.bbox("all") or (0, 0, 0, viewport)
        region = max(viewport, bounds[3] - bounds[1])
        current = self.canvas.yview()[0] * region
        target = current + top - 12 if top < 0 else current + bottom - viewport + 12
        if top < 0 or bottom > viewport:
            self.canvas.yview_moveto(max(0, min(region - viewport, target)) / region)

    def _run_report_check(self, action, kind):
        if self.closed or self._report_operation is not None or self._exporting_report:
            return
        operation = self._report_operation = (kind, object())
        self._report_controls()
        self.report_status.set("Checking device using saved settings…" if kind == "device" else "Checking GPU setup…")
        self._reveal_report_feedback()

        def done(result):
            if self.closed or self._report_operation is not operation:
                return
            self._report_operation = None
            if isinstance(result, Exception):
                self.report_feedback.error(
                    "Couldn't check this device" if kind == "device" else "Couldn't check GPU setup",
                    "Previous report retained." if self.report else "No report is available.",
                    "Try Check this device again." if kind == "device" else "Try Set up NVIDIA GPU again.", result)
            else:
                self.report = result
                self.diagnostic_text.configure(state="normal")
                self.diagnostic_text.delete("1.0", "end")
                self.diagnostic_text.insert("1.0", result)
                self.diagnostic_text.configure(state="disabled")
                self.report_status.set("Report ready. Review device details and local paths before sharing."
                                       if result else "Check finished. No report was produced.")
            self._report_controls()
            self._reveal_report_feedback()

        try:
            self._worker(action, done)
        except Exception as exc:
            done(exc)

    def export_report(self):
        from pathlib import Path
        if self.closed or self._exporting_report or not self.report:
            return
        # A native picker's event loop can deliver a newer report completion.
        report = self.report
        self._exporting_report = True
        self._report_controls()
        try:
            try:
                path = filedialog.asksaveasfilename(parent=self.root, title="Save device report", defaultextension=".txt",
                                                  initialfile="Utterleaf diagnostics.txt", filetypes=[("Text file", "*.txt")])
            except Exception as exc:
                if not self.closed:
                    self.report_feedback.error("Couldn't choose a report location", "The report has not been saved.",
                                               "Try Save report again and choose a writable folder.", exc)
                    self._reveal_report_feedback()
                return
            if not path or self.closed:
                return
            try:
                Path(path).write_text(report, encoding="utf-8")
            except Exception as exc:
                if not self.closed:
                    if self.report != report:
                        self.report_feedback.error("Couldn't save earlier report", "The chosen file may be incomplete.",
                                                   "A newer report is shown. Review it, then retry Save report.", exc)
                    else:
                        self.report_feedback.error("Couldn't save report", "The report is still here; the chosen file may be incomplete.",
                                                   "Choose a writable folder and try Save report again.", exc)
                    self._reveal_report_feedback()
            else:
                if not self.closed:
                    self.report_status.set(
                        "Earlier report saved. A newer report is shown; review it before saving or sharing."
                        if self.report != report else "Report saved. Review the file before sharing.")
                    self._reveal_report_feedback()
        finally:
            self._exporting_report = False
            if not self.closed:
                self._report_controls()

    def _clear_save_details(self):
        self._save_details = ""
        if self.root.focus_get() is self.save_details_button:
            target = self.close_button if self.save_button.instate(["disabled"]) else self.save_button
            target.focus_set()
        self.save_details_button.grid_remove()

    def _set_save_details(self, error, reload_error=None):
        details = str(error)
        if reload_error is not None:
            details += f"\n\nApp notification: {reload_error}"
        self._save_details = technical_details(details)
        self.save_details_button.grid()

    def show_save_details(self):
        if not self.closed and self._save_details:
            messagebox.showinfo("Save — Details", self._save_details, parent=self.root)

    def save(self):
        if self.closed or self.saving:
            return
        snapshot = self._snapshot()
        reset_pending = self._reset_pending
        operation = self._save_operation = object()
        self.saving = True
        self.save_button.configure(state="disabled")
        self._clear_save_details()
        self.reset_button.configure(state="disabled")
        self.feedback_reset_button.configure(state="disabled")
        self.status.set("Saving changes…")
        def commit():
            from utterleaf import ipc
            try:
                cfg = apply_form(Config() if reset_pending else load(), **snapshot)
            except SettingsSaveError as exc:
                reload_error = None
                if exc.saved:
                    try:
                        ipc.send("reload")
                    except Exception as notification_error:
                        reload_error = notification_error
                return _SaveOutcome(error=exc, reload_error=reload_error)
            try:
                return _SaveOutcome(config=cfg, reply=ipc.send("reload"))
            except Exception as exc:
                return _SaveOutcome(config=cfg, reload_error=exc)
        def done(result, *, started=True):
            if self.closed or self._save_operation is not operation:
                return
            self._save_operation = None
            self.saving = False
            self.reset_button.configure(state="normal")
            self.feedback_reset_button.configure(state="normal")
            error = result if isinstance(result, Exception) else result.error
            reload_error = None if isinstance(result, Exception) else result.reload_error
            if error is not None:
                self._dirty()
                if started and isinstance(error, FormValidationError):
                    self._show_invalid_field(error)
                    return
                failure = save_failure(error, started=started, reload_failed=reload_error is not None)
                self.status.set(failure.status)
                self._set_save_details(error, reload_error)
                messagebox.showerror(failure.title, failure.message, parent=self.root)
                return
            self.cfg, reply = result.config, result.reply
            self._reset_pending = False
            self.baseline = snapshot
            self._dirty()
            if reload_error is not None:
                if self._snapshot() == snapshot:
                    self.status.set("Saved · Restart Utterleaf to apply")
                self._set_save_details(reload_error)
                messagebox.showerror(
                    "Settings saved locally",
                    "Your submitted settings were saved, but the running app could not be notified.\n\n"
                    "Quit and reopen Utterleaf to use the saved settings. Any newer form edits remain unsaved.",
                    parent=self.root,
                )
                return
            if self._snapshot() == snapshot:
                self.status.set("Saved · Quit and reopen Utterleaf to apply this update" if reply == "restart-required"
                                else "Changes saved" if reply == "ok" else "Saved · Start Utterleaf to use these settings")
        try:
            self._worker(commit, done)
        except Exception as exc:
            done(exc, started=False)

    def _show_invalid_field(self, error):
        page = ("Vocabulary" if error.field in {"names"} else "Dictation"
                if error.field in {"hotkey", "mode", "speech_end_enabled",
                                   "speech_end_pause_seconds", "speech_end_insert",
                                   "output_format"} else "Engine")
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
            elif isinstance(field, (tk.Entry, ttk.Entry, ttk.Combobox)):
                field.selection_range(0, "end")
            from types import SimpleNamespace
            self._reveal_focus(SimpleNamespace(widget=field))

    def close(self):
        if self.closed:
            return
        if self.saving:
            self.status.set("Finishing your save…")
            return
        if self.obs_pairing_dialog is not None and not self.obs_pairing_dialog.closed:
            self.status.set("Finishing OBS pairing before closing Settings…")
            self.obs_pairing_dialog.close(on_closed=self.close)
            return
        if self._reset_pending or self._snapshot() != self.baseline:
            if not messagebox.askyesno("Discard unsaved changes?", "Close without saving your changes?", parent=self.root):
                return
        self._clear_save_details()
        self.closed = True
        self._save_operation = None
        self._connection_operation = None
        self._model_download_operation = None
        self.search_query.set("")
        self.root.unbind_class(self._search_bindtag, self._search_shortcut)
        self.root.unbind_class(self._search_bindtag, "<Escape>")
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
