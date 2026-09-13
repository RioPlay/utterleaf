"""Adversarial clipboard identity checks; never touch the system clipboard."""

from types import SimpleNamespace

import pytest

from utterleaf import inject


@pytest.fixture
def clipboard(monkeypatch):
    monkeypatch.setattr(inject, "_use_windows_clipboard", lambda: False)
    state = SimpleNamespace(text="original", sequence=10, copies=[], sends=0)

    def copy(text):
        state.text = text
        state.sequence += 1
        state.copies.append(text)

    def send():
        state.sends += 1
        return True

    state.copy = copy
    monkeypatch.setattr(inject.pyperclip, "copy", copy)
    monkeypatch.setattr(inject.pyperclip, "paste", lambda: state.text)
    monkeypatch.setattr(inject, "_clipboard_sequence", lambda: state.sequence)
    monkeypatch.setattr(inject, "_send_paste", send)
    monkeypatch.setattr(inject, "_paste_settled", lambda: None)
    monkeypatch.setattr(inject.time, "sleep", lambda _: None)
    return state


def test_same_text_copied_before_delivery_cancels_shortcut(monkeypatch, clipboard):
    monkeypatch.setattr(inject.time, "sleep", lambda _: clipboard.copy("dictation"))
    assert inject.paste("dictation") == "fail"
    assert clipboard.sends == 0
    assert clipboard.copies == ["dictation", "dictation"]


def test_same_text_copied_during_delivery_is_not_restored(monkeypatch, clipboard):
    monkeypatch.setattr(inject, "_paste_settled", lambda: clipboard.copy("dictation"))
    assert inject.paste("dictation") == "pasted"
    assert clipboard.sends == 1
    assert clipboard.copies == ["dictation", "dictation"]


def test_copy_away_and_back_still_belongs_to_user(monkeypatch, clipboard):
    def settled():
        clipboard.copy("other copy")
        clipboard.copy("dictation")

    monkeypatch.setattr(inject, "_paste_settled", settled)
    assert inject.paste("dictation") == "pasted"
    assert clipboard.copies == ["dictation", "other copy", "dictation"]


def test_unchanged_clipboard_restores_old_text(clipboard):
    assert inject.paste("dictation") == "pasted"
    assert clipboard.copies == ["dictation", "original"]


def test_clipboard_identity_unavailable_does_not_restore(monkeypatch, clipboard):
    monkeypatch.setattr(inject, "_clipboard_sequence", lambda: 0)
    assert inject.paste("dictation") == "pasted"
    assert clipboard.copies == ["dictation"]


def test_identity_becoming_unavailable_cancels_delivery(monkeypatch, clipboard):
    monkeypatch.setattr(inject.time, "sleep", lambda _: setattr(clipboard, "sequence", 0))
    assert inject.paste("dictation") == "fail"
    assert clipboard.sends == 0


def test_identity_becoming_unavailable_after_delivery_skips_restore(monkeypatch, clipboard):
    monkeypatch.setattr(inject, "_paste_settled", lambda: setattr(clipboard, "sequence", 0))
    assert inject.paste("dictation") == "pasted"
    assert clipboard.copies == ["dictation"]


def test_identity_checked_after_restoration_read(monkeypatch, clipboard):
    reads = 0

    def paste():
        nonlocal reads
        reads += 1
        if reads == 3:
            clipboard.copy("dictation")
        return clipboard.text

    monkeypatch.setattr(inject.pyperclip, "paste", paste)
    assert inject.paste("dictation") == "pasted"
    assert clipboard.copies == ["dictation", "dictation"]


def test_failed_helper_keeps_recovery_and_does_not_log_content(monkeypatch, clipboard, caplog):
    def send():
        raise RuntimeError("private content must not be logged")

    monkeypatch.setattr(inject, "_send_paste", send)
    assert inject.paste("private dictation") == "fail"
    assert clipboard.copies == ["private dictation"]
    assert "private" not in caplog.text


def test_restore_disabled_never_reads_old_clipboard(monkeypatch, clipboard):
    reads = []
    monkeypatch.setattr(inject.pyperclip, "paste", lambda: reads.append(clipboard.text) or clipboard.text)
    assert inject.paste("dictation", restore_clipboard=False) == "pasted"
    assert reads == ["dictation"]
    assert clipboard.copies == ["dictation"]


@pytest.mark.parametrize("expected,current,unchanged", [
    (11, 11, True), (11, 12, False), (11, 0, False), (0, 0, False),
    (None, None, True), (11, None, False), (None, 11, False),
])
def test_identity_comparison(monkeypatch, expected, current, unchanged):
    monkeypatch.setattr(inject, "_clipboard_sequence", lambda: current)
    assert inject._clipboard_unchanged(expected) is unchanged


def test_non_windows_identity_does_not_load_native_api(monkeypatch):
    monkeypatch.setattr(inject.sys, "platform", "linux")
    assert inject._clipboard_sequence() is None


def test_windows_identity_uses_unsigned_sequence(monkeypatch):
    import ctypes

    function = lambda: 0xF0000000
    monkeypatch.setattr(inject.sys, "platform", "win32")
    monkeypatch.setattr(ctypes, "windll", SimpleNamespace(user32=SimpleNamespace(
        GetClipboardSequenceNumber=function)), raising=False)
    assert inject._clipboard_sequence() == 0xF0000000
    assert function.argtypes == []
    assert function.restype is ctypes.c_ulong


def test_windows_identity_failure_is_not_unsupported_platform(monkeypatch):
    import ctypes

    monkeypatch.setattr(inject.sys, "platform", "win32")
    monkeypatch.setattr(ctypes, "windll", SimpleNamespace(), raising=False)
    assert inject._clipboard_sequence() == 0
