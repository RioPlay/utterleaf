"""Local, keyboard-accessible visual reference for the app's artwork."""
from __future__ import annotations

import tkinter as tk
import queue
import threading
from tkinter import ttk, filedialog
from PIL import ImageTk

from utterleaf import brand, theme
from utterleaf.ui_feedback import RecoveryFeedback
from utterleaf.ui_layout import ActionRow, wrapped_label


class AppearanceGuide:
    def __init__(self, parent):
        self.root = tk.Toplevel(parent)
        self.root.title("Utterleaf · Icons & artwork")
        self.root.geometry(f"{min(900, parent.winfo_screenwidth()-60)}x{min(740, parent.winfo_screenheight()-90)}")
        self.root.minsize(720, 540)
        theme.apply(self.root)
        self.photos = []
        self.entries = {}
        self.export_results = queue.Queue()
        self.export_poll = None
        self.closed = False
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(1, weight=1)
        title = ttk.Frame(self.root, padding=(24, 12))
        title.grid(row=0, column=0, sticky="ew")
        wrapped_label(title, text="Icons & artwork", style="Section.TLabel").pack(fill="x")
        wrapped_label(title, text="Light/dark previews. Page Up/Down to scroll.",
                      style="Hint.TLabel").pack(fill="x", pady=(6, 0))
        self.tabs = ttk.Notebook(self.root)
        self.tabs.grid(row=1, column=0, sticky="nsew", padx=20)
        self.canvases = {}
        self._tab_names = ("Tray states", "App badges", "Cutout marks", "Utterling", "Wordmark")
        tab_labels = {"Tray states": "Tray", "App badges": "Badges", "Cutout marks": "Marks"}
        for name in self._tab_names:
            tab = ttk.Frame(self.tabs)
            # Concise, stable labels fit large text without shrinking its font.
            self.tabs.add(tab, text=tab_labels.get(name, name))
            canvas = tk.Canvas(tab, bg=theme.SURFACE, highlightthickness=0)
            scrollbar = ttk.Scrollbar(tab, orient="vertical", command=canvas.yview)
            scrollbar.pack(side="right", fill="y")
            canvas.pack(side="left", fill="both", expand=True)
            canvas.configure(yscrollcommand=scrollbar.set)
            body = ttk.Frame(canvas, padding=16)
            body.columnconfigure(0, weight=1)
            item = canvas.create_window(0, 0, window=body, anchor="nw")
            canvas.bind("<Configure>", lambda e, c=canvas, i=item: c.itemconfigure(i, width=e.width))
            body.bind("<Configure>", lambda e, c=canvas: c.configure(scrollregion=c.bbox("all")))
            self.canvases[name] = canvas
            self._populate(name, body)
        self.tabs.enable_traversal()
        self.root.bind("<MouseWheel>", self._wheel)
        self.root.bind("<Button-4>", lambda e: self._wheel(e, -1))
        self.root.bind("<Button-5>", lambda e: self._wheel(e, 1))
        self.root.bind("<FocusIn>", self._reveal_focus)
        for sequence in ("<Prior>", "<Next>", "<Home>", "<End>"):
            self.root.bind(sequence, self._scroll_page)
        self.root.bind("<Escape>", lambda e: self.close())
        self.status = tk.StringVar(self.root)
        self.feedback = RecoveryFeedback(self.root, self.status)
        self.feedback.grid(row=2, column=0, sticky="ew", padx=20, pady=(10, 0))
        self.feedback.grid_remove()
        footer = ActionRow(self.root)
        footer.grid(row=3, column=0, sticky="ew", padx=20, pady=10)
        self.export_button = ttk.Button(footer, text="Export asset pack…", command=self.export)
        footer.add(self.export_button)
        self.close_button = footer.add(ttk.Button(footer, text="Close", command=self.close))

    def _row(self, parent, key, title, text, images, filename):
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=(0, 20))
        row.columnconfigure(0, weight=1)
        words = ttk.Frame(row)
        words.grid(row=0, column=0, sticky="ew", padx=(0, 16))
        wrapped_label(words, text=title, style="Section.TLabel").pack(fill="x")
        wrapped_label(words, text=text, style="Hint.TLabel").pack(fill="x", pady=(6, 4))
        wrapped_label(words, text=filename, style="Hint.TLabel").pack(fill="x")
        for col, background in enumerate(("#FFFFFF", brand.DARK), start=1):
            panel = tk.Frame(row, bg=background, padx=8, pady=8)
            panel.grid(row=0, column=col, sticky="n", padx=3)
            photo = ImageTk.PhotoImage(images[col-1], master=self.root)
            self.photos.append(photo)
            tk.Label(panel, image=photo, bg=background, takefocus=False).pack()
            tk.Label(panel, text="Light surface" if col == 1 else "Dark surface", bg=background,
                     fg="#526671" if col == 1 else "#CCDCD8", font=("TkDefaultFont", 8)).pack(pady=(5, 0))
        self.entries[key] = row

    def _populate(self, name, body):
        if name == "Tray states":
            ttk.Label(body, text="The tray uses a rounded dark badge. Transparent exports are also provided for each state. Offline is Ready.",
                      wraplength=610, style="Hint.TLabel").pack(anchor="w", pady=(0, 18))
            for state, (title, description) in brand.STATE_LABELS.items():
                self._row(body, state, title, description, [brand.leaf_image(state)]*2, f"tray-{state}.png")
                self._row(body, f"cutout-{state}", f"{title} · cutout", "Use the variant named for its intended background.",
                          [brand.cutout_icon(state, background=b) for b in ("light", "dark")],
                          f"cutout-{state}-for-light-64.png / for-dark-64.png")
        elif name == "App badges":
            for surface in ("dark", "light", "green"):
                self._row(body, f"app-{surface}", f"{surface.title()} badge", "Rounded-square fill is intentional. Pixels outside the badge are transparent. Dark is used in the app.",
                          [brand.render_icon(surface=surface)]*2, f"app-{surface}-64.png")
            ttk.Label(body, text="PNG sizes: 16, 24, 32, 48, 64, 128, 256, 512. The pack also includes Windows ICO and macOS ICNS. The portable Mac build is not yet an app bundle.",
                      wraplength=610, style="Hint.TLabel").pack(anchor="w")
        elif name == "Cutout marks":
            for variant in brand.MARK_COLORS:
                self._row(body, f"mark-{variant}", variant.title(),
                          "Leaf and waveform only, with transparent interior and exterior. Dark marks suit light surfaces; light and inverse suit dark surfaces.",
                          [brand.mark_image(variant)]*2, f"mark-{variant}-64.png / mark-{variant}.svg")
        elif name == "Utterling":
            for expression, (title, description) in brand.MASCOT_LABELS.items():
                self._row(body, f"mascot-{expression}", title, description,
                          [brand.mascot_image(expression, 104)]*2, f"utterling-{expression}.png")
        else:
            from .brand_export import wordmark_image
            self._row(body, "wordmark", "Utterleaf · Let ideas speak", "Primary wordmark for documentation and brand materials. Use the inverse variant on dark backgrounds.",
                      [wordmark_image(False, 170), wordmark_image(True, 170)], "wordmark.png / wordmark-inverse.png / SVG equivalents")

    def _selected_canvas(self):
        return self.canvases[self._tab_names[self.tabs.index("current")]]

    def _scroll_input(self, event):
        if self.closed or event.widget.winfo_toplevel() is not self.root:
            return False
        if event.widget.winfo_class() in {"Text", "Entry", "TEntry", "Spinbox", "TSpinbox",
                                         "TCombobox", "Listbox", "Scale", "TScale"}:
            return False
        lock_mask = 0x2 if self.root.tk.call("tk", "windowingsystem") == "aqua" else 0x12
        return not (event.state & ~lock_mask)

    def _scroll_page(self, event):
        if not self._scroll_input(event):
            return
        canvas = self._selected_canvas()
        if event.keysym in {"Home", "End"}:
            canvas.yview_moveto(0 if event.keysym == "Home" else 1)
        else:
            canvas.yview_scroll(-1 if event.keysym == "Prior" else 1, "pages")
        return "break"

    def _wheel(self, event, direction=None):
        if not self._scroll_input(event) or event.widget.winfo_class() in {"Scrollbar", "TScrollbar"}:
            return
        if direction is None:
            if not event.delta:
                return
            direction = -1 if event.delta > 0 else 1
        self._selected_canvas().yview_scroll(direction * 3, "units")
        return "break"

    def _reveal_focus(self, event):
        if self.closed:
            return
        canvas = self._selected_canvas()
        if not str(event.widget).startswith(str(canvas) + "."):
            return
        top = event.widget.winfo_rooty() - canvas.winfo_rooty()
        bottom = top + event.widget.winfo_height()
        total = max(1, canvas.bbox("all")[3])
        if top < 0 or bottom > canvas.winfo_height():
            canvas.yview_moveto(canvas.yview()[0] + (top-10 if top < 0 else bottom-canvas.winfo_height()+10)/total)

    def export(self):
        if self.closed or self.export_button.instate(["disabled"]):
            return
        try:
            path = filedialog.asksaveasfilename(parent=self.root, title="Export Utterleaf artwork", defaultextension=".zip",
                                              initialfile="utterleaf-artwork.zip", filetypes=[("ZIP archive", "*.zip")])
        except Exception as exc:
            if not self.closed:
                self.feedback.error("Couldn't choose an export location", "Export hasn't started.",
                                    "Try Export asset pack again and choose a writable folder.", exc)
                self.feedback.grid()
            return
        if not path or self.closed:
            return
        from .brand_export import export_pack
        self.status.set("Exporting artwork…")
        self.feedback.grid()
        self.export_button.configure(state="disabled", text="Exporting…")
        def work():
            try:
                export_pack(path)
            except Exception as exc:
                self.export_results.put(exc)
            else:
                self.export_results.put(None)
        try:
            threading.Thread(target=work, daemon=True).start()
        except Exception as exc:
            self._export_error(exc)
            return
        self.export_poll = self.root.after(100, self._export_done)

    def _export_error(self, error):
        self.export_button.configure(state="normal", text="Export asset pack…")
        self.feedback.error("Couldn't export artwork", "Export did not finish.",
                            "Check disk space and folder access, then retry Export.", error)
        self.feedback.grid()

    def _export_done(self):
        if self.closed:
            return
        try:
            result = self.export_results.get_nowait()
        except queue.Empty:
            self.export_poll = self.root.after(100, self._export_done)
            return
        self.export_poll = None
        self.export_button.configure(state="normal", text="Export asset pack…")
        if isinstance(result, Exception):
            self._export_error(result)
        else:
            self.status.set("Artwork exported. The asset pack includes icons, cutouts, mascots and a usage guide.")
            self.feedback.grid()

    def close(self):
        if self.closed:
            return
        self.closed = True
        if self.export_poll is not None:
            self.root.after_cancel(self.export_poll)
            self.export_poll = None
        self.root.destroy()
