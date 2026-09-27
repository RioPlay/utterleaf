"""Recovery-first feedback with explicitly requested, bounded local details."""

import tkinter as tk
from tkinter import messagebox, ttk
import unicodedata

from utterleaf.ui_layout import wrapped_label


def technical_details(value) -> str:
    """Keep native dialogs bounded; strip control/format characters, not Unicode."""
    original = str(value)
    text = original[:4096].replace("\t", "    ")
    safe = "".join(character for character in text
                   if character == "\n" or unicodedata.category(character) not in {"Cc", "Cf", "Cs"})
    lines = safe.splitlines()
    clipped = len(original) > 4096 or len(lines) > 12 or any(len(line) > 160 for line in lines)
    visible = "\n".join(line[:160] for line in lines[:12]).strip()
    if clipped:
        visible += "\n[Further technical details omitted]"
    return visible or "No further technical information is available."


class RecoveryFeedback(ttk.Frame):
    """Ordinary status stays quiet; only a current error exposes Details."""

    def __init__(self, parent, status):
        super().__init__(parent)
        self.status = status
        self.details = ""
        self.problem = ""
        self.columnconfigure(0, weight=1)
        self.label = wrapped_label(self, textvariable=status)
        self.label.grid(row=0, column=0, sticky="ew")
        self.details_button = ttk.Button(self, text="Details…", command=self.show_details, state="disabled")
        self.details_button.grid(row=1, column=0, sticky="w", pady=(8, 0))
        self.details_button.grid_remove()
        self._trace = status.trace_add("write", self._clear)
        self.bind("<Destroy>", self._destroy)

    def _clear(self, *_args):
        self.details = self.problem = ""
        if self.focus_get() is self.details_button:
            self.details_button.tk_focusNext().focus_set()
        self.details_button.configure(state="disabled")
        self.details_button.grid_remove()

    def error(self, problem, impact, recovery, details):
        self.status.set(f"{problem}\n{impact} {recovery}")
        self.problem = problem
        self.details = technical_details(details)
        self.details_button.configure(state="normal")
        self.details_button.grid()

    def show_details(self):
        if self.details:
            messagebox.showinfo(self.problem + " — Details", self.details, parent=self.winfo_toplevel())

    def _destroy(self, event):
        if event.widget is self:
            self.details = self.problem = ""
            try:
                self.status.trace_remove("write", self._trace)
            except tk.TclError:
                pass
