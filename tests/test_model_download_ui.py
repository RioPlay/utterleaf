"""Download consent and worker lifecycle, with real Tk but no model/store I/O."""
import threading
from types import SimpleNamespace

import pytest

import capture_model_management as captures
from test_capture_auxiliary import working_tk_display
from utterleaf import model_setup
from utterleaf.settings_ui import messagebox


@pytest.fixture
def download(working_tk_display, monkeypatch):
    original_start = threading.Thread.start
    original_download = model_setup.run_download
    original_confirmation = messagebox.askyesno
    with captures.blocked_runtime() as runtime, captures._window(runtime, visible=False) as window:
        window.vars["model"].set("tiny")
        window.vars["language"].set("en")
        window.vars["device"].set("cpu")
        window.vars["allow_network"].set(False)
        window.root.update_idletasks()
        workers, calls = [], []

        def worker(action, done, *, daemon=True):
            workers.append(SimpleNamespace(action=action, done=done, daemon=daemon))

        def run(name, backend, *, cancel):
            calls.append((name, backend, cancel))

        monkeypatch.setattr(window, "_worker", worker)
        monkeypatch.setattr("utterleaf.model_setup.run_download", run)
        runtime.confirm = True
        try:
            yield SimpleNamespace(window=window, runtime=runtime, workers=workers, calls=calls,
                                  begin=lambda: captures.REAL_DOWNLOAD(window))
        finally:
            # Tests override some capture guards. Restore those overrides while
            # the guard contexts are still active, not after they have exited.
            monkeypatch.undo()
        assert runtime.violations == []
        assert runtime.blocked_actions == []
        assert runtime.ipc_commands == []
    assert threading.Thread.start is original_start
    assert model_setup.run_download is original_download
    assert messagebox.askyesno is original_confirmation


def assert_idle(window):
    assert not window.model_downloading
    assert str(window.model_cancel_button.cget("state")) == "disabled"
    assert str(window.model_download_button.cget("state")) == "normal"


def test_declined_confirmation_preserves_drafts_and_can_retry(download):
    window = download.window
    snapshot, baseline = window._snapshot(), window.baseline.copy()
    download.runtime.confirm = False
    download.begin()
    assert download.workers == [] and download.calls == []
    assert_idle(window)
    assert window._snapshot() == snapshot and window.baseline == baseline
    download.runtime.confirm = True
    download.begin()
    assert len(download.workers) == 1


def test_reentrant_confirmation_opens_only_one_prompt_and_worker(download, monkeypatch):
    confirmations = []

    def confirm(*_args, **_kwargs):
        confirmations.append(True)
        if len(confirmations) == 1:
            download.begin()
        return True

    monkeypatch.setattr("utterleaf.settings_ui.messagebox.askyesno", confirm)
    download.begin()
    assert confirmations == [True]
    assert len(download.workers) == 1
    assert download.calls == []


def test_close_during_confirmation_never_dispatches_after_consent_returns(download, monkeypatch):
    window = download.window
    window.baseline = window._snapshot()

    def confirm(*_args, **_kwargs):
        window.close()
        return True

    monkeypatch.setattr("utterleaf.settings_ui.messagebox.askyesno", confirm)
    download.begin()
    assert window.closed
    assert download.workers == [] and download.calls == []
    assert not window.model_downloading


def test_confirmation_exception_releases_attempt_for_retry(download, monkeypatch):
    def fail(*_args, **_kwargs):
        raise RuntimeError(captures.ERROR)

    monkeypatch.setattr("utterleaf.settings_ui.messagebox.askyesno", fail)
    # A failed native consent request is recovered, not allowed to escape.
    download.begin()
    assert not download.window.model_downloading
    text = download.window.model_action_status.get().lower()
    assert "confirmation could not open" in text and "no download" in text
    assert "/synthetic/private" not in text
    assert download.window.model_details_button.winfo_manager()
    assert download.workers == [] and download.calls == []
    monkeypatch.setattr("utterleaf.settings_ui.messagebox.askyesno", lambda *_a, **_k: True)
    download.begin()
    assert len(download.workers) == 1


