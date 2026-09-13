"""Paste text into the focused app without stealing focus."""

from __future__ import annotations

import logging
import shutil
import subprocess
import sys
import time
from typing import Callable

import pyperclip
from utterleaf.host import is_wayland, linux_helpers

log = logging.getLogger("utterleaf")

HELPER_TIMEOUT_SECONDS = 1.0
HELPER_POLL_SECONDS = 0.01
HELPER_STOP_SECONDS = 0.2
HELPER_CLEANUP_SECONDS = 0.25


def _cancelled(cancel: Callable[[], bool] | None) -> bool:
    return bool(cancel is not None and cancel())


def _use_windows_clipboard() -> bool:
    return sys.platform == "win32"


def copy_text(text: str) -> bool:
    """Offer manual recovery without sending keystrokes to an unknown field."""
    try:
        if _use_windows_clipboard():
            from utterleaf import windows_clipboard

            return windows_clipboard.write(text).status == "ok"
        pyperclip.copy(text)
        return True
    except Exception:
        log.warning("Could not copy text for manual recovery")
        return False


def foreground_id() -> object:
    """Stable id for the focused window. Used to refuse a wrong-app paste."""
    try:
        if sys.platform == "win32":
            import ctypes

            return int(ctypes.windll.user32.GetForegroundWindow())
    except Exception:
        pass
    return foreground_app()


def same_target(saved, current) -> bool:
    if not saved:
        return True
    return saved == current


def _clipboard_sequence() -> int | None:
    """Windows change identity, without reading or retaining clipboard content.

    Text equality alone cannot detect a user copying the same text again. None
    means the platform has no supported identity check; zero on Windows means
    access could not be verified and must not authorize automatic restoration.
    """
    if sys.platform != "win32":
        return None
    try:
        import ctypes

        sequence = ctypes.windll.user32.GetClipboardSequenceNumber
        sequence.argtypes = []
        sequence.restype = ctypes.c_ulong
        return int(sequence())
    except Exception:
        return 0


def _clipboard_unchanged(sequence: int | None) -> bool:
    current = _clipboard_sequence()
    if sequence is None:
        return current is None
    return sequence != 0 and current == sequence


def foreground_app() -> str:
    try:
        if sys.platform == "win32":
            return _windows_foreground()
        if sys.platform == "darwin":
            return _mac_foreground()
        return _linux_foreground()
    except Exception:
        log.debug("Could not read foreground app", exc_info=True)
        return ""


def _paste_settled(deadline: float = 0.28, *,
                   cancel: Callable[[], bool] | None = None) -> bool:
    """Windows: wait for the target app to have finished reading the clipboard.

    A pasting app briefly opens the clipboard (visible via GetOpenClipboardWindow).
    Resuming as soon as we see it open once — or at the deadline — is faster than a
    fixed sleep and never regresses: the deadline is the old fixed wait.
    """
    if sys.platform != "win32":
        if cancel is None:
            time.sleep(deadline)
            return False
        deadline_at = time.monotonic() + deadline
        while time.monotonic() < deadline_at:
            if _cancelled(cancel):
                return True
            time.sleep(min(HELPER_POLL_SECONDS, max(0, deadline_at - time.monotonic())))
        return _cancelled(cancel)
    try:
        import ctypes

        get_open = ctypes.windll.user32.GetOpenClipboardWindow
        get_open.restype = ctypes.c_void_p
    except Exception:
        if cancel is None:
            time.sleep(deadline)
            return False
        deadline_at = time.monotonic() + deadline
        while time.monotonic() < deadline_at:
            if _cancelled(cancel):
                return True
            time.sleep(min(HELPER_POLL_SECONDS, max(0, deadline_at - time.monotonic())))
        return _cancelled(cancel)
    deadline_at = time.monotonic() + deadline
    saw_open = False
    while time.monotonic() < deadline_at:
        if _cancelled(cancel):
            return True
        if get_open():
            saw_open = True
        elif saw_open:
            return False
        time.sleep(0.01)
    # Never observed an open by the deadline: the fixed wait has elapsed, so we
    # are no later than the old behavior already was.
    return _cancelled(cancel)


