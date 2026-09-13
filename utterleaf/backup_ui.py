"""Keyboard-accessible, explicit local backup preview dialog."""
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from utterleaf import theme

from utterleaf.backup import PORTABLE_PREFERENCES, export_backup
from utterleaf.backup_store import apply_import, prepare_import, write_backup

LABELS = {"text_cleanup": "Text cleanup", "remove_fillers": "Remove fillers",
          "fix_corrections": "Fix spoken corrections", "beep": "Sound feedback",
          "tray": "Tray icon", "indicator": "Floating indicator", "denoise": "Noise reduction",
          "output_format": "Output style", "speech_end_enabled": "Stop after speech",
          "speech_end_pause_seconds": "Speech-end pause", "speech_end_insert": "Insert after speech end"}


class BackupDialog:
    def __init__(self, parent, cfg, vocabulary, *, plan=None, on_applied=lambda _values: None):
        self.cfg, self.vocabulary, self.plan = cfg, vocabulary, plan
        self.on_applied = on_applied
        self.review = None
        self.payload = None
        self.root = tk.Toplevel(parent)
        theme.apply(self.root)
        self.root.title("Import backup · Review" if plan is not None else "Export backup · Review")
        self.root.geometry("680x660")
        self.root.minsize(480, 460)
        self.root.transient(parent)
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(3, weight=1)
        self.intro = ttk.Label(self.root, text="Choose portable preferences and vocabulary to include. Network, clipboard, "
                  "microphone, hotkeys and model settings stay unchanged. Vocabulary may contain personal information.",
                  wraplength=610)
        self.intro.grid(row=0, column=0, sticky="ew", padx=18, pady=12)
        choices = ttk.Frame(self.root)
        choices.grid(row=1, column=0, sticky="ew", padx=18)
        available = dict(plan.preferences) if plan is not None else {key: getattr(cfg, key) for key in PORTABLE_PREFERENCES}
        self.selected = {}
        for index, key in enumerate(available):
            var = tk.BooleanVar(self.root, value=plan is None)
            self.selected[key] = var
            ttk.Checkbutton(choices, text=LABELS[key], variable=var, command=self.refresh).grid(
                row=index // 2, column=index % 2, sticky="w", padx=(0, 14), pady=3)
        vocabulary_row = ttk.Frame(self.root)
        vocabulary_row.grid(row=2, column=0, sticky="ew", padx=18, pady=10)
        self.mode = tk.StringVar(self.root, value="keep")
        self.include_vocabulary = tk.BooleanVar(self.root, value=True)
        if plan is None:
            ttk.Checkbutton(vocabulary_row, text="Include vocabulary (comments excluded)",
                            variable=self.include_vocabulary, command=self.refresh).pack(anchor="w")
        else:
            ttk.Label(vocabulary_row, text="Vocabulary decision:").pack(side="left")
            picker = ttk.Combobox(vocabulary_row, textvariable=self.mode,
                                 values=("keep",) if plan.vocabulary is None else ("keep", "merge", "replace"),
                                 state="readonly", width=12)
            picker.pack(side="left", padx=8)
            picker.bind("<<ComboboxSelected>>", lambda _event: self.refresh())
        frame = ttk.Frame(self.root)
        frame.grid(row=3, column=0, sticky="nsew", padx=18)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)
        self.preview = tk.Text(frame, wrap="word", height=12, takefocus=True,
                               bg=theme.SURFACE_LOW, fg=theme.ON_SURFACE,
                               insertbackground=theme.PRIMARY, selectbackground=theme.PRIMARY_CONTAINER,
                               selectforeground=theme.ON_PRIMARY_CONTAINER, highlightcolor=theme.PRIMARY,
                               highlightbackground=theme.OUTLINE_VARIANT, relief="flat", padx=10, pady=8)
        self.preview.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(frame, command=self.preview.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.preview.configure(yscrollcommand=scroll.set)
        self.status = tk.StringVar(self.root)
        self.status_label = ttk.Label(self.root, textvariable=self.status, wraplength=610)
        self.status_label.grid(row=4, column=0, sticky="ew", padx=18, pady=8)
        actions = ttk.Frame(self.root)
        actions.grid(row=5, column=0, sticky="e", padx=18, pady=(0, 14))
        ttk.Button(actions, text="Cancel", command=self.root.destroy).pack(side="left", padx=8)
        self.confirm = ttk.Button(actions, text="Apply reviewed import…" if plan is not None else "Save new backup…",
                                  command=self.confirm_action, style="Primary.TButton")
        self.confirm.pack(side="left")
        self.root.bind("<Escape>", lambda _event: self.root.destroy())
        self.root.bind("<Configure>", self.resize)
        self.refresh()
        self.root.grab_set()
        self.confirm.focus_set()

    def resize(self, event):
        if event.widget is self.root:
            for label in (self.intro, self.status_label):
                label.configure(wraplength=max(200, event.width - 36))

    def refresh(self):
        self.review = self.payload = None
        keys = tuple(key for key, var in self.selected.items() if var.get())
        try:
            if self.plan is None:
                self.payload = export_backup(self.cfg, self.vocabulary, preference_keys=keys,
                                             include_vocabulary=self.include_vocabulary.get())
                content = self.payload
                self.status.set("Review the plaintext content. Save creates a new file; existing files are never overwritten.")
            else:
                self.review = prepare_import(self.plan, preference_keys=keys, vocabulary_mode=self.mode.get())
                values = self.review.values
                lines = ["Selected preference changes:"]
                def label(value):
                    return "On" if value is True else "Off" if value is False else {"auto": "Automatic", "on": "On", "off": "Off"}.get(value, str(value))
                for key, before, after in self.review.preference_changes:
                    lines.append(f"{LABELS[key]}: {label(before)} → {label(after)}")
                if not keys:
                    lines.append("None selected")
                incoming = self.plan.vocabulary
                lines += ["", f"Imported vocabulary entries: {len(incoming or ())}",
                          f"Current vocabulary entries: {self.review.vocabulary_counts[0]}",
                          f"Result vocabulary entries: {self.review.vocabulary_counts[1]}",
                          f"Decision: {self.mode.get()}",
                          f"Existing definitions kept on merge conflicts: {len(values.vocabulary_conflicts)}",
                          "", "Imported vocabulary (review before applying):"]
                lines.extend(f"{s} → {w}" for s, w in incoming or ())
                if values.vocabulary_conflicts:
                    lines += ["", "Conflicting spoken terms kept unchanged:", *values.vocabulary_conflicts]
                content = "\n".join(lines)
                self.status.set("Nothing is saved until you apply and confirm. Replace removes the current vocabulary.")
            self.confirm.configure(state="normal")
        except Exception:
            content = "Could not build a safe preview. Check the selected file and current vocabulary, then reopen this dialog."
            self.status.set("No changes saved.")
            self.confirm.configure(state="disabled")
        self.preview.configure(state="normal")
        self.preview.delete("1.0", "end")
        self.preview.insert("1.0", content)
        self.preview.configure(state="disabled")

    def confirm_action(self):
        try:
            if self.plan is None:
                if self.payload is None:
                    return
                name = filedialog.asksaveasfilename(parent=self.root, title="Save a new backup file",
                    defaultextension=".json", initialfile="utterleaf-backup.json", filetypes=[("JSON backup", "*.json")])
                if not name:
                    return
                write_backup(Path(name), self.payload)
                self.status.set("Backup saved. This dialog can now be closed.")
            else:
                if self.review is None:
                    return
                if not messagebox.askyesno("Apply reviewed backup?",
                    "Save the selected preferences and vocabulary decision shown in this preview?\n\n"
                    "Network and clipboard settings remain unchanged.", parent=self.root):
                    return
                values = apply_import(self.review)
                self.on_applied(values)
                self.root.destroy()
        except FileExistsError:
            messagebox.showerror("Choose a new filename", "An existing file will not be overwritten. Choose a different filename.", parent=self.root)
        except Exception as error:
            from utterleaf.backup import BackupError
            message = str(error) if isinstance(error, BackupError) else "The file operation failed. Check access and free disk space."
            messagebox.showerror("Backup could not finish", message, parent=self.root)
