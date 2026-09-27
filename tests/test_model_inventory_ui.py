"""Synthetic inventory data and native keys; never scan personal model files."""

import gc
import tkinter as tk
from tkinter import ttk

import pytest

from utterleaf import model_inventory_ui as ui, theme
from utterleaf.model_inventory import ModelInstallation
from utterleaf.ui_feedback import technical_details
from utterleaf.ui_layout import ScrollableContent


INSTALLED = ModelInstallation("base", "ctranslate2", "installed", 1_234_567)
NPU = ModelInstallation("base", "openvino", "installed", 4_567_890)
INCOMPLETE = ModelInstallation("distil-small.en", "ctranslate2", "incomplete", 0)
PRIVATE = "PRIVATE-SENTINEL C:/private/model\x00\u202e " + "x" * 5000
ERROR = ModelInstallation("small", "openvino", "error", None, PRIVATE)


class HeldWorker:
    def __init__(self):
        self.jobs = []
        self.fail_start = False

    def __call__(self, work, done):
        if self.fail_start:
            raise RuntimeError(PRIVATE)
        self.jobs.append((work, done))

    def finish(self, result, index=-1):
        self.jobs[index][1](result)


@pytest.fixture(scope="module")
def tk_root():
    root = tk.Tk()
    root.withdraw()
    yield root
    root.destroy()
    del root
    gc.collect()


@pytest.fixture
def panel(tk_root, monkeypatch):
    # A missed mock fails before probing paths or starting any external action.
    def forbidden(*_args, **_kwargs):
        raise AssertionError("Inventory test crossed an external boundary")

    monkeypatch.setattr(ui.model_inventory, "inventory_models", forbidden)
    monkeypatch.setattr("utterleaf.config.save", forbidden)
    monkeypatch.setattr("utterleaf.ipc.send", forbidden)
    dialogs = []
    monkeypatch.setattr("utterleaf.ui_feedback.messagebox.showinfo",
                        lambda title, message, **_kw: dialogs.append((title, message)))
    root = tk.Toplevel(tk_root)
    root.withdraw()
    theme.apply(root)
    worker = HeldWorker()
    selected = []
    state = {"closed": False, "reason": None}
    view = ui.ModelInventoryPanel(
        root, worker=worker, selection_reason=lambda _entry: state["reason"],
        select_model=selected.append, is_closed=lambda: state["closed"])
    view.pack(fill="x", padx=12, pady=12)
    after = ttk.Button(root, text="Close")
    after.pack()
    root.geometry("620x780+20+20")
    root.deiconify()
    errors = []
    root.report_callback_exception = lambda *error: errors.append(error)
    root.update()
    yield view, worker, selected, state, dialogs, after
    root.destroy()
    assert errors == []


def _load(view, worker, entries=(INSTALLED, NPU, INCOMPLETE, ERROR)):
    view.refresh()
    worker.finish(entries)
    view.update()


def _choose(view, index):
    view.model_picker.current(index)
    view.model_picker.event_generate("<<ComboboxSelected>>")
    view.update()


def _primary(view):
    return "\n".join(variable.get() for variable in
                     (view.selected_text, view.size_text, view.reason_text, view.status))


@pytest.mark.parametrize("size, expected", [
    (None, "unknown"), (0, "0 bytes"), (1, "1 byte"), (999, "999 bytes"),
    (1000, "about 1.0 kB"), (1500, "about 1.5 kB"),
    (999_000, "about 999.0 kB"), (1_000_000, "about 1.0 MB"),
    (1_000_000_000, "about 1.0 GB"), (1_543_210_987, "about 1.5 GB"),
    (1_000_000_000_000, "about 1.0 TB"),
])
def test_setup_size_uses_honest_decimal_units_and_marks_rounding(size, expected):
    assert ui._setup_size(size) == f"Setup file size: {expected}."


