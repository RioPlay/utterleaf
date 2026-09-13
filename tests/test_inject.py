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
    # These exercise the existing Pyperclip path. The bounded Windows backend
    # has its own process-free integration fixture in test_windows_delivery.py.
    monkeypatch.setattr(inject, "_use_windows_clipboard", lambda: False)


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
    monkeypatch.setattr(inject, "_windows_combo_status", lambda **_kw: "failed")
    assert inject._windows_paste() == "failed"
    monkeypatch.setattr(inject, "_windows_combo_status", lambda **_kw: "success")
    assert inject._windows_paste() == "success"


@pytest.mark.parametrize("returncode, expected", [(0, True), (1, False)])
def test_macos_paste_reports_osascript_result(monkeypatch, returncode, expected):
    monkeypatch.setattr(inject.sys, "platform", "darwin")
    calls = []

    def run(args, **kwargs):
        calls.append(args)
        return "success" if returncode == 0 else "uncertain"

    monkeypatch.setattr(inject, "_run_helper", run)
    assert inject._send_paste() == ("success" if expected else "uncertain")
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
    monkeypatch.setattr(inject, "_run_helper",
                        lambda args, **kwargs: (calls.append(list(args)) or "success"))
    inject._send_keys_combo(ctrl=True, key="z")
    assert calls == [["ydotool", "key", "29:1", "44:1", "44:0", "29:0"]]