def _restore_owned(previous, text: str, sequence: int | None, target) -> None:
    """Restore only clipboard content still owned by this delivery attempt."""
    if previous is None or not same_target(target, foreground_id()):
        return
    try:
        if pyperclip.paste() == text and _clipboard_unchanged(sequence):
            pyperclip.copy(previous)
    except Exception:
        pass


def _paste_windows_clipboard(text: str, restore_clipboard: bool, target,
                             cancel: Callable[[], bool] | None) -> str:
    """Keep owner-controlled native reads/writes outside the delivery process."""
    from utterleaf import windows_clipboard

    if _cancelled(cancel):
        return "cancelled"
    moved = target is not None and not same_target(target, foreground_id())
    previous = (windows_clipboard.snapshot(cancel=cancel)
                if restore_clipboard and not moved else None)
    if _cancelled(cancel):
        return "cancelled"
    saved = previous is not None and previous.status == "ok"
    copied = windows_clipboard.write(text,
        expected_sequence=previous.sequence if saved else None, cancel=cancel)
    if copied.status != "ok":
        # No shortcut has been dispatched, even if a child may have changed
        # the clipboard. Keep the app's ordinary manual recovery available.
        return "cancelled" if _cancelled(cancel) or copied.status == "cancelled" else "fail"
    sequence = copied.sequence
    if _cancelled(cancel):
        # Do not launch a new restoration worker after cancellation/quit.
        return "cancelled"
    if moved or (target is not None and not same_target(target, foreground_id())):
        return "clipboard"
    if cancel is None:
        time.sleep(0.05)
    else:
        deadline = time.monotonic() + 0.05
        while time.monotonic() < deadline:
            if _cancelled(cancel):
                return "cancelled"
            time.sleep(min(HELPER_POLL_SECONDS, max(0, deadline - time.monotonic())))
    if _cancelled(cancel):
        return "cancelled"
    if target is not None and not same_target(target, foreground_id()):
        return "clipboard"
    if not sequence or not _clipboard_unchanged(sequence):
        return "fail"

    # Sequence metadata does not request clipboard rendering. Recheck it as
    # part of the final dispatch guard, without another clipboard data read.
    guard = lambda: _cancelled(cancel) or not _clipboard_unchanged(sequence)
    try:
        dispatch = _send_paste(cancel=guard, target=target)
    except Exception:
        # Dispatch may have begun; never retry or restore over a late paste.
        return "uncertain"
    if dispatch in ("cancelled", "target"):
        if _cancelled(cancel):
            return "cancelled"
        return "clipboard" if dispatch == "target" else "fail"
    if dispatch == "uncertain" or (dispatch in (True, "success") and _cancelled(cancel)):
        return "uncertain"
    if dispatch not in (True, "success"):
        return "fail"
    if restore_clipboard and saved:
        if _paste_settled(cancel=cancel):
            return "uncertain"
        if _cancelled(cancel):
            return "uncertain"
        if same_target(target, foreground_id()):
            restored = windows_clipboard.write(previous.text,
                expected_sequence=sequence, cancel=cancel)
            if restored.status == "uncertain" or _cancelled(cancel):
                return "uncertain"
    return "pasted"


