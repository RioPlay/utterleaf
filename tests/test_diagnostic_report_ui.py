"""Guarded diagnostic/report recovery: no real probes, exports or preferences."""

from pathlib import Path
import tkinter as tk
import unicodedata

import pytest

from test_settings_ui import tk_root, window
from utterleaf.config import Config
from utterleaf.model_setup import ModelAvailability
from utterleaf.settings_ui import SettingsWindow


def _blocked(*_args, **_kwargs):
    pytest.fail("Unexpected external operation in a diagnostic UI test")


@pytest.fixture(autouse=True)
def report_guards(monkeypatch):
    dialogs = []
    monkeypatch.setattr("utterleaf.model_setup.inspect_model",
                        lambda name, backend: ModelAvailability(name, backend, "missing", None))
    monkeypatch.setattr("utterleaf.settings_ui.load", Config)
    monkeypatch.setattr("utterleaf.settings.save", _blocked)
    monkeypatch.setattr("utterleaf.model_setup.run_download", _blocked)
    monkeypatch.setattr("utterleaf.hardware.generate_diagnostic_report", _blocked)
    monkeypatch.setattr("utterleaf.hardware.cuda_setup_plan", _blocked)
    monkeypatch.setattr("utterleaf.settings_ui.filedialog.asksaveasfilename", _blocked)
    monkeypatch.setattr("utterleaf.settings_ui.messagebox.showerror", _blocked)
    monkeypatch.setattr("utterleaf.ui_feedback.messagebox.showinfo",
                        lambda *a, **k: dialogs.append((a, k)))
    monkeypatch.setattr(Path, "write_text", _blocked)
    return dialogs


@pytest.fixture
def pending(window, monkeypatch):
    operations = []
    monkeypatch.setattr(window, "_worker", lambda action, done, **kwargs: operations.append((action, done)))
    return operations


def _seed_report(window, report="Previously reviewed report\nKeep this selected line"):
    window.report = report
    text = window.diagnostic_text
    text.configure(state="normal")
    text.delete("1.0", "end")
    text.insert("1.0", report)
    text.tag_add("sel", "2.0", "2.4")
    text.mark_set("insert", "2.4")
    text.configure(state="disabled")
    window.export_button.configure(state="normal")


def _preview(window):
    text = window.diagnostic_text
    return (window.report, text.get("1.0", "end-1c"),
            tuple(map(str, text.tag_ranges("sel"))), text.index("insert"))


def _assert_checks_enabled(window):
    assert not window.diagnostic_button.instate(["disabled"])
    assert not window.cuda_button.instate(["disabled"])


@pytest.mark.parametrize("action", ["diagnostics", "cuda_setup"])
def test_report_checks_share_one_operation_and_keep_reviewed_content(window, pending, action):
    _seed_report(window)
    before = _preview(window)
    window.vars["hotkey"].set("f8")
    draft = window._snapshot()
    getattr(window, action)()
    operation = window._report_operation
    assert operation is not None
    assert window.diagnostic_button.instate(["disabled"])
    assert window.cuda_button.instate(["disabled"])
    assert not window.export_button.instate(["disabled"])
    window.diagnostics()
    window.cuda_setup()
    assert len(pending) == 1
    assert window._report_operation is operation
    assert _preview(window) == before
    assert window._snapshot() == draft
    pending[0][1]("New successful report")
    assert window._report_operation is None
    _assert_checks_enabled(window)
    assert window.report == "New successful report"
    assert window.diagnostic_text.get("1.0", "end-1c") == window.report
    assert str(window.diagnostic_text.cget("state")) == "disabled"
    assert not window.export_button.instate(["disabled"])
    assert window._snapshot() == draft