def test_linux_paste_falls_back_only_when_first_helper_never_started(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(inject.sys, "platform", "linux")
    monkeypatch.setenv("XDG_SESSION_TYPE", "x11")
    calls: list[list[str]] = []
    monkeypatch.setattr(inject.shutil, "which", lambda name: name in {"xdotool", "ydotool"})

    def run(args, **kwargs):
        calls.append(list(args))
        return "not_started" if args[0] == "xdotool" else "success"

    monkeypatch.setattr(inject, "_run_helper", run)
    monkeypatch.setattr(inject.time, "sleep", lambda _s: None)
    assert inject._linux_paste() == "success"
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
    monkeypatch.setattr(ctypes.windll.user32, "SendInput", lambda _n, _ptr, _size: 0)
    assert inject._windows_combo(ctrl=True, key="v") is False


@pytest.mark.parametrize("accepted", [1, 2, 3])
def test_windows_partial_paste_is_uncertain_and_sends_keyups_only(monkeypatch, accepted):
    if sys.platform != "win32":
        pytest.skip("SendInput only exists on Windows")
    import ctypes

    counts, cleanup_events = [], []
    def send(n, pointer, _size):
        counts.append(n)
        if len(counts) == 2:
            array = pointer._obj
            cleanup_events.extend((array[i].ii.ki.wVk, array[i].ii.ki.dwFlags)
                                  for i in range(n))
        return accepted if len(counts) == 1 else n

    monkeypatch.setattr(ctypes.windll.user32, "SendInput", send)
    assert inject._windows_paste() == "uncertain"
    assert counts == [4, 2]
    assert cleanup_events == [(0x56, 0x2), (0x11, 0x2)]


def test_windows_partial_paste_stays_uncertain_when_keyup_cleanup_fails(monkeypatch):
    if sys.platform != "win32":
        pytest.skip("SendInput only exists on Windows")
    import ctypes

    counts = []
    def send(n, _ptr, _size):
        counts.append(n)
        return 3 if len(counts) == 1 else 0

    monkeypatch.setattr(ctypes.windll.user32, "SendInput", send)
    assert inject._windows_paste() == "uncertain"
    assert counts == [4, 2]


def test_windows_rechecks_target_after_clipboard_verification(monkeypatch):
    monkeypatch.setattr(inject.sys, "platform", "win32")
    focus = [123]
    clipboard = ["old"]

    def read_clipboard():
        if clipboard[-1] == "dictation":
            focus[0] = 456
        return clipboard[-1]

    monkeypatch.setattr(inject, "foreground_id", lambda: focus[0])
    monkeypatch.setattr(inject.pyperclip, "paste", read_clipboard)
    monkeypatch.setattr(inject.pyperclip, "copy", clipboard.append)
    monkeypatch.setattr(inject.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(inject, "_windows_paste", lambda: pytest.fail("wrong-target SendInput"))
    assert inject.paste("dictation", target=123) == "clipboard"
    assert clipboard == ["old", "dictation"]


def test_wayland_failed_native_helpers_preserve_dictation(monkeypatch):
    monkeypatch.setattr(inject.sys, "platform", "linux")
    monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
    monkeypatch.setattr(inject.shutil, "which", lambda name: name in {"wtype", "ydotool", "xdotool"})
    calls = []

    def run(args, **kwargs):
        calls.append(args[0])
        return "uncertain"

    monkeypatch.setattr(inject, "_run_helper", run)
    clipboard = ["old"]
    monkeypatch.setattr(inject.pyperclip, "paste", lambda: clipboard[-1])
    monkeypatch.setattr(inject.pyperclip, "copy", clipboard.append)
    monkeypatch.setattr(inject.time, "sleep", lambda _: None)
    assert inject.paste("keep this dictation", target="") == "uncertain"
    assert calls == ["wtype"]
    assert clipboard == ["old", "keep this dictation"]


def test_wayland_does_not_use_stale_xwayland_focus(monkeypatch):
    monkeypatch.setattr(inject.sys, "platform", "linux")
    monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
    monkeypatch.setattr(inject.shutil, "which", lambda _: True)
    monkeypatch.setattr(inject.subprocess, "run", lambda *a, **k: pytest.fail("Queried X11 focus on Wayland"))
    assert inject.foreground_id() == ""


def test_helper_timeout_kills_and_reaps_owned_process(monkeypatch):
    events = []

    class Process:
        def poll(self):
            return None
        def terminate(self):
            events.append("terminate")
        def wait(self, timeout=None):
            events.append(("wait", timeout))
            if len([event for event in events if isinstance(event, tuple)]) == 1:
                raise subprocess.TimeoutExpired("helper", timeout)
            return -9
        def kill(self):
            events.append("kill")

    monkeypatch.setattr(inject.subprocess, "Popen", lambda *a, **k: Process())
    moments = iter((0.0, 2.0))
    monkeypatch.setattr(inject.time, "monotonic", lambda: next(moments))
    assert inject._run_helper(["wtype"], timeout=1.0) == "uncertain"
    assert events == ["terminate", ("wait", inject.HELPER_STOP_SECONDS),
                      "kill", ("wait", inject.HELPER_STOP_SECONDS)]


def test_inflight_cancel_releases_modifier_without_second_paste(monkeypatch):
    commands, terminated = [], []

    class PasteProcess:
        def poll(self): return None
        def terminate(self): terminated.append(True)
        def wait(self, timeout=None): return -15
        def kill(self): pytest.fail("terminate completed")

    class CleanupProcess:
        def poll(self): return 0
        def terminate(self): pytest.fail("completed cleanup must not terminate")
        def wait(self, timeout=None): return 0
        def kill(self): pytest.fail("completed cleanup must not kill")

    def popen(args, **_kwargs):
        commands.append(list(args))
        return PasteProcess() if len(commands) == 1 else CleanupProcess()

    checks = iter((False, True))
    monkeypatch.setattr(inject.subprocess, "Popen", popen)
    status = inject._run_helper(
        ["wtype", "-M", "ctrl", "v", "-m", "ctrl"],
        cancel=lambda: next(checks), cleanup=["wtype", "-m", "ctrl"])
    assert status == "uncertain"
    assert commands == [["wtype", "-M", "ctrl", "v", "-m", "ctrl"],
                        ["wtype", "-m", "ctrl"]]
    assert terminated == [True]


def test_launched_linux_failure_never_tries_second_paste_helper(monkeypatch):
    monkeypatch.setattr(inject, "linux_helpers", lambda: ("wtype", "ydotool"))
    monkeypatch.setattr(inject.shutil, "which", lambda _name: True)
    calls = []
    monkeypatch.setattr(inject, "_run_helper",
                        lambda args, **kwargs: calls.append(list(args)) or "uncertain")
    assert inject._linux_paste() == "uncertain"
    assert calls == [["wtype", "-M", "ctrl", "v", "-m", "ctrl"]]


def test_cancel_before_dispatch_restores_owned_clipboard(monkeypatch):
    clipboard = ["old"]
    cancelled = [False]
    monkeypatch.setattr(inject.pyperclip, "paste", lambda: clipboard[-1])
    monkeypatch.setattr(inject.pyperclip, "copy", clipboard.append)
    monkeypatch.setattr(inject.time, "sleep", lambda _seconds: cancelled.__setitem__(0, True))
    monkeypatch.setattr(inject, "_send_paste", lambda **_kwargs: pytest.fail("cancelled before dispatch"))
    assert inject.paste("dictation", cancel=lambda: cancelled[0]) == "cancelled"
    assert clipboard == ["old", "dictation", "old"]


def test_cancel_before_dispatch_preserves_new_user_copy(monkeypatch):
    clipboard = ["old"]
    cancelled = [False]
    monkeypatch.setattr(inject.pyperclip, "paste", lambda: clipboard[-1])
    monkeypatch.setattr(inject.pyperclip, "copy", clipboard.append)
    def user_copy(_seconds):
        clipboard.append("user copy")
        cancelled[0] = True
    monkeypatch.setattr(inject.time, "sleep", user_copy)
    monkeypatch.setattr(inject, "_send_paste", lambda **_kwargs: pytest.fail("cancelled before dispatch"))
    assert inject.paste("dictation", cancel=lambda: cancelled[0]) == "cancelled"
    assert clipboard == ["old", "dictation", "user copy"]


def test_cancelled_launched_helper_is_uncertain_and_keeps_dictation(monkeypatch):
    clipboard = ["old"]
    monkeypatch.setattr(inject.pyperclip, "paste", lambda: clipboard[-1])
    monkeypatch.setattr(inject.pyperclip, "copy", clipboard.append)
    monkeypatch.setattr(inject.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(inject, "_send_paste", lambda **_kwargs: "uncertain")
    assert inject.paste("dictation", cancel=lambda: False) == "uncertain"
    assert clipboard == ["old", "dictation"]


def test_cancel_racing_success_is_uncertain_when_restore_is_disabled(monkeypatch):
    clipboard = ["old"]
    cancelled = [False]
    monkeypatch.setattr(inject.pyperclip, "paste", lambda: clipboard[-1])
    monkeypatch.setattr(inject.pyperclip, "copy", clipboard.append)
    monkeypatch.setattr(inject.time, "sleep", lambda _seconds: None)
    def dispatch(**_kwargs):
        cancelled[0] = True
        return "success"
    monkeypatch.setattr(inject, "_send_paste", dispatch)
    assert inject.paste("dictation", restore_clipboard=False,
                        cancel=lambda: cancelled[0]) == "uncertain"
    assert clipboard == ["old", "dictation"]


def test_fresh_cancel_predicate_allows_later_independent_delivery(monkeypatch):
    clipboard = ["old"]
    monkeypatch.setattr(inject.pyperclip, "paste", lambda: clipboard[-1])
    monkeypatch.setattr(inject.pyperclip, "copy", clipboard.append)
    monkeypatch.setattr(inject.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(inject, "_send_paste", lambda **_kwargs: "success")
    monkeypatch.setattr(inject, "_paste_settled", lambda **_kwargs: False)
    assert inject.paste("old job", cancel=lambda: True) == "cancelled"
    assert inject.paste("new job", cancel=lambda: False) == "pasted"
    assert clipboard == ["old", "new job", "old"]
