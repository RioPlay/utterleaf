"""Explicit setup for an optional decoder already installed by the user."""

from pathlib import Path
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import webbrowser

from utterleaf import theme
from utterleaf.file_decoder import DOWNLOAD_URL, decoder_selection, forget_decoder, select_decoder
from utterleaf.file_probe import forget_probe, probe_selection, select_probe


class DecoderDialog:
    def __init__(self, parent):
        self.root = tk.Toplevel(parent)
        self.root.title("More file formats — Utterleaf")
        self.root.geometry("680x560")
        self.root.minsize(560, 500)
        self.root.transient(parent)
        theme.apply(self.root)
        page = ttk.Frame(self.root, padding=12)
        page.pack(fill="both", expand=True)
        page.columnconfigure(0, weight=1)
        page.rowconfigure(5, weight=1)
        ttk.Label(page, text="More file formats", style="Section.TLabel").grid(row=0, column=0, sticky="w")
        self.labels = []
        def label(text, row):
            widget = ttk.Label(page, text=text, wraplength=625, justify="left")
            widget.grid(row=row, column=0, sticky="ew", pady=(6, 0))
            self.labels.append(widget)
        label("Choose FFmpeg to decode audio and video, and FFprobe to inspect tracks. PCM WAV works without either tool.", 1)
        if sys.platform == "win32":
            instructions = ("1. Open the download page below. Under Windows, choose gyan.dev.\n"
                            "2. Download the release essentials ZIP, then use Extract All.\n"
                            "3. Keep that folder. Choose bin → ffmpeg.exe and bin → ffprobe.exe below.")
        elif sys.platform == "darwin":
            instructions = ("1. Install with Homebrew: brew install ffmpeg\n"
                            "2. Find both paths: command -v ffmpeg ffprobe\n"
                            "3. Choose each below. Command+Shift+G opens a path.")
        else:
            instructions = ("1. Install FFmpeg from your distribution's package manager.\n"
                            "2. Find both paths: command -v ffmpeg ffprobe\n"
                            "3. Choose each executable below (usually in /usr/bin).")
        label(instructions, 2)
        tools = ttk.Frame(page)
        tools.grid(row=3, column=0, sticky="ew", pady=(8, 0))
        tools.columnconfigure(0, weight=1)
        self.ffmpeg_status = tk.StringVar()
        self.ffprobe_status = tk.StringVar()
        self._tool_row(tools, 0, "FFmpeg", "Decodes selected audio and video files.", self.ffmpeg_status,
                       self.choose, self.forget)
        self._tool_row(tools, 1, "FFprobe", "Inspects selected tracks and their timing.", self.ffprobe_status,
                       self.choose_probe, self.forget_probe)
        label("Use trusted programs. Selections are checked before use; choose again after an update.", 4)
        self.status = tk.StringVar()
        self.status_label = ttk.Label(page, textvariable=self.status, wraplength=625)
        self.status_label.grid(row=5, column=0, sticky="ew", pady=(8, 0))
        self.labels.append(self.status_label)
        self.refresh()
        actions = ttk.Frame(page)
        actions.grid(row=6, column=0, sticky="ew", pady=(6, 0))
        ttk.Button(actions, text="Download page…", command=self.download_page).pack(side="left")
        ttk.Button(actions, text="Done", command=self.root.destroy).pack(side="right")
        self.root.bind("<Configure>", self.resize)
        self.root.bind("<Escape>", lambda _event: self.root.destroy())
        self.root.grab_set()

    def _tool_row(self, parent, row, name, description, status, choose, forget):
        group = ttk.LabelFrame(parent, text=name, padding=(8, 3))
        group.grid(row=row, column=0, sticky="ew", pady=(0 if row == 0 else 4, 0))
        group.columnconfigure(0, weight=1)
        ttk.Label(group, text=description, wraplength=480, justify="left").grid(row=0, column=0, columnspan=2, sticky="ew")
        # Keep long paths selectable without growing the dialog off-screen.
        ttk.Entry(group, textvariable=status, state="readonly", width=24).grid(row=1, column=0, sticky="ew", pady=(3, 0))
        actions = ttk.Frame(group)
        actions.grid(row=1, column=1, padx=(10, 0), pady=(3, 0))
        ttk.Button(actions, text="Choose…", command=choose, style="Primary.TButton").pack(side="left")
        ttk.Button(actions, text="Forget", command=forget).pack(side="left", padx=(5, 0))

    def resize(self, event):
        if event.widget is self.root:
            for label in self.labels:
                label.configure(wraplength=max(200, event.width - 48))

    def refresh(self):
        try:
            selected = decoder_selection()
            self.ffmpeg_status.set(selected["path"]
                                   if selected else "Not selected. WAV remains available.")
        except Exception as exc:
            self.ffmpeg_status.set(str(exc))
        try:
            selected = probe_selection()
            self.ffprobe_status.set(selected["path"]
                                    if selected else "Not selected. PCM WAV inspection works.")
        except Exception as exc:
            self.ffprobe_status.set(str(exc))

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

    def choose_probe(self):
        name = filedialog.askopenfilename(parent=self.root, title="Choose the installed ffprobe executable",
                                         filetypes=[("FFprobe executable", "ffprobe.exe" if sys.platform == "win32" else "ffprobe"),
                                                    ("All files", "*.*")])
        if not name:
            return
        if not messagebox.askyesno("Use this FFprobe installation?",
                                   f"Use {Path(name)} to inspect tracks and timing for files you select?\n\nOnly choose a program you installed from a trusted source. Utterleaf will remember this choice.",
                                   parent=self.root):
            return
        try:
            select_probe(name)
            self.refresh()
        except Exception as exc:
            self.ffprobe_status.set(str(exc))

    def forget_probe(self):
        try:
            forget_probe()
            self.refresh()
        except OSError:
            self.ffprobe_status.set("Could not forget the FFprobe selection. Check access to the app's settings folder.")
