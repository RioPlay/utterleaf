import subprocess
import sys

import pytest

from utterleaf import inject
from utterleaf.inject import same_target


def test_same_target_treats_empty_as_ok() -> None:
    assert same_target(None, 123) is True
    assert same_target(0, 0) is True


def test_same_target_rejects_other_window() -> None:
    assert same_target(1, 2) is False
    assert same_target(5, 5) is True


def test_paste_restores_clipboard_when_send_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    copies = []
    monkeypatch.setattr(inject.pyperclip, "paste", lambda: "old")
    monkeypatch.setattr(inject.pyperclip, "copy", lambda text: copies.append(text))
    monkeypatch.setattr(inject.time, "sleep", lambda _s: None)
    monkeypatch.setattr(inject, "_send_paste", lambda: True)
    assert inject.paste("hello") == "pasted"
    assert copies == ["hello", "old"]


def test_paste_keeps_clipboard_when_send_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    copies = []
    monkeypatch.setattr(inject.pyperclip, "paste", lambda: "old")
    monkeypatch.setattr(inject.pyperclip, "copy", lambda text: copies.append(text))
    monkeypatch.setattr(inject.time, "sleep", lambda _s: None)
    monkeypatch.setattr(inject, "_send_paste", lambda: False)
    assert inject.paste("hello") == "fail"
    assert copies == ["hello"]


def test_windows_paste_returns_combo_result(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(inject.time, "sleep", lambda _s: None)
    monkeypatch.setattr(inject, "_windows_combo", lambda **_kw: False)
    assert inject._windows_paste() is False
    monkeypatch.setattr(inject, "_windows_combo", lambda **_kw: True)
    assert inject._windows_paste() is True


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