def test_construction_and_preferences_never_scan_or_start_work(panel):
    view, worker, selected, state, dialogs, _ = panel
    assert worker.jobs == []
    assert view.entries == ()
    assert view.selected_entry is None
    assert view.model_picker.instate(["disabled"])
    assert view.use_button.instate(["disabled"])
    assert "Select Refresh local list" in view.status.get()
    assert "Custom locations are not listed" in view.status.get()
    state["reason"] = "Choose a compatible language."
    view.preferences_changed()
    assert worker.jobs == [] and selected == [] and dialogs == []


def test_explicit_refresh_uses_supplied_worker_and_single_pending_operation(panel, monkeypatch):
    view, worker, selected, _, _, _ = panel
    calls = []
    monkeypatch.setattr(ui.model_inventory, "inventory_models", lambda: calls.append("scan") or (INSTALLED,))
    view.refresh_button.invoke()
    view.refresh()
    view.refresh_button.invoke()
    assert calls == [] and len(worker.jobs) == 1
    assert view.refresh_button.instate(["disabled"])
    assert view.model_picker.instate(["disabled"])
    assert view.use_button.instate(["disabled"])
    work, done = worker.jobs[0]
    done(work())
    assert calls == ["scan"]
    assert view.entries == (INSTALLED,)
    assert view.selected_entry == INSTALLED
    assert view.status.get() == ("Use this model changes only the model field. "
                                 "Save changes applies your selection.")
    assert view.refresh_button.instate(["!disabled"])
    assert view.model_picker.instate(["readonly", "!disabled"])
    assert selected == []


@pytest.mark.parametrize("index, name, state_text, size", [
    (0, "Base — CPU / NVIDIA", "Installed", "about 1.2 MB"),
    (1, "Base — NPU", "Installed", "about 4.6 MB"),
    (2, "Distilled Small English — CPU / NVIDIA", "Incomplete", "0 bytes"),
    (3, "Small — NPU", "could not", "unknown"),
])
def test_each_entry_shows_factual_name_state_purpose_and_scoped_size(panel, index, name, state_text, size):
    view, worker, _, _, dialogs, _ = panel
    _load(view, worker)
    _choose(view, index)
    assert view.model_picker.get() == name
    assert name in view.selected_text.get()
    assert state_text.lower() in view.selected_text.get().lower()
    assert ("English-only" if index == 2 else "Multilingual") in view.selected_text.get()
    assert view.size_text.get().startswith("Setup file size: ")
    assert size in view.size_text.get()
    assert "excludes extra files and shared cache" in view.size_hint.cget("text")
    assert "Not download size or reclaimable space" in view.size_hint.cget("text")
    assert "Automatic processing may use a separate NPU installation" in view.snapshot_label.cget("text")
    assert "Refresh after downloads or external file changes" in view.snapshot_label.cget("text")
    if index < 2:
        assert "loading is not checked" in view.selected_text.get()
    if index == 2:
        assert "Download above to finish setup" in view.selected_text.get()
    assert "PRIVATE-SENTINEL" not in _primary(view)
    assert dialogs == []


def test_empty_result_removes_previous_row_and_explains_custom_location_limit(panel):
    view, worker, selected, _, _, _ = panel
    _load(view, worker)
    _load(view, worker, ())
    assert view.entries == () and view.selected_entry is None
    assert view.model_picker.get() == ""
    assert view.model_picker.instate(["disabled"])
    assert view.use_button.instate(["disabled"])
    assert "No guided local installations found" in view.status.get()
    assert "Choose a model and Download above" in view.status.get()
    assert "Custom locations are not listed" in view.status.get()
    assert not view.size_hint.winfo_ismapped()
    assert selected == []