@pytest.mark.parametrize("action", ["diagnostics", "cuda_setup"])
@pytest.mark.parametrize("has_report", [False, True])
def test_failed_check_preserves_preview_selection_and_drafts(window, pending, report_guards, action, has_report):
    if has_report:
        _seed_report(window)
    before = _preview(window)
    window.vars["model"].set("base")
    draft = window._snapshot()
    getattr(window, action)()
    pending[0][1](RuntimeError("private diagnostic path C:/private-account/report"))
    assert _preview(window) == before
    assert window._snapshot() == draft
    assert window._report_operation is None
    _assert_checks_enabled(window)
    assert window.export_button.instate(["disabled"]) is (not has_report)
    primary = window.report_status.get()
    expected_impact = "Previous report retained" if has_report else "No report is available"
    assert expected_impact in primary
    assert "private" not in primary
    assert "retry" in primary.lower() or "again" in primary.lower()
    assert report_guards == []
    assert not window.report_feedback.details_button.instate(["disabled"])
    window.report_feedback.details_button.invoke()
    assert len(report_guards) == 1
    assert "private diagnostic path" in report_guards[0][0][1]
    assert report_guards[0][1]["parent"] == window.root


@pytest.mark.parametrize("action", ["diagnostics", "cuda_setup"])
def test_worker_start_failure_restores_controls_and_preserves_report(window, monkeypatch, action):
    _seed_report(window)
    before = _preview(window)

    def fail_start(*_args, **_kwargs):
        raise RuntimeError("private thread start failure")

    monkeypatch.setattr(window, "_worker", fail_start)
    getattr(window, action)()
    assert window._report_operation is None
    _assert_checks_enabled(window)
    assert not window.export_button.instate(["disabled"])
    assert _preview(window) == before
    assert "Previous report retained" in window.report_status.get()
    assert "private" not in window.report_status.get()
    assert "private thread start failure" in window.report_feedback.details


def test_diagnostics_uses_saved_configuration_without_applying_drafts(window, pending, monkeypatch):
    saved = Config(model="tiny", device="cpu", language="en", allow_network=False)
    observed = []
    monkeypatch.setattr("utterleaf.settings_ui.load", lambda: saved)
    monkeypatch.setattr("utterleaf.hardware.generate_diagnostic_report",
                        lambda cfg: observed.append(cfg) or "Saved configuration report")
    window.vars["model"].set("base")
    window.vars["device"].set("gpu")
    draft = window._snapshot()
    window.diagnostics()
    action, done = pending[0]
    result = action()
    assert observed == [saved]
    assert observed[0] is saved
    done(result)
    assert window.report == "Saved configuration report"
    assert window._snapshot() == draft


def test_cuda_action_only_collects_existing_guidance(window, pending, monkeypatch):
    calls = []
    monkeypatch.setattr("utterleaf.settings_ui.load", _blocked)
    monkeypatch.setattr("utterleaf.hardware.cuda_setup_plan", lambda: calls.append("guidance") or ["First", "Second"])
    window.cuda_setup()
    action, done = pending[0]
    done(action())
    assert calls == ["guidance"]
    assert window.report == "First\nSecond"


def test_report_details_are_bounded_explicit_and_retry_clears_them(window, pending, report_guards):
    window.diagnostics()
    pending[0][1](RuntimeError("private marker\x00\x1b\u202e\t" + "x" * 6000 + "\nline" * 30))
    assert report_guards == []
    assert "private marker" not in window.report_status.get()
    details = window.report_feedback.details
    assert len(details) < 2200
    assert len(details.splitlines()) <= 13
    assert all(char == "\n" or unicodedata.category(char) not in {"Cc", "Cf", "Cs"} for char in details)
    window.report_feedback.details_button.invoke()
    assert report_guards[0][0][1] == details
    window.diagnostics()
    assert window.report_feedback.details == ""
    assert window.report_feedback.details_button.instate(["disabled"])
    assert not window.report_feedback.details_button.winfo_manager()
    pending[1][1]("Recovered report")
    assert window.report_feedback.details == ""
    assert window.report == "Recovered report"


def test_stale_report_callback_cannot_replace_a_newer_operation(window, pending):
    window.diagnostics()
    old_done = pending[0][1]
    old_done("First report")
    window.cuda_setup()
    current = window._report_operation
    status = window.report_status.get()
    before = _preview(window)
    old_done(RuntimeError("private stale failure"))
    old_done("stale replacement")
    assert window._report_operation is current
    assert window.report_status.get() == status
    assert _preview(window) == before
    assert window.diagnostic_button.instate(["disabled"])
    pending[1][1]("Current report")
    assert window.report == "Current report"


