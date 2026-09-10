import subprocess
import sys

import pytest

from utterleaf import inject
from utterleaf.inject import same_target


@pytest.fixture(autouse=True)
def stable_clipboard_identity(monkeypatch):
    # These tests simulate clipboard contents. Their identity must also be
    # simulated, rather than depending on a CI runner's native clipboard.
    # Changes/unavailable identities have dedicated adversarial tests.
    monkeypatch.setattr(inject, "_clipboard_sequence", lambda: 1)


def test_same_target_treats_empty_as_ok() -> None:
    assert same_target(None, 123) is True
    assert same_target(0, 0) is True


def test_same_target_rejects_other_window() -> None:
    assert same_target(1, 2) is False
    assert same_target(5, 5) is True


def test_paste_restores_clipboard_when_send_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    copies = []
    monkeypatch.setattr(inject.pyperclip, "paste", lambda: copies[-1] if copies else "old")
    monkeypatch.setattr(inject.pyperclip, "copy", lambda text: copies.append(text))
    monkeypatch.setattr(inject.time, "sleep", lambda _s: None)
    monkeypatch.setattr(inject, "_send_paste", lambda: True)
    assert inject.paste("hello") == "pasted"
    assert copies == ["hello", "old"]


def test_paste_preserves_copy_made_during_delivery(monkeypatch):
    clipboard = ["old"]
    monkeypatch.setattr(inject.pyperclip, "paste", lambda: clipboard[-1])
    monkeypatch.setattr(inject.pyperclip, "copy", clipboard.append)
    monkeypatch.setattr(inject, "_send_paste", lambda: True)
    monkeypatch.setattr(inject, "_paste_settled", lambda: clipboard.append("new user copy"))
    assert inject.paste("dictation") == "pasted"
    assert clipboard == ["old", "dictation", "new user copy"]


def test_paste_does_not_erase_text_when_old_clipboard_unreadable(monkeypatch):
    copies = []
    def unavailable():
        if copies:
            return copies[-1]
        raise RuntimeError("Clipboard busy")
    monkeypatch.setattr(inject.pyperclip, "paste", unavailable)
    monkeypatch.setattr(inject.pyperclip, "copy", copies.append)
    monkeypatch.setattr(inject, "_send_paste", lambda: True)
    monkeypatch.setattr(inject, "_paste_settled", lambda: None)
    assert inject.paste("dictation") == "pasted"
    assert copies == ["dictation"]


def test_paste_keeps_clipboard_when_send_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    copies = []
    monkeypatch.setattr(inject.pyperclip, "paste", lambda: copies[-1] if copies else "old")
    monkeypatch.setattr(inject.pyperclip, "copy", lambda text: copies.append(text))
    monkeypatch.setattr(inject.time, "sleep", lambda _s: None)
    monkeypatch.setattr(inject, "_send_paste", lambda: False)
    assert inject.paste("hello") == "fail"
    assert copies == ["hello"]


def test_paste_rechecks_focus_after_settling(monkeypatch):
    clipboard = ["old"]
    focus = [123]
    monkeypatch.setattr(inject, "foreground_id", lambda: focus[0])
    monkeypatch.setattr(inject.pyperclip, "paste", lambda: clipboard[-1])
    monkeypatch.setattr(inject.pyperclip, "copy", clipboard.append)
    monkeypatch.setattr(inject.time, "sleep", lambda _: focus.__setitem__(0, 456))
    monkeypatch.setattr(inject, "_send_paste", lambda: pytest.fail("Wrong-window paste"))
    assert inject.paste("dictation", target=123) == "clipboard"
    assert clipboard == ["old", "dictation"]


def test_paste_cancels_if_user_copies_during_settling(monkeypatch):
    clipboard = ["old"]
    monkeypatch.setattr(inject.pyperclip, "paste", lambda: clipboard[-1])
    monkeypatch.setattr(inject.pyperclip, "copy", clipboard.append)
    monkeypatch.setattr(inject.time, "sleep", lambda _: clipboard.append("user copy"))
    monkeypatch.setattr(inject, "_send_paste", lambda: pytest.fail("Pasted unrelated content"))
    assert inject.paste("dictation") == "fail"
    assert clipboard == ["old", "dictation", "user copy"]


def test_paste_cancels_when_clipboard_cannot_be_verified(monkeypatch):
    def unavailable():
        raise RuntimeError("Clipboard busy")
    monkeypatch.setattr(inject.pyperclip, "paste", unavailable)
    monkeypatch.setattr(inject.pyperclip, "copy", lambda _: None)
    monkeypatch.setattr(inject.time, "sleep", lambda _: None)
    monkeypatch.setattr(inject, "_send_paste", lambda: pytest.fail("Unverified paste"))
    assert inject.paste("dictation") == "fail"