def test_actual_thread_start_failure_recovers_and_retry_uses_non_daemon_worker(download, monkeypatch):
    window = download.window
    snapshot, baseline = window._snapshot(), window.baseline.copy()
    monkeypatch.setattr(window, "_worker", captures.SettingsWindow._worker.__get__(window))
    attempts = []

    def fail_start(thread):
        attempts.append(thread)
        raise RuntimeError(captures.ERROR)

    monkeypatch.setattr(threading.Thread, "start", fail_start)
    download.begin()
    assert len(attempts) == 1 and attempts[0].daemon is False
    assert_idle(window)
    text = window.model_action_status.get().lower()
    assert "could not start" in text and "no download" in text and "retry" in text
    assert "/synthetic/private" not in text
    assert window.model_details_button.winfo_manager()
    assert window._snapshot() == snapshot and window.baseline == baseline
    assert download.calls == [] and window.events.empty()

    held = []
    monkeypatch.setattr(threading.Thread, "start", lambda thread: held.append(thread))
    download.begin()
    assert len(held) == 1 and held[0].daemon is False
    assert window.model_downloading and not window.model_details_button.winfo_manager()
    held[0]._target()
    callback, value = window.events.get_nowait()
    callback(value)
    assert "installed" in window.model_action_status.get().lower()
    assert len(download.calls) == 1
    assert window._snapshot() == snapshot and window.baseline == baseline


def test_attempt_identity_is_immutable_across_consent_and_worker_form_changes(download, monkeypatch):
    window = download.window
    baseline = window.baseline.copy()

    def confirm(*_args, **_kwargs):
        window.vars["model"].set("base")
        window.vars["device"].set("npu")
        return True

    monkeypatch.setattr("utterleaf.settings_ui.messagebox.askyesno", confirm)
    download.begin()
    assert len(download.workers) == 1 and download.workers[0].daemon is False
    window.vars["model"].set("small")
    window.vars["device"].set("gpu")
    snapshot = window._snapshot()
    download.workers[0].action()
    download.workers[0].done(None)
    assert [(name, backend) for name, backend, _cancel in download.calls] == [("tiny.en", "ctranslate2")]
    assert "Tiny English installed" in window.model_action_status.get()
    assert "Small English" in window.model_status.get()
    assert window._snapshot() == snapshot and window.baseline == baseline
    assert window.vars["allow_network"].get() is False


def test_busy_attempt_ignores_second_download_and_cancel_keeps_worker_until_completion(download):
    window = download.window
    download.begin()
    cancel = window.model_download_cancel
    download.begin()
    assert len(download.workers) == 1 and len(download.runtime.dialogs) == 1
    window.cancel_model_download()
    assert window.model_downloading and cancel.is_set()
    assert str(window.model_download_button.cget("state")) == "disabled"
    download.workers[0].done(RuntimeError(captures.ERROR))
    assert_idle(window)
    assert "cancelled" in window.model_action_status.get().lower()
    assert not window.model_details_button.winfo_manager()


def test_late_cancel_does_not_relabel_success(download):
    window = download.window
    download.begin()
    download.workers[0].action()
    window.cancel_model_download()
    download.workers[0].done(None)
    assert not window.model_downloading
    assert "installed" in window.model_action_status.get().lower()
    assert "cancel" not in window.model_action_status.get().lower()
    assert not window.model_details_button.winfo_manager()


@pytest.mark.parametrize("first_result", [None, RuntimeError("synthetic failed attempt")])
def test_duplicate_terminal_callback_cannot_change_finished_result(download, first_result):
    window = download.window
    download.begin()
    done = download.workers[0].done
    done(first_result)
    before = window.model_action_status.get(), window.model_details_button.winfo_manager()
    done(RuntimeError("stale private exception"))
    assert (window.model_action_status.get(), window.model_details_button.winfo_manager()) == before
    assert not window.model_downloading


def test_stale_callback_cannot_unlock_or_overwrite_newer_attempt(download):
    window = download.window
    download.begin()
    old_done = download.workers[0].done
    old_done(RuntimeError(captures.ERROR))
    download.begin()
    current_cancel = window.model_download_cancel
    status = window.model_action_status.get()
    old_done(None)
    assert window.model_downloading and window.model_download_cancel is current_cancel
    assert window.model_action_status.get() == status
    assert str(window.model_cancel_button.cget("state")) == "normal"
    assert str(window.model_download_button.cget("state")) == "disabled"
    assert not window.model_details_button.winfo_manager()
    download.workers[1].done(None)
    assert "installed" in window.model_action_status.get().lower()


def test_close_cancels_consented_work_and_late_callback_is_inert(download):
    window = download.window
    download.begin()
    worker = download.workers[0]
    cancel = window.model_download_cancel
    assert worker.daemon is False
    window.close()
    assert window.closed and cancel.is_set()
    worker.action()
    assert download.calls[0][2] is cancel
    worker.done(None)
    worker.done(RuntimeError(captures.ERROR))
    window.close()


def test_destroyed_window_ignores_queued_completion(download):
    window = download.window
    download.begin()
    # The deliberate external destroy bypasses close(); discard unrelated Tk
    # timers so this lifecycle probe cannot leak callbacks into the next root.
    window.root.after_cancel(window.poll_id)
    if window._page_reset is not None:
        window.root.after_cancel(window._page_reset)
    window.root.destroy()
    download.workers[0].done(None)
    download.workers[0].done(RuntimeError(captures.ERROR))
