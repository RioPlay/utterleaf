"""Local, keyboard-accessible visual reference for the app's artwork."""
from __future__ import annotations

import tkinter as tk
import queue
import threading
from tkinter import ttk, filedialog, messagebox
from PIL import ImageTk

from utterleaf import brand, theme


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
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        title = ttk.Frame(self.root, padding=(24, 18))
        title.pack(fill="x")
        ttk.Label(title, text="Icons & artwork", style="Title.TLabel").pack(anchor="w")
        ttk.Label(title, text="What each image means, where it appears, and how it looks on light and dark surfaces.",
                  style="Hint.TLabel", wraplength=640).pack(anchor="w", pady=(6, 0))
        self.tabs = ttk.Notebook(self.root)
        self.tabs.pack(fill="both", expand=True, padx=20)
        self.canvases = {}
        for name in ("Tray states", "App badges", "Cutout marks", "Utterling", "Wordmark"):
            tab = ttk.Frame(self.tabs)
            self.tabs.add(tab, text=name)
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
        self.root.bind("<Escape>", lambda e: self.close())
        footer = ttk.Frame(self.root, padding=(20, 14))
        footer.pack(fill="x")
        self.export_button = ttk.Button(footer, text="Export asset pack…", command=self.export)
        self.export_button.pack(side="left")
        ttk.Button(footer, text="Close", command=self.close).pack(side="right")

    def _row(self, parent, key, title, text, images, filename):
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=(0, 20))
        row.columnconfigure(0, weight=1)
        words = ttk.Frame(row)
        words.grid(row=0, column=0, sticky="nw", padx=(0, 16))
        ttk.Label(words, text=title, style="Section.TLabel", wraplength=320).pack(anchor="w")
        description = ttk.Label(words, text=text, style="Hint.TLabel", wraplength=320)
        description.pack(anchor="w", pady=(6, 4))
        reference = ttk.Label(words, text=filename, style="Hint.TLabel", wraplength=320)
        reference.pack(anchor="w")
        words.bind("<Configure>", lambda e: [w.configure(wraplength=max(120, e.width)) for w in words.winfo_children()])
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

    def _wheel(self, event, direction=None):
        name = self.tabs.tab(self.tabs.select(), "text")
        self.canvases[name].yview_scroll(direction if direction is not None else (-3 if event.delta > 0 else 3), "units")

    def _reveal_focus(self, event):
        canvas = self.canvases[self.tabs.tab(self.tabs.select(), "text")]
        if not str(event.widget).startswith(str(canvas) + "."):
            return
        top = event.widget.winfo_rooty() - canvas.winfo_rooty()
        bottom = top + event.widget.winfo_height()
        total = max(1, canvas.bbox("all")[3])
        if top < 0 or bottom > canvas.winfo_height():
            canvas.yview_moveto(canvas.yview()[0] + (top-10 if top < 0 else bottom-canvas.winfo_height()+10)/total)

    def export(self):
        path = filedialog.asksaveasfilename(parent=self.root, title="Export Utterleaf artwork", defaultextension=".zip",
                                          initialfile="utterleaf-artwork.zip", filetypes=[("ZIP archive", "*.zip")])
        if not path:
            return
        from .brand_export import export_pack
        self.export_button.configure(state="disabled", text="Exporting…")
        def work():
            try:
                export_pack(path)
            except Exception as exc:
                self.export_results.put(exc)
            else:
                self.export_results.put(None)
        threading.Thread(target=work, daemon=True).start()
        self.export_poll = self.root.after(100, self._export_done)

    def _export_done(self):
        try:
            result = self.export_results.get_nowait()
        except queue.Empty:
            self.export_poll = self.root.after(100, self._export_done)
            return
        self.export_poll = None
        self.export_button.configure(state="normal", text="Export asset pack…")
        if isinstance(result, Exception):
            messagebox.showerror("Could not export artwork", str(result), parent=self.root)
        else:
            messagebox.showinfo("Artwork exported", "Saved the icon sizes, transparent cutouts, mascots, and usage guide.", parent=self.root)

    def close(self):
        if self.export_poll is not None:
            self.root.after_cancel(self.export_poll)
        self.root.destroy()