def paste(text: str, restore_clipboard: bool = True, target=None, *,
          cancel: Callable[[], bool] | None = None) -> str:
    """Return pasted, clipboard, fail, empty, cancelled, or uncertain.

    A successful shortcut is not proof the editor inserted the text. Clipboard
    and focus checks reduce races; they do not make desktop delivery atomic.
    ``uncertain`` means dispatch may have begun; callers must not retry because
    part of the shortcut may already have been sent. ``fail`` and ``cancelled``
    before dispatch do not promise an unchanged clipboard: its write may have
    finished even when no shortcut was sent.
    """
    if text == "":
        return "empty"
    if _cancelled(cancel):
        return "cancelled"
    if _use_windows_clipboard():
        return _paste_windows_clipboard(text, restore_clipboard, target, cancel)
    if target is not None and not same_target(target, foreground_id()):
        try:
            pyperclip.copy(text)
        except Exception:
            return "fail"
        log.warning("Focus moved; left text on the clipboard")
        return "clipboard"
    previous = None
    if restore_clipboard:
        try:
            previous = pyperclip.paste()
        except Exception:
            previous = None
    try:
        pyperclip.copy(text)
    except Exception:
        log.exception("Clipboard copy failed")
        return "fail"
    sequence = _clipboard_sequence()

    # Allow shortcut modifiers to settle before the final focus check. Doing
    # this inside the platform helper leaves an avoidable wrong-window gap.
    if cancel is None:
        time.sleep(0.05)
    else:
        deadline = time.monotonic() + 0.05
        while time.monotonic() < deadline:
            if _cancelled(cancel):
                if restore_clipboard:
                    _restore_owned(previous, text, sequence, target)
                return "cancelled"
            time.sleep(min(HELPER_POLL_SECONDS, max(0, deadline - time.monotonic())))
    if target is not None and not same_target(target, foreground_id()):
        log.warning("Focus moved before delivery; left text on the clipboard")
        return "clipboard"
    try:
        if pyperclip.paste() != text or (sequence != 0 and not _clipboard_unchanged(sequence)):
            log.warning("Clipboard changed before delivery; paste cancelled")
            return "fail"
    except Exception:
        log.warning("Could not verify clipboard before delivery; paste cancelled")
        return "fail"

    if _cancelled(cancel):
        if restore_clipboard:
            _restore_owned(previous, text, sequence, target)
        return "cancelled"

    try:
        dispatch = (_send_paste() if cancel is None and target is None else
                    _send_paste(cancel=cancel, target=target))
    except Exception:
        # Preserve the copied dictation and the caller's recovery path. Helper
        # errors need not include command output or clipboard content in logs.
        log.warning("Paste shortcut failed; dictation remains available for recovery")
        return "fail"
    # Compatibility with private test/platform adapters that returned bool.
    if dispatch is True:
        dispatch = "success"
    elif dispatch is False:
        dispatch = "failed"
    if dispatch == "cancelled":
        if restore_clipboard:
            _restore_owned(previous, text, sequence, target)
        return "cancelled"
    if dispatch == "target":
        return "clipboard"
    if dispatch == "uncertain":
        return "uncertain"
    if dispatch == "success" and _cancelled(cancel):
        # The shortcut was accepted, but cancellation raced its completion.
        # Keep recovery on the clipboard and do not claim a confirmed paste.
        return "uncertain"
    if dispatch == "success" and restore_clipboard:
        cancelled_while_settling = (_paste_settled() if cancel is None else
                                    _paste_settled(cancel=cancel))
        if cancelled_while_settling:
            return "uncertain"
        # Restore only if the user is still in the same window: a slow app can
        # paste after the restore, and the swap must not leak old clipboard
        # content into whatever took focus.
        # A copy made while the target handles the paste belongs to the user.
        # Check identity after reading so identical copied text is still detected.
        _restore_owned(previous, text, sequence, target)
    return "pasted" if dispatch == "success" else "fail"


def undo_last() -> bool:
    return _send_keys_combo(ctrl=True, key="z")


def _send_paste(*, cancel: Callable[[], bool] | None = None, target=None) -> str:
    if sys.platform == "win32":
        invalid = _dispatch_valid(cancel, target)
        if invalid:
            return invalid
        return _windows_paste()
    if sys.platform == "darwin":
        return _mac_paste(cancel=cancel, target=target)
    return _linux_paste(cancel=cancel, target=target)


def _send_keys_combo(*, ctrl: bool = False, meta: bool = False, key: str) -> bool:
    if sys.platform == "win32":
        return _windows_combo(ctrl=ctrl, key=key)
    if sys.platform == "darwin":
        which = "command down" if meta or ctrl else "control down"
        script = f'tell application "System Events" to keystroke "{key}" using {{{which}}}'
        return _run_helper(["osascript", "-e", script], cleanup=None) == "success"
    for helper in linux_helpers():
        if not shutil.which(helper):
            continue
        if helper == "wtype":
            args = ["wtype"]
            if ctrl:
                args += ["-M", "ctrl"]
            args += [key]
            if ctrl:
                args += ["-m", "ctrl"]
        elif helper == "xdotool":
            mods = []
            if ctrl:
                mods.append("ctrl")
            if meta:
                mods.append("super")
            args = ["xdotool", "key", "+".join(mods + [key]) if mods else key]
        else:
            codes = {"v": "47", "z": "44"}
            vk = codes.get(key)
            if vk is None:
                return False
            args = ["ydotool", "key"]
            if ctrl:
                args += ["29:1", f"{vk}:1", f"{vk}:0", "29:0"]
            else:
                args += [f"{vk}:1", f"{vk}:0"]
        status = _run_helper(args, cleanup=_modifier_release(helper))
        if status == "success":
            return True
        if status != "not_started":
            return False
    return False