def test_closed_report_callbacks_and_public_actions_do_not_touch_destroyed_tk(window, pending):
    window.diagnostics()
    done = pending[0][1]
    window.close()
    assert window.closed
    done("late report")
    done(RuntimeError("late failure"))
    window.diagnostics()
    window.cuda_setup()
    window.export_report()
    assert len(pending) == 1


@pytest.mark.parametrize("write_fails", [False, True])
def test_export_snapshots_reviewed_report_before_modal_picker(window, pending, monkeypatch, write_fails):
    _seed_report(window)
    reviewed = window.report
    window.diagnostics()
    writes = []

    def choose(**kwargs):
        assert kwargs["parent"] == window.root
        pending[0][1]("A report completed while the native picker was open")
        return "synthetic-report.txt"

    def write(path, text, **kwargs):
        writes.append((str(path), text, kwargs))
        if write_fails:
            raise OSError("private earlier-report write failure")

    monkeypatch.setattr("utterleaf.settings_ui.filedialog.asksaveasfilename", choose)
    monkeypatch.setattr(Path, "write_text", write)
    window.export_report()
    assert writes == [("synthetic-report.txt", reviewed, {"encoding": "utf-8"})]
    assert window.report == "A report completed while the native picker was open"
    assert window.diagnostic_text.get("1.0", "end-1c") == window.report
    primary = window.report_status.get()
    if write_fails:
        assert "Couldn't save earlier report" in primary
        assert "chosen file may be incomplete" in primary
        assert "A newer report is shown" in primary
        assert "Review it, then retry Save report" in primary
        assert "private" not in primary
    else:
        assert primary == "Earlier report saved. A newer report is shown; review it before saving or sharing."
    assert not window._exporting_report
    _assert_checks_enabled(window)


def test_picker_cancel_keeps_existing_recovery_details_and_report(window, monkeypatch):
    _seed_report(window)
    window.report_feedback.error("Previous failure", "Report retained.", "Retry.", "private previous failure")
    before = _preview(window)
    status, details = window.report_status.get(), window.report_feedback.details
    monkeypatch.setattr("utterleaf.settings_ui.filedialog.asksaveasfilename", lambda **k: "")
    window.export_report()
    assert _preview(window) == before
    assert window.report_status.get() == status
    assert window.report_feedback.details == details
    assert not window._exporting_report
    assert not window.export_button.instate(["disabled"])


@pytest.mark.parametrize("failure_point", ["picker", "write"])
def test_report_export_failure_preserves_report_and_uses_explicit_details(window, monkeypatch, report_guards, failure_point):
    _seed_report(window)
    before = _preview(window)
    draft = window._snapshot()

    def fail(*_args, **_kwargs):
        raise OSError("private destination C:/private-account/report.txt")

    if failure_point == "picker":
        monkeypatch.setattr("utterleaf.settings_ui.filedialog.asksaveasfilename", fail)
    else:
        monkeypatch.setattr("utterleaf.settings_ui.filedialog.asksaveasfilename", lambda **k: "synthetic-report.txt")
        monkeypatch.setattr(Path, "write_text", fail)
    window.export_report()
    assert _preview(window) == before
    assert window._snapshot() == draft
    assert not window._exporting_report
    _assert_checks_enabled(window)
    assert not window.export_button.instate(["disabled"])
    assert report_guards == []
    assert "private" not in window.report_status.get()
    assert "retry" in window.report_status.get().lower() or "again" in window.report_status.get().lower()
    if failure_point == "write":
        assert "incomplete" in window.report_status.get().lower()
    window.report_feedback.details_button.invoke()
    assert "private destination" in report_guards[0][0][1]


def test_closing_from_native_picker_prevents_a_report_write(window, monkeypatch):
    _seed_report(window)

    def choose(**_kwargs):
        window.close()
        return "must-not-be-written.txt"

    monkeypatch.setattr("utterleaf.settings_ui.filedialog.asksaveasfilename", choose)
    window.export_report()
    assert window.closed