def test_successful_refresh_preserves_name_and_backend_not_old_index(panel):
    view, worker, _, _, _, _ = panel
    _load(view, worker)
    _choose(view, 1)
    updated = ModelInstallation("base", "openvino", "incomplete", 100)
    _load(view, worker, (NPU, INSTALLED, updated))
    assert view.model_picker.current() == 0
    assert view.selected_entry == NPU
    _load(view, worker, (INSTALLED, updated))
    assert view.model_picker.current() == 1
    assert view.selected_entry == updated
    _load(view, worker, (INCOMPLETE,))
    assert view.selected_entry == INCOMPLETE


@pytest.mark.parametrize("started", [False, True])
@pytest.mark.parametrize("previous", [False, True])
def test_refresh_errors_preserve_list_release_actions_and_offer_explicit_safe_details(panel, started, previous):
    view, worker, selected, _, dialogs, _ = panel
    if previous:
        _load(view, worker)
        _choose(view, 1)
    before = view.entries, view.selected_entry
    worker.fail_start = not started
    view.refresh()
    if started:
        worker.finish(RuntimeError(PRIVATE))
    view.update()
    assert (view.entries, view.selected_entry) == before
    assert view._operation is None
    assert view.refresh_button.instate(["!disabled"])
    assert view.model_picker.instate(["readonly" if previous else "disabled"])
    assert view.use_button.instate(["!disabled" if previous else "disabled"])
    assert ("could not finish" if started else "could not start") in view.status.get()
    assert "Select Refresh local list to retry" in view.status.get()
    assert "PRIVATE-SENTINEL" not in _primary(view)
    assert dialogs == [] and selected == []
    view.feedback.details_button.invoke()
    assert dialogs == [(view.feedback.problem + " — Details", technical_details(PRIVATE))]
    assert "\x00" not in dialogs[0][1] and "\u202e" not in dialogs[0][1]
    assert len(dialogs[0][1]) < 2000
    worker.fail_start = False
    jobs = len(worker.jobs)
    view.refresh()
    view.refresh()
    assert len(worker.jobs) == jobs + 1
    assert view.feedback.details == ""
    assert not view.feedback.details_button.winfo_ismapped()
    worker.finish((INSTALLED,))
    assert view.entries == (INSTALLED,)


def test_duplicate_and_stale_completions_cannot_replace_newer_results(panel):
    view, worker, _, _, _, _ = panel
    _load(view, worker, (INSTALLED,))
    first_done = worker.jobs[0][1]
    first_done(RuntimeError(PRIVATE))
    assert view.entries == (INSTALLED,) and view.feedback.details == ""
    view.refresh()
    first_done((ERROR,))
    assert view._operation is not None
    assert view.entries == (INSTALLED,)
    worker.finish((NPU,))
    first_done((ERROR,))
    assert view.entries == (NPU,)
    assert "PRIVATE-SENTINEL" not in _primary(view)


def test_synchronous_completion_then_dispatch_exception_does_not_replace_success(panel):
    view, _, _, _, _, _ = panel
    def finish_then_raise(_work, done):
        done((INSTALLED,))
        raise RuntimeError(PRIVATE)
    view._worker = finish_then_raise
    view.refresh()
    assert view.entries == (INSTALLED,)
    assert view._operation is None
    assert view.feedback.details == ""
    assert view.refresh_button.instate(["!disabled"])


@pytest.mark.parametrize("ending", ["closed", "disposed", "destroyed"])
def test_close_dispose_and_destroy_ignore_late_callbacks_and_new_actions(panel, ending):
    view, worker, selected, state, dialogs, _ = panel
    _load(view, worker, (INSTALLED,))
    view.refresh()
    done = worker.jobs[-1][1]
    before = view.entries
    if ending == "closed":
        state["closed"] = True
    elif ending == "disposed":
        view.dispose()
        view.dispose()
    else:
        view.destroy()
    done((NPU,))
    done(RuntimeError(PRIVATE))
    view.refresh()
    view.preferences_changed()
    view.use_selected()
    view._show_details()
    assert view.entries == before
    assert len(worker.jobs) == 2
    assert selected == [] and dialogs == []