def _windows_foreground() -> str:
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    hwnd = user32.GetForegroundWindow()
    length = user32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buf, length + 1)
    title = buf.value

    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    handle = ctypes.windll.kernel32.OpenProcess(
        PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value
    )
    exe = ""
    if handle:
        size = wintypes.DWORD(260)
        name = ctypes.create_unicode_buffer(260)
        if ctypes.windll.kernel32.QueryFullProcessImageNameW(handle, 0, name, ctypes.byref(size)):
            exe = name.value.rsplit("\\", 1)[-1]
        ctypes.windll.kernel32.CloseHandle(handle)
    return f"{exe} {title}".strip()


def _mac_foreground() -> str:
    script = 'tell application "System Events" to get name of first process whose frontmost is true'
    result = subprocess.run(
        ["osascript", "-e", script], capture_output=True, text=True, check=False,
        timeout=HELPER_TIMEOUT_SECONDS,
    )
    return (result.stdout or "").strip()


def _linux_foreground() -> str:
    # XWayland's active window may be stale while a native client has focus.
    if is_wayland():
        return ""
    if shutil.which("xdotool"):
        wid = subprocess.run(
            ["xdotool", "getactivewindow"], capture_output=True, text=True, check=False,
            timeout=HELPER_TIMEOUT_SECONDS,
        )
        if wid.returncode == 0 and wid.stdout.strip():
            name = subprocess.run(
                ["xdotool", "getwindowname", wid.stdout.strip()],
                capture_output=True,
                text=True,
                check=False,
                timeout=HELPER_TIMEOUT_SECONDS,
            )
            return (name.stdout or "").strip()
    return ""


def _windows_combo_status(*, ctrl: bool, key: str) -> str:
    import ctypes

    INPUT_KEYBOARD = 1
    KEYEVENTF_KEYUP = 0x0002
    VK = {"v": 0x56, "z": 0x5A, "ctrl": 0x11}
    extra = ctypes.c_ulong(0)

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = (
            ("wVk", ctypes.c_ushort),
            ("wScan", ctypes.c_ushort),
            ("dwFlags", ctypes.c_ulong),
            ("time", ctypes.c_ulong),
            ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
        )

    class HARDWAREINPUT(ctypes.Structure):
        _fields_ = (
            ("uMsg", ctypes.c_ulong),
            ("wParamL", ctypes.c_short),
            ("wParamH", ctypes.c_ushort),
        )

    class MOUSEINPUT(ctypes.Structure):
        _fields_ = (
            ("dx", ctypes.c_long),
            ("dy", ctypes.c_long),
            ("mouseData", ctypes.c_ulong),
            ("dwFlags", ctypes.c_ulong),
            ("time", ctypes.c_ulong),
            ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
        )

    class _INNER(ctypes.Union):
        _fields_ = (("ki", KEYBDINPUT), ("mi", MOUSEINPUT), ("hi", HARDWAREINPUT))

    class INPUT(ctypes.Structure):
        _fields_ = (("type", ctypes.c_ulong), ("ii", _INNER))

    def event(vk: int, flags: int = 0) -> INPUT:
        item = INPUT(type=INPUT_KEYBOARD)
        item.ii.ki = KEYBDINPUT(vk, 0, flags, 0, ctypes.pointer(extra))
        return item

    sequence = []
    if ctrl:
        sequence.append(event(VK["ctrl"]))
    sequence.append(event(VK[key]))
    sequence.append(event(VK[key], KEYEVENTF_KEYUP))
    if ctrl:
        sequence.append(event(VK["ctrl"], KEYEVENTF_KEYUP))
    array = (INPUT * len(sequence))(*sequence)
    sent = ctypes.windll.user32.SendInput(
        len(sequence), ctypes.byref(array), ctypes.sizeof(INPUT))
    if sent == len(sequence):
        return "success"
    if sent <= 0:
        return "failed"
    # Some prefix of the shortcut was accepted. It may already have pasted and
    # may have left V or Ctrl held. Send key-up events only; never retry key-down.
    release = [event(VK[key], KEYEVENTF_KEYUP)]
    if ctrl:
        release.append(event(VK["ctrl"], KEYEVENTF_KEYUP))
    releases = (INPUT * len(release))(*release)
    try:
        ctypes.windll.user32.SendInput(
            len(release), ctypes.byref(releases), ctypes.sizeof(INPUT))
    except Exception:
        pass
    return "uncertain"


