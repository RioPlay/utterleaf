"""Explicit local OBS pairing management; no connection, capture or model imports."""
from __future__ import annotations

from dataclasses import dataclass
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from utterleaf import theme
from utterleaf.obs_pairing_store import (
    ObsPairingStore, PairingStoreCancelled, PairingStoreCommitError,
)


@dataclass(frozen=True)
class _Outcome:
    action: str
    kind: str
    paired: bool | None
    package_removed: bool = False


def _stored(store) -> bool:
    key = store.load()
    try:
        return key is not None
    finally:
        if key is not None:
            key[:] = b"\0" * len(key)


def _pairing_worker(factory, commands, events, cancel, stop, stopped):
    """This thread receives no Tk objects and returns no secrets or exceptions."""
    try:
        with factory() as store:
            store.claim_owner()
            paired = None
            action, path, replace = "refresh", None, False
            while not stop.is_set():
                try:
                    if action == "refresh":
                        paired = _stored(store)
                        outcome = _Outcome(action, "ready", paired)
                    elif cancel.is_set():
                        raise PairingStoreCancelled("Cancelled before operation")
                    elif action == "import":
                        result = store.import_package(path, replace=replace, cancelled=cancel.is_set)
                        paired = True
                        outcome = _Outcome(action, "saved", paired, result.package_removed)
                    else:
                        store.forget()
                        paired = False
                        outcome = _Outcome(action, "forgotten", paired)
                except PairingStoreCancelled:
                    outcome = _Outcome(action, "cancelled", paired)
                except PairingStoreCommitError:
                    paired = None
                    outcome = _Outcome(action, "uncertain", paired)
                except Exception:
                    # An unexpected failure may happen after a storage change.
                    # Only the typed precommit cancellation proves preservation.
                    paired = None
                    outcome = _Outcome(action, "error", paired)
                events.put(outcome)
                if stop.is_set():
                    break
                command = commands.get()
                if command is None:
                    break
                action, path, replace = command
    except Exception:
        events.put(_Outcome("open", "unavailable", None))
    finally:
        stopped.set()


