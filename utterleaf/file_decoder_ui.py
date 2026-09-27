"""Explicit setup for an optional decoder already installed by the user."""

from pathlib import Path
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import webbrowser

from utterleaf import theme
from utterleaf.file_decoder import DOWNLOAD_URL, decoder_selection, forget_decoder, select_decoder
from utterleaf.ui_layout import ActionRow, ScrollableContent, wrapped_label
from utterleaf.ui_feedback import RecoveryFeedback


class DecoderDialog:
    def __init__(self, parent):
        self.root = tk.Toplevel(parent)
        self.root.title("More file formats — Utterleaf")
        self.root.geometry("680x530")
        self.root.minsize(560, 500)
        self.root.transient(parent)
        theme.apply(self.root)
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        self.content = ScrollableContent(self.root, padding=24)
        self.content.grid(row=0, column=0, sticky="nsew")
        page = self.content.body
        page.columnconfigure(0, weight=1)
        wrapped_label(page, text="MP3, M4A and video files", style="Section.TLabel").grid(
            row=0, column=0, sticky="ew")

        def label(text, row):
            widget = wrapped_label(page, text=text, justify="left")
            widget.grid(row=row, column=0, sticky="ew", pady=(12, 0))

        self.status = tk.StringVar(self.root)
        self.feedback = RecoveryFeedback(page, self.status)
        self.feedback.grid(row=1, column=0, sticky="ew", pady=(12, 0))
        label("Connect FFmpeg once to decode common audio and video locally. PCM WAV already works without it. No audio is uploaded.", 2)
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
        label(instructions, 3)
        label("Choose a current FFmpeg build you trust and verify its publisher checksum. Selecting it permits Utterleaf to run that program for your files. Setup does not run installers.", 4)
        self.refresh()
        actions = ActionRow(self.root)
        actions.grid(row=1, column=0, sticky="ew", padx=24, pady=(12, 20))
        actions.add(ttk.Button(actions, text="Download page…", command=self.download_page))
        actions.add(ttk.Button(actions, text="Choose FFmpeg…", style="Primary.TButton", command=self.choose))
        actions.add(ttk.Button(actions, text="Forget selection", command=self.forget))
        actions.add(ttk.Button(actions, text="Done", command=self.root.destroy))
        self.root.bind("<Escape>", lambda _event: self.root.destroy())
        self.root.grab_set()

    def refresh(self):
        try:
            selected = decoder_selection()
            self.status.set("Selected: " + Path(selected["path"]).name + ". Choose again after updating it."
                            if selected else "No FFmpeg selected. WAV remains available.")
        except Exception as exc:
            self.feedback.error(
                "Couldn't read file-format setup",
                "Extra audio and video formats may be unavailable; PCM WAV still works.",
                "Choose a trusted FFmpeg executable again, or forget the stored selection.",
                exc,
            )

    def download_page(self):
        try:
            if not webbrowser.open(DOWNLOAD_URL):
                raise RuntimeError("The browser did not accept the request.")
            self.status.set("Download page opened. Install and verify FFmpeg, then choose its executable here.")
        except Exception as exc:
            self.feedback.error("Couldn't open download page", "The browser could not open the page.",
                                f"Open {DOWNLOAD_URL} in your browser.", exc)
        self.content.reveal(self.feedback)

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
            self.feedback.error(
                "Couldn't use that FFmpeg installation",
                "The requested setup did not complete.",
                "Verify the installation and publisher checksum, then choose FFmpeg again.",
                exc,
            )
        self.content.reveal(self.feedback)

    def forget(self):
        try:
            forget_decoder()
            self.refresh()
        except OSError as exc:
            self.feedback.error(
                "Couldn't forget file-format setup",
                "Utterleaf could not confirm that the stored selection was removed.",
                "Check access to Utterleaf's settings folder, then choose Forget selection again.",
                exc,
            )
        self.content.reveal(self.feedback)