def _windows_combo(*, ctrl: bool, key: str) -> bool:
    """Compatibility result for non-paste shortcuts such as Undo."""
    return _windows_combo_status(ctrl=ctrl, key=key) == "success"


def _windows_paste() -> str:
    return _windows_combo_status(ctrl=True, key="v")


def _terminate_helper(process) -> None:
    try:
        process.terminate()
    except OSError:
        pass
    try:
        process.wait(timeout=HELPER_STOP_SECONDS)
        return
    except (OSError, subprocess.TimeoutExpired):
        pass
    try:
        process.kill()
    except OSError:
        pass
    try:
        process.wait(timeout=HELPER_STOP_SECONDS)
    except (OSError, subprocess.TimeoutExpired):
        pass


def _run_helper(args: list[str], *, cancel: Callable[[], bool] | None = None,
                timeout: float = HELPER_TIMEOUT_SECONDS,
                cleanup: list[str] | None = None) -> str:
    """Run one owned helper, returning success/uncertain/not_started/cancelled."""
    if _cancelled(cancel):
        return "cancelled"
    try:
        process = subprocess.Popen(
            args, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        return "not_started"
    deadline = time.monotonic() + timeout
    status = "uncertain"
    try:
        while True:
            code = process.poll()
            if code is not None:
                status = "success" if code == 0 else "uncertain"
                break
            if _cancelled(cancel) or time.monotonic() >= deadline:
                _terminate_helper(process)
                break
            time.sleep(HELPER_POLL_SECONDS)
    except Exception:
        _terminate_helper(process)
    if status != "success" and cleanup is not None:
        # The paste helper may have stopped between modifier-down and modifier-up.
        # Release only that modifier with a separately bounded, non-paste command.
        _run_helper(cleanup, timeout=HELPER_CLEANUP_SECONDS, cleanup=None)
    return status


def _modifier_release(helper: str) -> list[str] | None:
    if helper == "wtype":
        return ["wtype", "-m", "ctrl"]
    if helper == "xdotool":
        return ["xdotool", "keyup", "ctrl"]
    if helper == "ydotool":
        return ["ydotool", "key", "29:0"]
    return None


def _dispatch_valid(cancel: Callable[[], bool] | None, target) -> str | None:
    if _cancelled(cancel):
        return "cancelled"
    current = foreground_id() if target is not None else None
    if _cancelled(cancel):
        return "cancelled"
    if target is not None and not same_target(target, current):
        return "target"
    return None


def _mac_paste(*, cancel: Callable[[], bool] | None = None, target=None) -> str:
    invalid = _dispatch_valid(cancel, target)
    if invalid:
        return invalid
    script = 'tell application "System Events" to keystroke "v" using {command down}'
    status = _run_helper(["osascript", "-e", script], cancel=cancel, cleanup=None)
    return "failed" if status == "not_started" else status


def _linux_paste(*, cancel: Callable[[], bool] | None = None, target=None) -> str:
    for helper in linux_helpers():
        if not shutil.which(helper):
            continue
        invalid = _dispatch_valid(cancel, target)
        if invalid:
            return invalid
        if helper == "wtype":
            args = ["wtype", "-M", "ctrl", "v", "-m", "ctrl"]
        elif helper == "xdotool":
            args = ["xdotool", "key", "ctrl+v"]
        else:
            args = ["ydotool", "key", "29:1", "47:1", "47:0", "29:0"]
        status = _run_helper(args, cancel=cancel, cleanup=_modifier_release(helper))
        if status == "success":
            return status
        if status != "not_started":
            # Once a process launched, partial shortcut delivery is possible.
            # Never try a second paste helper after an indeterminate result.
            return status
    log.warning("Paste helpers unavailable or failed (%s); text remains on the clipboard", ", ".join(linux_helpers()))
    return "failed"