def test_cached_compatibility_changes_and_use_only_stage_the_current_entry(panel):
    view, worker, selected, state, _, _ = panel
    _load(view, worker)
    state["reason"] = "Choose NPU processing above to use this installation."
    view.preferences_changed()
    assert view.use_button.instate(["disabled"])
    assert view.reason_text.get() == state["reason"]
    view.use_selected()
    assert selected == []
    state["reason"] = None
    view.preferences_changed()
    assert view.use_button.instate(["!disabled"])
    assert not view.reason_label.winfo_ismapped()
    view.use_button.invoke()
    assert selected == [INSTALLED]
    assert view.status.get() == "Model selected. Save changes applies any unsaved preferences."
    assert len(worker.jobs) == 1
    state["reason"] = "Choose another language first."
    view.use_selected()  # Recheck even if preferences_changed was not called.
    assert selected == [INSTALLED]


def test_error_entry_cannot_be_used_and_only_explicit_details_expose_raw_text(panel):
    view, worker, selected, _, dialogs, _ = panel
    _load(view, worker, (ERROR, INSTALLED))
    assert view.use_button.instate(["disabled"])
    view.use_selected()
    assert selected == [] and dialogs == []
    assert "PRIVATE-SENTINEL" not in _primary(view)
    view.feedback.details_button.invoke()
    assert dialogs[-1][1] == technical_details(PRIVATE)
    _choose(view, 1)
    assert view.feedback.details == ""
    assert not view.feedback.details_button.winfo_ismapped()
    assert view.use_button.instate(["!disabled"])


def test_staging_exception_and_reentrant_close_are_safe(panel):
    view, worker, _, state, dialogs, _ = panel
    _load(view, worker, (INSTALLED,))
    def fail(_entry):
        raise RuntimeError(PRIVATE)
    view._select_model = fail
    view.use_selected()
    assert "Model selection could not be completed" in view.status.get()
    assert "PRIVATE-SENTINEL" not in _primary(view)
    assert dialogs == []
    before = view.status.get()
    view._select_model = lambda _entry: state.update(closed=True)
    view.use_selected()
    assert view.status.get() == before


def _visible(widget, viewport):
    assert widget.winfo_ismapped()
    assert widget.winfo_width() >= widget.winfo_reqwidth()
    assert widget.winfo_height() >= widget.winfo_reqheight()
    x = widget.winfo_rootx() - viewport.winfo_rootx()
    y = widget.winfo_rooty() - viewport.winfo_rooty()
    assert 0 <= x and x + widget.winfo_width() <= viewport.winfo_width()
    assert 0 <= y and y + widget.winfo_height() <= viewport.winfo_height()


