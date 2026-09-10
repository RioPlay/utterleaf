"""Explicit setup for an optional decoder already installed by the user."""

from pathlib import Path
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import webbrowser

from utterleaf import theme
from utterleaf.file_decoder import DOWNLOAD_URL, decoder_selection, forget_decoder, select_decoder


class DecoderDialog:
    def __init__(self, parent):
        self.root = tk.Toplevel(parent)
        self.root.title("More file formats — Utterleaf")
        self.root.geometry("680x530")
        self.root.minsize(560, 500)
        self.root.transient(parent)
        theme.apply(self.root)
        page = ttk.Frame(self.root, padding=24)
        page.pack(fill="both", expand=True)
        page.columnconfigure(0, weight=1)
        page.rowconfigure(5, weight=1)
        ttk.Label(page, text="MP3, M4A and video files", style="Section.TLabel").grid(row=0, column=0, sticky="w")
        self.labels = []
        def label(text, row):
            widget = ttk.Label(page, text=text, wraplength=625, justify="left")
            widget.grid(row=row, column=0, sticky="ew", pady=(12, 0))
            self.labels.append(widget)
        label("Connect FFmpeg once to decode common audio and video locally. PCM WAV already works without it. No audio is uploaded.", 1)
        if sys.platform == "win32":
            instructions = ("1. Open the download page below. Under Windows, choose gyan.dev.\n"
                            "2. Download the release essentials ZIP, then use Extract All.\n"
                            "3. Keep that folder in a permanent location. Choose its bin → ffmpeg.exe below.")
        elif sys.platform == "darwin":
            instructions = ("1. Install FFmpeg using your trusted package manager (Homebrew: brew install ffmpeg).\n"
                            "2. Find its path with: command -v ffmpeg\n"
                            "3. Choose that ffmpeg executable below. In the picker, Command+Shift+G opens a path.")
        else:
            instructions = ("1. Install FFmpeg from your distribution's package manager. On Ubuntu/Debian: sudo apt install ffmpeg\n"
                            "2. Find its path with: command -v ffmpeg\n"
                            "3. Choose that ffmpeg executable below (usually /usr/bin/ffmpeg).")
        label(instructions, 2)
        label("Choose a current FFmpeg build you trust and verify its publisher checksum. Selecting it permits Utterleaf to run that program for your files. Setup does not run installers.", 3)
        self.status = tk.StringVar()
        current = ttk.Label(page, textvariable=self.status, wraplength=625)
        current.grid(row=4, column=0, sticky="ew", pady=(16, 0))
        self.labels.append(current)
        self.refresh()
        actions = ttk.Frame(page)
        actions.grid(row=6, column=0, sticky="ew", pady=(16, 0))
        ttk.Button(actions, text="Download page…", command=self.download_page).pack(side="left")
        ttk.Button(actions, text="Choose FFmpeg…", style="Primary.TButton", command=self.choose).pack(side="left", padx=8)
        secondary = ttk.Frame(page)
        secondary.grid(row=7, column=0, sticky="ew", pady=(10, 0))
        ttk.Button(secondary, text="Forget selection", command=self.forget).pack(side="left")
        ttk.Button(secondary, text="Done", command=self.root.destroy).pack(side="right")
        self.root.bind("<Configure>", self.resize)
        self.root.bind("<Escape>", lambda _event: self.root.destroy())
        self.root.grab_set()

    def resize(self, event):
        if event.widget is self.root:
            for label in self.labels:
                label.configure(wraplength=max(200, event.width - 48))

    def refresh(self):
        try:
            selected = decoder_selection()
            self.status.set("Selected: " + Path(selected["path"]).name + ". Choose again after updating it."
                            if selected else "No FFmpeg selected. WAV remains available.")
        except Exception as exc:
            self.status.set(str(exc))

    def download_page(self):
        try:
            if not webbrowser.open(DOWNLOAD_URL):
                self.status.set(f"Open {DOWNLOAD_URL} in your browser.")
        except Exception:
            self.status.set(f"Open {DOWNLOAD_URL} in your browser.")

    def choose(self):
        name = filedialog.askopenfilename(parent=self.root, title="Choose the installed ffmpeg executable",
                                         filetypes=[("FFmpeg executable", "ffmpeg.exe" if sys.platform == "win32" else "ffmpeg"),
                                                    ("All files", "*.*")])
        if not name:
            return
        if not messagebox.askyesno("Use this FFmpeg installation?",
                                   f"Use {Path(name)} to decode files you select?\n\nOnly choose a program you installed from a trusted source. Utterleaf will remember this choice.",
                                   parent=self.root):
            return
        try:
            select_decoder(name)
            self.refresh()
        except Exception as exc:
            self.status.set(str(exc))

    def forget(self):
        try:
            forget_decoder()
            self.refresh()
        except OSError:
            self.status.set("Could not forget the selection. Check access to the app's settings folder.")
