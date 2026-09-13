"""Windows delivery contracts using an in-memory clipboard, never the OS clipboard."""
from types import SimpleNamespace

import pytest

from utterleaf import inject, windows_clipboard as wc


@pytest.fixture
def clipboard(monkeypatch):
    state = SimpleNamespace(text="previous", sequence=10, reads=0, writes=[],
                            sends=0, focus=123, cancelled=False)

    def snapshot(**_kwargs):
        state.reads += 1
        return wc.Result("ok", state.text, state.sequence)

    def write(text, *, expected_sequence=None, cancel=None):
        state.writes.append((text, expected_sequence))
        if cancel is not None and cancel():
            return wc.Result("cancelled")
        if expected_sequence is not None and expected_sequence != state.sequence:
            return wc.Result("changed", sequence=state.sequence)
        state.text = text
        state.sequence += 1
        return wc.Result("ok", sequence=state.sequence)

    def send(*, cancel=None, target=None):
        if cancel is not None and cancel():
            return "cancelled"
        if target is not None and target != state.focus:
            return "target"
        state.sends += 1
        return "success"

    state.write = write
    state.snapshot = snapshot
    monkeypatch.setattr(inject, "_use_windows_clipboard", lambda: True)
    monkeypatch.setattr(inject, "foreground_id", lambda: state.focus)
    monkeypatch.setattr(inject, "_clipboard_sequence", lambda: state.sequence)
    monkeypatch.setattr(inject, "_send_paste", send)
    monkeypatch.setattr(inject, "_paste_settled", lambda **_kwargs: False)
    monkeypatch.setattr(inject.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(wc, "snapshot", snapshot)
    monkeypatch.setattr(wc, "write", write)
    monkeypatch.setattr(inject.pyperclip, "paste", lambda: pytest.fail("Unbounded clipboard read"))
    monkeypatch.setattr(inject.pyperclip, "copy", lambda _text: pytest.fail("Unbounded clipboard write"))
    return state


def test_confirmed_paste_uses_one_snapshot_and_conditional_restore(clipboard):
    assert inject.paste("dictation", target=123) == "pasted"
    assert clipboard.reads == 1
    assert clipboard.writes == [("dictation", 10), ("previous", 11)]
    assert clipboard.sends == 1
    assert clipboard.text == "previous"


def test_restoration_disabled_performs_no_clipboard_data_reads(clipboard):
    assert inject.paste("dictation", restore_clipboard=False, target=123) == "pasted"
    assert clipboard.reads == 0
    assert clipboard.writes == [("dictation", None)]


def test_snapshot_timeout_skips_restoration_and_keeps_delivery(monkeypatch, clipboard):
    monkeypatch.setattr(wc, "snapshot", lambda **_kwargs: wc.Result("unavailable"))
    assert inject.paste("dictation", target=123) == "pasted"
    assert clipboard.writes == [("dictation", None)]
    assert clipboard.sends == 1


def test_new_copy_between_snapshot_and_write_prevents_overwrite(monkeypatch, clipboard):
    def write(text, **kwargs):
        clipboard.text = "new user copy"
        clipboard.sequence += 1
        return clipboard.write(text, **kwargs)
    monkeypatch.setattr(wc, "write", write)
    assert inject.paste("dictation", target=123) == "fail"
    assert clipboard.text == "new user copy"
    assert clipboard.sends == 0


def test_same_text_copy_before_dispatch_is_a_new_owner(monkeypatch, clipboard):
    monkeypatch.setattr(inject.time, "sleep", lambda _: setattr(clipboard, "sequence", 12))
    assert inject.paste("dictation", target=123) == "fail"
    assert clipboard.sends == 0
    assert clipboard.writes == [("dictation", 10)]


def test_final_dispatch_guard_checks_clipboard_again(monkeypatch, clipboard):
    def send(*, cancel, target):
        clipboard.sequence += 1
        assert cancel()
        return "cancelled"
    monkeypatch.setattr(inject, "_send_paste", send)
    assert inject.paste("dictation", target=123) == "fail"
    assert clipboard.sends == 0


def test_focus_moving_during_copy_keeps_recovery_without_shortcut(monkeypatch, clipboard):
    def write(text, **kwargs):
        result = clipboard.write(text, **kwargs)
        clipboard.focus = 456
        return result
    monkeypatch.setattr(wc, "write", write)
    assert inject.paste("dictation", target=123) == "clipboard"
    assert clipboard.text == "dictation"
    assert clipboard.sends == 0


def test_already_moved_focus_uses_bounded_recovery_copy_only(clipboard):
    clipboard.focus = 456
    assert inject.paste("dictation", target=123) == "clipboard"
    assert clipboard.reads == 0
    assert clipboard.writes == [("dictation", None)]
    assert clipboard.sends == 0


@pytest.mark.parametrize("status", ["unavailable", "changed", "uncertain"])
def test_unconfirmed_copy_never_dispatches_or_retries(monkeypatch, clipboard, status):
    calls = []
    monkeypatch.setattr(wc, "write", lambda text, **_kwargs: calls.append(text) or wc.Result(status))
    assert inject.paste("dictation", target=123) == "fail"
    assert calls == ["dictation"]
    assert clipboard.sends == 0


def test_cancel_before_any_work_starts_no_helper(clipboard):
    assert inject.paste("dictation", cancel=lambda: True) == "cancelled"
    assert clipboard.reads == 0 and clipboard.writes == []


def test_cancel_during_snapshot_never_writes(monkeypatch, clipboard):
    def snapshot(**_kwargs):
        clipboard.cancelled = True
        return wc.Result("unavailable")
    monkeypatch.setattr(wc, "snapshot", snapshot)
    assert inject.paste("dictation", cancel=lambda: clipboard.cancelled) == "cancelled"
    assert clipboard.writes == []


def test_cancel_after_copy_starts_no_restore_or_shortcut(monkeypatch, clipboard):
    def write(text, **kwargs):
        result = clipboard.write(text, **kwargs)
        clipboard.cancelled = True
        return result
    monkeypatch.setattr(wc, "write", write)
    assert inject.paste("dictation", target=123, cancel=lambda: clipboard.cancelled) == "cancelled"
    assert clipboard.writes == [("dictation", 10)]
    assert clipboard.text == "dictation"
    assert clipboard.sends == 0


@pytest.mark.parametrize("dispatch", ["uncertain", "failed"])
def test_shortcut_failure_never_restores_or_retries(monkeypatch, clipboard, dispatch):
    calls = []
    monkeypatch.setattr(inject, "_send_paste", lambda **kwargs: calls.append(kwargs) or dispatch)
    assert inject.paste("dictation", target=123) == ("uncertain" if dispatch == "uncertain" else "fail")
    assert len(calls) == 1
    assert clipboard.writes == [("dictation", 10)]


def test_cancel_racing_shortcut_is_uncertain(monkeypatch, clipboard):
    def send(**_kwargs):
        clipboard.cancelled = True
        return "success"
    monkeypatch.setattr(inject, "_send_paste", send)
    assert inject.paste("dictation", target=123, cancel=lambda: clipboard.cancelled) == "uncertain"
    assert clipboard.writes == [("dictation", 10)]


def test_same_text_copy_after_paste_prevents_restoration(monkeypatch, clipboard):
    def settled(**_kwargs):
        clipboard.sequence += 1
        return False
    monkeypatch.setattr(inject, "_paste_settled", settled)
    assert inject.paste("dictation", target=123) == "pasted"
    assert clipboard.text == "dictation"
    assert clipboard.writes == [("dictation", 10), ("previous", 11)]


def test_unconfirmed_restoration_does_not_retry_paste(monkeypatch, clipboard):
    def write(text, **kwargs):
        if clipboard.sends:
            return wc.Result("uncertain")
        return clipboard.write(text, **kwargs)
    monkeypatch.setattr(wc, "write", write)
    assert inject.paste("dictation", target=123) == "uncertain"
    assert clipboard.sends == 1


def test_manual_copy_uses_bounded_write_without_snapshot(clipboard):
    assert inject.copy_text("manual recovery")
    assert clipboard.reads == 0 and clipboard.sends == 0
    assert clipboard.writes == [("manual recovery", None)]


def test_manual_copy_cannot_claim_unconfirmed_write(monkeypatch, clipboard):
    monkeypatch.setattr(wc, "write", lambda *_args, **_kwargs: wc.Result("uncertain"))
    assert not inject.copy_text("manual recovery")


def test_private_cli_route_runs_only_the_worker(monkeypatch):
    from utterleaf import __main__
    calls = []
    monkeypatch.setattr(wc, "run_worker", lambda: calls.append(True) or 2)
    assert __main__.main(["--clipboard-worker"]) == 2
    assert calls == [True]


@pytest.mark.parametrize("extra", [["--doctor"], ["--speech-review"], ["--download-model"], ["--polish", "text"], ["--settings"]])
def test_private_cli_rejects_other_actions_before_worker(monkeypatch, extra):
    from utterleaf import __main__
    monkeypatch.setattr(wc, "run_worker", lambda: pytest.fail("Mixed action reached clipboard"))
    with pytest.raises(SystemExit) as exc:
        __main__.main(["--clipboard-worker", *extra])
    assert exc.value.code == 2