def test_export_blocks_reentrancy_and_new_checks_while_picker_is_open(window, pending, monkeypatch):
    _seed_report(window)
    calls, writes = [], []

    def choose(**_kwargs):
        calls.append("picker")
        assert window._exporting_report
        assert window.diagnostic_button.instate(["disabled"])
        assert window.cuda_button.instate(["disabled"])
        assert window.export_button.instate(["disabled"])
        window.export_report()
        window.diagnostics()
        window.cuda_setup()
        return "synthetic-report.txt"

    monkeypatch.setattr("utterleaf.settings_ui.filedialog.asksaveasfilename", choose)
    monkeypatch.setattr(Path, "write_text", lambda *a, **k: writes.append(a))
    window.export_report()
    assert calls == ["picker"]
    assert len(writes) == 1
    assert pending == []
    assert not window._exporting_report


def test_export_without_a_report_never_opens_a_picker(window):
    assert window.report == ""
    window.export_report()


@pytest.mark.parametrize("scale", [1.0, 1.5, 2.0])
@pytest.mark.parametrize("failure", ["diagnostics", "cuda_setup", "write", "earlier_write"])
def test_report_error_group_fits_compact_view_without_moving_focus(tk_root, monkeypatch, scale, failure):
    monkeypatch.setattr("utterleaf.settings_ui.startup_enabled", lambda: False)
    monkeypatch.setattr("utterleaf.settings_ui.dictionary_text", lambda: "utter leaf = Utterleaf")
    baseline = float(tk_root.tk.call("tk", "scaling"))
    root = tk.Toplevel(tk_root)
    app = None
    try:
        root.tk.call("tk", "scaling", baseline * scale)
        app = SettingsWindow(root, Config(), background=False)
        root.geometry("760x560")
        app.vars["hotkey"].set("f8")
        app.navigate("Help & diagnostics")
        root.update()
        _seed_report(app)
        pending = []
        monkeypatch.setattr(app, "_worker", lambda action, done, **k: pending.append(done))
        focused = app.nav["Help & diagnostics"]
        focused.focus_force()
        root.update()
        draft, before = app._snapshot(), _preview(app)
        expected_preview = [before]
        if failure in {"diagnostics", "cuda_setup"}:
            getattr(app, failure)()
            pending[0](RuntimeError("synthetic diagnostic failure"))
        else:
            if failure == "earlier_write":
                app.diagnostics()

            def choose(**_kwargs):
                if failure == "earlier_write":
                    pending[0]("Newer report from the pending check\nNewer report remains visible")
                    expected_preview[0] = _preview(app)
                return "synthetic-report.txt"

            def fail_write(*_args, **_kwargs):
                raise OSError("synthetic report-write failure")

            monkeypatch.setattr("utterleaf.settings_ui.filedialog.asksaveasfilename", choose)
            monkeypatch.setattr(Path, "write_text", fail_write)
            app.export_report()
            assert "incomplete" in app.report_status.get().lower()
        root.update()
        assert root.focus_get() == focused
        assert app._snapshot() == draft
        assert _preview(app) == expected_preview[0]

        def assert_feedback_visible():
            left, top = app.canvas.winfo_rootx(), app.canvas.winfo_rooty()
            right, bottom = left + app.canvas.winfo_width(), top + app.canvas.winfo_height()
            for control in (app.report_feedback, app.report_feedback.label, app.report_feedback.details_button):
                assert control.winfo_ismapped()
                assert control.winfo_height() >= control.winfo_reqheight()
                assert left <= control.winfo_rootx()
                assert control.winfo_rootx() + control.winfo_width() <= right
                assert top <= control.winfo_rooty()
                assert control.winfo_rooty() + control.winfo_height() <= bottom

        assert_feedback_visible()
        app.canvas.yview_moveto(0)
        root.update()
        app.report_feedback.details_button.focus_force()
        root.update()
        assert root.focus_get() == app.report_feedback.details_button
        assert_feedback_visible()
        assert app._snapshot() == draft
    finally:
        if app is not None:
            app.closed = True
            root.after_cancel(app.poll_id)
            if app._page_reset is not None:
                root.after_cancel(app._page_reset)
        root.destroy()
        tk_root.tk.call("tk", "scaling", baseline)