@pytest.mark.parametrize("scale", [1, 1.5, 2])
def test_compact_roundtrip_preserves_native_keyboard_pointer_and_full_wrapped_text(tk_root, monkeypatch, scale):
    baseline = float(tk_root.tk.call("tk", "scaling"))
    tk_root.tk.call("tk", "scaling", baseline * scale)
    root = tk.Toplevel(tk_root)
    root.withdraw()
    theme.apply(root)
    scroll = ScrollableContent(root, padding=12)
    scroll.pack(fill="both", expand=True)
    worker = HeldWorker()
    selected, dialogs, errors = [], [], []
    monkeypatch.setattr(ui.model_inventory, "inventory_models", lambda: pytest.fail("Unexpected real scan"))
    monkeypatch.setattr("utterleaf.ui_feedback.messagebox.showinfo",
                        lambda title, message, **_kw: dialogs.append((title, message)))
    root.report_callback_exception = lambda *error: errors.append(error)
    view = ui.ModelInventoryPanel(scroll.body, worker=worker, selection_reason=lambda _entry: None,
                                  select_model=selected.append, is_closed=lambda: False)
    view.pack(fill="x")
    after = ttk.Button(root, text="Close")
    after.pack()
    try:
        root.geometry("430x560+20+20")
        root.deiconify()
        root.update()
        _load(view, worker, (INCOMPLETE, INSTALLED))
        for geometry in ("430x560", "1000x800", "430x560"):
            root.geometry(geometry)
            root.update()
            view.refresh_button.focus_force()
            root.update()
            view.refresh_button.event_generate("<Tab>")
            root.update()
            assert root.focus_get() is view.model_picker
            _visible(view.model_picker, scroll.canvas)
            view.model_picker.event_generate("<Tab>")
            root.update()
            assert root.focus_get() is view.use_button
            _visible(view.use_button, scroll.canvas)
            view.use_button.event_generate("<Shift-Tab>")
            root.update()
            assert root.focus_get() is view.model_picker
            assert view.selected_entry == INCOMPLETE
            # Escape cancels the native picker popup without editing the row.
            view.model_picker.event_generate("<Down>")
            root.update()
            view.model_picker.event_generate("<Escape>")
            root.update()
            assert view.model_picker.instate(["readonly"])
            # Traverse the full text using page keys, not synthetic canvas alignment.
            view.refresh_button.focus_force()
            root.update()
            view.refresh_button.event_generate("<Home>")
            root.update()
            labels = [view.snapshot_label, view.selected_label, view.size_label, view.size_hint]
            covered = {label: [] for label in labels}
            for _ in range(20):
                for label in labels:
                    assert label.winfo_width() >= label.winfo_reqwidth()
                    assert label.winfo_height() >= label.winfo_reqheight()
                    x = label.winfo_rootx() - scroll.canvas.winfo_rootx()
                    assert 0 <= x and x + label.winfo_width() <= scroll.canvas.winfo_width()
                    y = label.winfo_rooty() - scroll.canvas.winfo_rooty()
                    covered[label].append((max(0, -y), min(label.winfo_height(), scroll.canvas.winfo_height() - y)))
                if scroll.canvas.yview()[1] >= 1:
                    break
                view.refresh_button.event_generate("<Next>")
                root.update()
            for label, intervals in covered.items():
                end = 0
                for start, stop in sorted(intervals):
                    if stop <= start:
                        continue
                    assert start <= end
                    end = max(end, stop)
                assert end >= label.winfo_height()
            view.refresh_button.event_generate("<Tab>")
            root.update()
            view.model_picker.event_generate("<Tab>")
            root.update()
            _visible(view.use_button, scroll.canvas)
            view.use_button.event_generate("<space>")
            root.update()
            assert selected[-1] == view.selected_entry
            before = len(selected)
            button = view.use_button
            location = button.winfo_rootx(), button.winfo_rooty()
            x, y = button.winfo_width() // 2, button.winfo_height() // 2
            button.event_generate("<Enter>", x=x, y=y)
            button.event_generate("<ButtonPress-1>", x=x, y=y)
            root.update()
            assert (button.winfo_rootx(), button.winfo_rooty()) == location
            button.event_generate("<ButtonRelease-1>", x=x, y=y)
            root.update()
            assert len(selected) == before + 1
            assert view.selected_entry == INCOMPLETE
        # Recovery and its explicit Details remain reachable at the final compact size.
        worker.fail_start = True
        view.refresh()
        root.update()
        view.refresh_button.focus_force()
        root.update()
        for control in (view.model_picker, view.use_button, view.feedback.details_button):
            root.focus_get().event_generate("<Tab>")
            root.update()
            assert root.focus_get() is control
            _visible(control, scroll.canvas)
        _visible(view.feedback.label, scroll.canvas)
        view.feedback.details_button.event_generate("<space>")
        root.update()
        assert dialogs == [(view.feedback.problem + " — Details", technical_details(PRIVATE))]
        assert "PRIVATE-SENTINEL" not in _primary(view)
        assert len(worker.jobs) == 1 and errors == []
    finally:
        root.destroy()
        tk_root.tk.call("tk", "scaling", baseline)
