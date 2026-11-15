"""Explicit, read-only local model inventory for the native Settings form."""

import tkinter as tk
from tkinter import ttk

from utterleaf import model_inventory
from utterleaf.model_inventory import ModelInstallation
from utterleaf.model_presentation import model_display_name, model_purpose
from utterleaf.ui_feedback import RecoveryFeedback
from utterleaf.ui_layout import ActionRow, wrapped_label


def _installation_name(entry: ModelInstallation) -> str:
    backend = "NPU" if entry.backend == "openvino" else "CPU / NVIDIA"
    return f"{model_display_name(entry.name)} — {backend}"


def _setup_size(size: int | None) -> str:
    if size is None:
        return "Setup file size: unknown."
    if size < 1000:
        return f"Setup file size: {size} {'byte' if size == 1 else 'bytes'}."
    for divisor, unit in ((1_000_000_000_000, "TB"), (1_000_000_000, "GB"),
                          (1_000_000, "MB"), (1_000, "kB")):
        if size >= divisor:
            return f"Setup file size: about {size / divisor:.1f} {unit}."


class ModelInventoryPanel(ttk.Frame):
    """The owner supplies its queue, compatibility policy, and staging callback.

    Construction and preference changes never scan. Destroying or disposing the
    panel invalidates its one pending completion, without owning a worker thread
    or attempting to cancel local filesystem work already in progress.
    """

    def __init__(self, parent, *, worker, selection_reason, select_model, is_closed):
        super().__init__(parent)
        self._worker = worker
        self._selection_reason = selection_reason
        self._select_model = select_model
        self._is_closed = is_closed
        self._operation = None
        self._disposed = False
        self.entries = ()
        self.columnconfigure(0, weight=1)

        self.snapshot_label = wrapped_label(
            self, text="Refresh after downloads or external file changes. "
            "Automatic processing may use a separate NPU installation.")
        self.snapshot_label.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        refresh_actions = ActionRow(self)
        refresh_actions.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        self.refresh_button = refresh_actions.add(ttk.Button(
            refresh_actions, text="Refresh local list", command=self.refresh))
        picker_row = ttk.Frame(self)
        picker_row.columnconfigure(0, weight=1)
        picker_row.grid(row=2, column=0, sticky="ew", pady=(0, 8))
        wrapped_label(picker_row, text="Local installation").grid(row=0, column=0, sticky="ew")
        self.model_picker = ttk.Combobox(picker_row, state="disabled", width=1)
        self.model_picker.grid(row=1, column=0, sticky="ew", pady=(4, 0))
        self.model_picker.bind("<<ComboboxSelected>>", self._selection_changed)

        self.selected_text = tk.StringVar(self)
        self.selected_label = wrapped_label(self, textvariable=self.selected_text)
        self.selected_label.grid(row=3, column=0, sticky="ew")
        self.size_text = tk.StringVar(self)
        self.size_label = wrapped_label(self, textvariable=self.size_text)
        self.size_label.grid(row=4, column=0, sticky="ew", pady=(6, 0))
        self.size_hint = wrapped_label(
            self, text="Recognized setup files only; excludes extra files and shared cache. "
            "Not download size or reclaimable space.")
        self.size_hint.grid(row=5, column=0, sticky="ew", pady=(4, 0))
        self.reason_text = tk.StringVar(self)
        self.reason_label = wrapped_label(self, textvariable=self.reason_text)
        self.reason_label.grid(row=6, column=0, sticky="ew", pady=(6, 0))
        use_actions = ActionRow(self)
        use_actions.grid(row=7, column=0, sticky="ew", pady=(8, 0))
        self.use_button = use_actions.add(ttk.Button(
            use_actions, text="Use this model", command=self.use_selected, state="disabled"))
        self.status = tk.StringVar(self, value="Select Refresh local list to check guided installations. "
                                   "Custom locations are not listed.")
        self.feedback = RecoveryFeedback(self, self.status)
        self.feedback.grid(row=8, column=0, sticky="ew", pady=(8, 0))
        self.feedback.details_button.configure(command=self._show_details)
        self.bind("<Destroy>", self._destroy)
        self._render_selection()

    @property
    def selected_entry(self) -> ModelInstallation | None:
        if self._disposed:
            return None
        index = self.model_picker.current()
        return self.entries[index] if 0 <= index < len(self.entries) else None

    def _alive(self):
        return not self._disposed and not self._is_closed()

    def dispose(self):
        """Invalidate callbacks even when the owning Settings window is hidden."""
        self._disposed = True
        self._operation = None

    def _destroy(self, event):
        if event.widget is self:
            self.dispose()

    def _show_details(self):
        if self._alive():
            self.feedback.show_details()

    def _render_selection(self):
        entry = self.selected_entry
        if entry is None:
            self.selected_text.set("")
            self.size_text.set("")
            self.reason_text.set("")
            self.size_label.grid_remove()
            self.size_hint.grid_remove()
            self.reason_label.grid_remove()
            self.use_button.configure(state="disabled")
            return
        states = {
            "installed": "Installed — required files are present; model loading is not checked.",
            "incomplete": "Incomplete — use this model, then Download above to finish setup.",
            "error": "Could not check these files. Refresh local list to retry.",
        }
        self.selected_text.set(f"{_installation_name(entry)}\n{states.get(entry.state, states['error'])}\n"
                               f"{model_purpose(entry.name)}")
        self.size_text.set(_setup_size(entry.size_bytes))
        self.size_label.grid()
        self.size_hint.grid()
        reason = self._selection_reason(entry)
        self.reason_text.set(reason or "")
        if reason:
            self.reason_label.grid()
        else:
            self.reason_label.grid_remove()
        enabled = (self._operation is None and entry.state in {"installed", "incomplete"}
                   and reason is None)
        self.use_button.configure(state="normal" if enabled else "disabled")

    def _selection_changed(self, _event=None):
        if not self._alive() or self._operation is not None:
            return
        self._render_selection()
        entry = self.selected_entry
        if entry is not None and entry.state == "error":
            self.feedback.error("Local model files could not be checked.",
                                "This installation cannot be selected from the list.",
                                "Select Refresh local list to retry.", entry.detail)
        else:
            self.status.set("Use this model changes only the model field. Save changes applies your selection.")

    def preferences_changed(self):
        """Re-evaluate compatibility using cached entries, without filesystem work."""
        if self._alive():
            self._render_selection()

    def refresh(self):
        if not self._alive() or self._operation is not None:
            return
        selected = self.selected_entry
        identity = (selected.name, selected.backend) if selected is not None else None
        operation = self._operation = object()
        self.refresh_button.configure(state="disabled")
        self.model_picker.configure(state="disabled")
        self.use_button.configure(state="disabled")
        self.status.set("Checking guided local model files…")

        def done(result, *, started=True):
            if not self._alive() or self._operation is not operation:
                return
            self._operation = None
            self.refresh_button.configure(state="normal")
            if isinstance(result, Exception):
                self.model_picker.configure(state="readonly" if self.entries else "disabled")
                self._render_selection()
                self.feedback.error(
                    "Local model refresh could not finish." if started else "Local model refresh could not start.",
                    "The previous list is unchanged." if self.entries else "No local list is available.",
                    "Select Refresh local list to retry.", result)
                return
            self.entries = tuple(result)
            self.model_picker.configure(values=tuple(_installation_name(entry) for entry in self.entries),
                                        state="readonly" if self.entries else "disabled")
            if self.entries:
                index = next((index for index, entry in enumerate(self.entries)
                              if (entry.name, entry.backend) == identity), 0)
                self.model_picker.current(index)
                self._selection_changed()
            else:
                self.model_picker.set("")
                self._render_selection()
                self.status.set("No guided local installations found. Choose a model and Download above. "
                                "Custom locations are not listed.")

        try:
            self._worker(model_inventory.inventory_models, done)
        except Exception as exc:
            done(exc, started=False)

    def use_selected(self):
        if not self._alive() or self._operation is not None:
            return
        self._render_selection()
        entry = self.selected_entry
        if entry is None or self.use_button.instate(["disabled"]):
            return
        try:
            self._select_model(entry)
        except Exception as exc:
            if self._alive():
                self.feedback.error("Model selection could not be completed.",
                                    "Review the model field above.", "Try Use this model again.", exc)
            return
        if self._alive():
            self.status.set("Model selected. Save changes applies any unsaved preferences.")