class ObsPairingDialog:
    def __init__(self, parent, *, store_factory=ObsPairingStore):
        self.parent, self.factory = parent, store_factory
        self.closed = self.busy = self.closing = False
        self.paired = None
        self._on_closed = None
        self._review_close_result = False
        self.root = tk.Toplevel(parent)
        theme.apply(self.root)
        self.root.title("Utterleaf · OBS pairing")
        self.root.geometry("620x480")
        self.root.minsize(450, 460)
        self.root.transient(parent)
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        self.labels = []
        viewport = ttk.Frame(self.root)
        viewport.grid(row=0, column=0, sticky="nsew")
        viewport.columnconfigure(0, weight=1)
        viewport.rowconfigure(0, weight=1)
        self.canvas = tk.Canvas(viewport, bg=theme.SURFACE_LOW, highlightthickness=0)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(viewport, orient="vertical", command=self.canvas.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.canvas.configure(yscrollcommand=scroll.set)
        content = ttk.Frame(self.canvas, style="Page.TFrame", padding=24)
        self.content = content
        self.content_id = self.canvas.create_window((0, 0), window=content, anchor="nw")
        content.bind("<Configure>", lambda _e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", self._resize)
        self._label(content, "OBS PAIRING", "Eyebrow.TLabel")
        self._label(content, "Keep your connection local", "Title.TLabel", pady=(8, 10))
        self._label(content, "Live OBS transcription is in development. This window manages your saved pairing only.",
                    "Subtitle.TLabel", pady=(0, 18))
        card = ttk.Frame(content, padding=16)
        card.pack(fill="x")
        self.state = tk.StringVar(self.root, "Checking saved pairing…")
        self.state_label = ttk.Label(card, textvariable=self.state, style="Section.TLabel", wraplength=520)
        self.state_label.pack(anchor="w", fill="x")
        self.labels.append((self.state_label, 80))
        self.status = tk.StringVar(self.root, "Checking private local storage…")
        self.status_label = ttk.Label(card, textvariable=self.status, style="Hint.TLabel", wraplength=520)
        self.status_label.pack(anchor="w", fill="x", pady=(6, 12))
        self.labels.append((self.status_label, 80))
        self.import_button = ttk.Button(card, text="Import pairing file…", style="Primary.TButton",
                                        command=self.import_pairing)
        self.import_button.pack(anchor="w")
        self._label(content, "In OBS, open Tools → Utterleaf pairing to create or export a pairing file. "
                    "Choose that file here on the same Windows account.", "Subtitle.TLabel", pady=(16, 10))
        footer = ttk.Frame(self.root, padding=(20, 12))
        footer.grid(row=1, column=0, sticky="ew")
        self.refresh_button = ttk.Button(footer, text="Refresh", command=self.refresh)
        self.refresh_button.pack(side="left")
        self.forget_button = ttk.Button(footer, text="Forget…", command=self.forget_pairing)
        self.forget_button.pack(side="left", padx=8)
        self.close_button = ttk.Button(footer, text="Close", command=self.close)
        self.close_button.pack(side="right")
        self.cancel_button = ttk.Button(card, text="Cancel import", command=self.cancel_import)
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.bind("<Escape>", lambda _e: self.close())
        self.root.bind("<Configure>", self._resize)
        self.root.bind("<Map>", self._mapped, add="+")
        self.root.bind("<FocusIn>", self._reveal_focus, add="+")
        self.root.bind("<MouseWheel>", lambda e: self.canvas.yview_scroll(-1 if e.delta > 0 else 1, "units"))
        self.root.bind("<Button-4>", lambda _e: self.canvas.yview_scroll(-1, "units"))
        self.root.bind("<Button-5>", lambda _e: self.canvas.yview_scroll(1, "units"))
        self.root.bind("<Destroy>", self._destroyed, add="+")
        self._start()
        self.poll_id = self.root.after(40, self._poll)

    def _mapped(self, event):
        if event.widget is self.root and not self.closed:
            self.root.grab_set()
            self.close_button.focus_set()

    def _label(self, parent, text, style, *, pady=0, margin=48):
        label = ttk.Label(parent, text=text, style=style, wraplength=560)
        label.pack(anchor="w", fill="x", pady=pady)
        self.labels.append((label, margin))
        return label

    def _resize(self, event):
        if event.widget is self.canvas:
            self.canvas.itemconfigure(self.content_id, width=event.width)
            for label, margin in self.labels:
                label.configure(wraplength=max(100, event.width - margin))

    def _reveal_focus(self, event):
        self._reveal(event.widget)

    def _reveal(self, widget):
        if not str(widget).startswith(str(self.content)):
            return
        self.root.update_idletasks()
        region = self.canvas.bbox("all")
        height = max(1, region[3] - region[1]) if region else 1
        top = widget.winfo_rooty() - self.canvas.winfo_rooty()
        bottom = top + widget.winfo_height() - self.canvas.winfo_height()
        if top < 0:
            self.canvas.yview_moveto(max(0, self.canvas.yview()[0] + top / height))
        elif bottom > 0:
            self.canvas.yview_moveto(min(1, self.canvas.yview()[0] + bottom / height))

    def _start(self):
        self.commands, self.events = queue.Queue(maxsize=1), queue.Queue(maxsize=2)
        self.cancel, self.stop, self.stopped = threading.Event(), threading.Event(), threading.Event()
        self.busy = True
        self._failed = False
        self.worker = threading.Thread(target=_pairing_worker,
            args=(self.factory, self.commands, self.events, self.cancel, self.stop, self.stopped),
            name="obs-pairing-setup", daemon=False)
        try:
            self.worker.start()
        except Exception:
            self._failed = True
            self.events.put(_Outcome("open", "unavailable", None))
            self.stopped.set()
        self._controls()

    def _controls(self):
        active = not self.busy and not self.closing and not self._failed and not self.stopped.is_set()
        self.import_button.configure(text="Replace pairing file…" if self.paired else "Import pairing file…",
                                     state="normal" if active and self.paired is not None else "disabled")
        self.forget_button.configure(state="normal" if active and self.paired is not False else "disabled")
        self.refresh_button.configure(text="Retry" if self.stopped.is_set() else "Refresh",
                                      state="normal" if not self.busy and not self.closing else "disabled")

    def _submit(self, action, path=None, replace=False):
        if self.busy or self.closing or self.stopped.is_set():
            return
        self.busy = True
        self.cancel.clear()
        self.status.set({"refresh": "Checking saved pairing…", "import": "Importing and verifying pairing…",
                         "forget": "Removing this desktop pairing…"}[action])
        if action == "import":
            self.cancel_button.pack(anchor="w", pady=(2, 0))
            self.cancel_button.configure(state="normal")
        self._controls()
        self.commands.put_nowait((action, path, replace))

    def refresh(self):
        if self.closed or self.busy or self.closing:
            return
        if self.stopped.is_set():
            self._join()
            self.state.set("Checking saved pairing…")
            self.status.set("Checking private local storage…")
            self._start()
        elif not self._failed:
            self._submit("refresh")

    def import_pairing(self):
        if self.busy or self.closing or self.paired is None or self.stopped.is_set():
            return
        path = filedialog.askopenfilename(parent=self.root, title="Choose an OBS pairing file",
                                         filetypes=[("Utterleaf OBS pairing", "*.ulobs")])
        if not path or self.closed or self.closing:
            return
        replace = bool(self.paired)
        title = "Replace this desktop pairing?" if replace else "Import this pairing?"
        if not messagebox.askyesno(title,
            "Save the selected pairing in Utterleaf? After saving and verifying it, Utterleaf removes "
            "the selected transfer file when possible.\n\n"
            "This changes only this desktop copy. Other copied files remain valid until you replace "
            "or forget pairing in OBS. No recording starts.", parent=self.root):
            return
        self._submit("import", path, replace)

    def forget_pairing(self):
        if self.busy or self.closing or self.paired is False or self.stopped.is_set():
            return
        if messagebox.askyesno("Forget this desktop pairing?",
            "Remove Utterleaf’s saved pairing from this computer?\n\n"
            "This does not revoke copied pairing files. Use Forget pairing in OBS to revoke them. "
            "Your preferences, models and transcripts are kept.", parent=self.root):
            self._submit("forget")

    def cancel_import(self):
        self.cancel.set()
        self.cancel_button.configure(state="disabled")
        self.status.set("Cancelling before commit, if possible. Waiting for the verified result…")

    def _receive(self, outcome):
        self.busy, self.paired = False, outcome.paired
        if outcome.kind == "unavailable":
            self._failed = True
        self.cancel_button.pack_forget()
        self.state.set("Pairing saved" if self.paired else "Not paired" if self.paired is False else "Pairing needs attention")
        messages = {
            "ready": "A saved pairing does not mean OBS is connected. Nothing here starts recording. Pairing is separate from Reset to defaults.",
            "forgotten": "This desktop pairing was removed. Other copies remain valid until revoked in OBS.",
            "cancelled": "Cancelled before commit. Your previous pairing and the transfer file were kept.",
            "uncertain": "Pairing was written but could not be verified. The transfer file was kept. Refresh to inspect the saved state before continuing.",
            "unavailable": "Private pairing storage could not open. Close other pairing windows, or check local storage access, then Retry.",
            "error": "The operation could not finish. Check the selected file and local storage access. Refresh to inspect the saved state.",
            "saved": "Pairing saved and verified. The selected transfer file was removed." if outcome.package_removed else
                     "Pairing saved and verified, but the selected transfer file remains. Keep it private; copies remain usable until revoked in OBS.",
        }
        message = messages[outcome.kind]
        if outcome.kind == "saved" and self.cancel.is_set():
            message = "Pairing committed before cancellation. " + message
        if self.closing and outcome.action in ("import", "forget") and outcome.kind != "cancelled":
            self._review_close_result = True
            message += " Close this window after reviewing the result."
        self.status.set(message)
        self._controls()
        if outcome.kind != "ready" and self.root.winfo_viewable():
            self._reveal(self.status_label)

    def _poll(self):
        if self.closed:
            return
        while True:
            try:
                self._receive(self.events.get_nowait())
            except queue.Empty:
                break
        if self.stopped.is_set():
            self._join()
            self.busy = False
            self._controls()
            if self.closing and not self._review_close_result:
                self._finish_close()
                return
        self.poll_id = self.root.after(40, self._poll)

    def close(self, *, on_closed=None):
        if on_closed is not None:
            self._on_closed = on_closed
        if self.closed:
            return
        if self.stopped.is_set() and not self.busy:
            self._finish_close()
            return
        self.closing = True
        self.cancel.set()
        self.stop.set()
        try:
            self.commands.put_nowait(None)
        except queue.Full:
            pass
        self.status.set("Finishing the pairing operation and releasing private storage…")
        self._controls()

    def _finish_close(self):
        self._join()
        callback = self._on_closed
        self._on_closed = None
        self.closed = True
        self.root.after_cancel(self.poll_id)
        self.root.destroy()
        if callback is not None:
            callback()

    def _join(self):
        if self.worker.ident is not None:
            self.worker.join()

    def _destroyed(self, event):
        if event.widget is not self.root:
            return
        self.closed = True
        if hasattr(self, "poll_id"):
            try:
                self.root.after_cancel(self.poll_id)
            except tk.TclError:
                pass
        self.cancel.set()
        self.stop.set()
        try:
            self.commands.put_nowait(None)
        except queue.Full:
            pass