def test_windows_paste_returns_combo_result(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(inject.time, "sleep", lambda _s: None)
    monkeypatch.setattr(inject, "_windows_combo", lambda **_kw: False)
    assert inject._windows_paste() is False
    monkeypatch.setattr(inject, "_windows_combo", lambda **_kw: True)
    assert inject._windows_paste() is True


@pytest.mark.parametrize("returncode, expected", [(0, True), (1, False)])
def test_macos_paste_reports_osascript_result(monkeypatch, returncode, expected):
    monkeypatch.setattr(inject.sys, "platform", "darwin")
    calls = []

    def run(args, check=False):
        calls.append(args)
        return subprocess.CompletedProcess(args, returncode)

    monkeypatch.setattr(inject.subprocess, "run", run)
    assert inject._send_paste() is expected
    assert calls == [[
        "osascript", "-e",
        'tell application "System Events" to keystroke "v" using {command down}',
    ]]


def test_linux_undo_uses_ydotool_when_that_is_the_helper(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(inject.sys, "platform", "linux")
    calls: list[list[str]] = []
    monkeypatch.setattr(inject.shutil, "which", lambda name: name == "ydotool")
    monkeypatch.setattr(
        inject.subprocess,
        "run",
        lambda args, check=False: (calls.append(list(args)) or subprocess.CompletedProcess(args, 0)),
    )
    inject._send_keys_combo(ctrl=True, key="z")
    assert calls == [["ydotool", "key", "29:1", "44:1", "44:0", "29:0"]]


def test_linux_paste_falls_back_when_first_helper_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(inject.sys, "platform", "linux")
    monkeypatch.setenv("XDG_SESSION_TYPE", "x11")
    calls: list[list[str]] = []
    monkeypatch.setattr(inject.shutil, "which", lambda name: name in {"xdotool", "ydotool"})

    class Result:
        def __init__(self, code: int) -> None:
            self.returncode = code

    def run(args, check=False):
        calls.append(list(args))
        return Result(1 if args[0] == "xdotool" else 0)

    monkeypatch.setattr(inject.subprocess, "run", run)
    monkeypatch.setattr(inject.time, "sleep", lambda _s: None)
    assert inject._linux_paste() is True
    assert calls == [
        ["xdotool", "key", "ctrl+v"],
        ["ydotool", "key", "29:1", "47:1", "47:0", "29:0"],
    ]


def test_windows_combo_reports_sendinput_count(monkeypatch: pytest.MonkeyPatch) -> None:
    if sys.platform != "win32":
        pytest.skip("SendInput only exists on Windows")
    import ctypes

    monkeypatch.setattr(ctypes.windll.user32, "SendInput", lambda n, _ptr, _size: n)
    assert inject._windows_combo(ctrl=True, key="v") is True
    monkeypatch.setattr(ctypes.windll.user32, "SendInput", lambda n, _ptr, _size: n - 1)
    assert inject._windows_combo(ctrl=True, key="v") is False


def test_wayland_failed_native_helpers_preserve_dictation(monkeypatch):
    monkeypatch.setattr(inject.sys, "platform", "linux")
    monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
    monkeypatch.setattr(inject.shutil, "which", lambda name: name in {"wtype", "ydotool", "xdotool"})
    calls = []

    def run(args, **kwargs):
        calls.append(args[0])
        return subprocess.CompletedProcess(args, 0 if args[0] == "xdotool" else 1)

    monkeypatch.setattr(inject.subprocess, "run", run)
    clipboard = ["old"]
    monkeypatch.setattr(inject.pyperclip, "paste", lambda: clipboard[-1])
    monkeypatch.setattr(inject.pyperclip, "copy", clipboard.append)
    monkeypatch.setattr(inject.time, "sleep", lambda _: None)
    assert inject.paste("keep this dictation", target="") == "fail"
    assert calls == ["wtype", "ydotool"]
    assert clipboard == ["old", "keep this dictation"]


def test_wayland_does_not_use_stale_xwayland_focus(monkeypatch):
    monkeypatch.setattr(inject.sys, "platform", "linux")
    monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
    monkeypatch.setattr(inject.shutil, "which", lambda _: True)
    monkeypatch.setattr(inject.subprocess, "run", lambda *a, **k: pytest.fail("Queried X11 focus on Wayland"))
    assert inject.foreground_id() == ""