def test_report_details_first_mouse_click_does_not_move_button_or_miss_action(window, pending, report_guards):
    window.root.deiconify()
    window.root.geometry("760x560")
    window.navigate("Help & diagnostics")
    window.root.update()
    window.diagnostics()
    pending[0][1](RuntimeError("private first-click details"))
    window.root.update()
    window.nav["Help & diagnostics"].focus_force()
    window.root.update()
    button = window.report_feedback.details_button
    canvas = window.canvas
    bounds = canvas.bbox("all")
    region = bounds[3] - bounds[1]
    desired = canvas.yview()[0] * region + button.winfo_rooty() - canvas.winfo_rooty() - 4
    canvas.yview_moveto(desired / region)
    window.root.update()
    assert window.report_feedback.label.winfo_rooty() < canvas.winfo_rooty()
    assert button.winfo_rooty() >= canvas.winfo_rooty()
    assert button.winfo_rooty() + button.winfo_height() <= canvas.winfo_rooty() + canvas.winfo_height()
    before_scroll = canvas.yview()
    before_bounds = (button.winfo_rootx(), button.winfo_rooty(), button.winfo_width(), button.winfo_height())
    screen_x = button.winfo_rootx() + button.winfo_width() // 2
    screen_y = button.winfo_rooty() + button.winfo_height() // 2
    button.event_generate("<Enter>")
    button.event_generate("<ButtonPress-1>", x=screen_x - button.winfo_rootx(),
                          y=screen_y - button.winfo_rooty(), rootx=screen_x, rooty=screen_y)
    window.root.update()
    after_press_scroll = canvas.yview()
    after_press_bounds = (button.winfo_rootx(), button.winfo_rooty(), button.winfo_width(), button.winfo_height())
    # Release at the original screen point. A moving button loses the pointer;
    # reproduce Tk's leave-state transition rather than clicking its new place.
    if not (button.winfo_rootx() <= screen_x < button.winfo_rootx() + button.winfo_width()
            and button.winfo_rooty() <= screen_y < button.winfo_rooty() + button.winfo_height()):
        button.event_generate("<Leave>")
    button.event_generate("<ButtonRelease-1>", x=screen_x - button.winfo_rootx(),
                          y=screen_y - button.winfo_rooty(), rootx=screen_x, rooty=screen_y)
    window.root.update()
    assert after_press_scroll == before_scroll
    assert after_press_bounds == before_bounds
    assert len(report_guards) == 1
    assert "private first-click details" in report_guards[0][0][1]


def test_other_page_report_completion_does_not_navigate_or_scroll(window, pending):
    window.root.deiconify()
    window.root.geometry("760x560")
    window.navigate("Help & diagnostics")
    window.root.update()
    window.diagnostics()
    window.navigate("Vocabulary")
    window.root.update()
    focused = window.nav["Vocabulary"]
    focused.focus_force()
    window.root.update()
    before = window.canvas.yview()
    pending[0][1](RuntimeError("synthetic background completion"))
    window.root.update()
    assert window.pages["Vocabulary"].winfo_ismapped()
    assert not window.pages["Help & diagnostics"].winfo_ismapped()
    assert window.root.focus_get() == focused
    assert window.canvas.yview() == before


def test_successful_report_stays_read_only_and_supports_tab_traversal(window, pending):
    window.root.deiconify()
    window.navigate("Help & diagnostics")
    window.root.update()
    window.diagnostics()
    pending[0][1]("Safe synthetic report\nSecond line")
    window.root.update()
    text = window.diagnostic_text
    text.focus_force()
    window.root.update()
    before = text.get("1.0", "end-1c")
    assert str(text.cget("state")) == "disabled"
    text.event_generate("<KeyPress-x>")
    text.event_generate("<KeyRelease-x>")
    following = text.tk_focusNext()
    text.event_generate("<Tab>")
    window.root.update()
    assert window.root.focus_get() == following
    following.event_generate("<Shift-Tab>")
    window.root.update()
    assert window.root.focus_get() == text
    assert text.get("1.0", "end-1c") == before
