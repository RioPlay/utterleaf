"""Paste text into the focused app without stealing focus."""

from __future__ import annotations

import logging
import shutil
import subprocess
import sys
import time

import pyperclip
from utterleaf.host import linux_helpers

log = logging.getLogger("utterleaf")


def copy_text(text: str) -> bool:
    """Offer manual recovery without sending keystrokes to an unknown field."""
    try:
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


def _paste_settled(deadline: float = 0.28) -> None:
    """Windows: wait for the target app to have finished reading the clipboard.

    A pasting app briefly opens the clipboard (visible via GetOpenClipboardWindow).
    Resuming as soon as we see it open once — or at the deadline — is faster than a
    fixed sleep and never regresses: the deadline is the old fixed wait.
    """
    if sys.platform != "win32":
        time.sleep(deadline)
        return
    try:
        import ctypes

        get_open = ctypes.windll.user32.GetOpenClipboardWindow
        get_open.restype = ctypes.c_void_p
    except Exception:
        time.sleep(deadline)
        return
    deadline_at = time.monotonic() + deadline
    saw_open = False
    while time.monotonic() < deadline_at:
        if get_open():
            saw_open = True
        elif saw_open:
            return
        time.sleep(0.01)
    # Never observed an open by the deadline: the fixed wait has elapsed, so we
    # are no later than the old behavior already was.


def paste(text: str, restore_clipboard: bool = True, target=None) -> str:
    """Paste into the focused app. Returns pasted, clipboard, fail, or empty."""
    if text == "":
        return "empty"
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

    # Allow shortcut modifiers to settle before the final focus check. Doing
    # this inside the platform helper leaves an avoidable wrong-window gap.
    time.sleep(0.05)
    if target is not None and not same_target(target, foreground_id()):
        log.warning("Focus moved before delivery; left text on the clipboard")
        return "clipboard"
    try:
        if pyperclip.paste() != text:
            log.warning("Clipboard changed before delivery; paste cancelled")
            return "fail"
    except Exception:
        log.warning("Could not verify clipboard before delivery; paste cancelled")
        return "fail"

    ok = _send_paste()
    if ok and restore_clipboard:
        _paste_settled()
        # Restore only if the user is still in the same window: a slow app can
        # paste after the restore, and the swap must not leak old clipboard
        # content into whatever took focus.
        if previous is not None and same_target(target, foreground_id()):
            try:
                # A copy made while the target handles the paste belongs to
                # the user. Never replace it with our saved clipboard.
                if pyperclip.paste() == text:
                    pyperclip.copy(previous)
            except Exception:
                pass
    return "pasted" if ok else "fail"


def undo_last() -> bool:
    return _send_keys_combo(ctrl=True, key="z")


def _send_paste() -> bool:
    if sys.platform == "win32":
        return _windows_paste()
    if sys.platform == "darwin":
        return _mac_paste()
    return _linux_paste()


def _send_keys_combo(*, ctrl: bool = False, meta: bool = False, key: str) -> bool:
    if sys.platform == "win32":
        return _windows_combo(ctrl=ctrl, key=key)
    if sys.platform == "darwin":
        which = "command down" if meta or ctrl else "control down"
        script = f'tell application "System Events" to keystroke "{key}" using {{{which}}}'
        return subprocess.run(["osascript", "-e", script], check=False).returncode == 0
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
        result = subprocess.run(args, check=False)
        if result.returncode == 0:
            return True
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
        ["osascript", "-e", script], capture_output=True, text=True, check=False
    )
    return (result.stdout or "").strip()


def _linux_foreground() -> str:
    if shutil.which("xdotool"):
        wid = subprocess.run(
            ["xdotool", "getactivewindow"], capture_output=True, text=True, check=False
        )
        if wid.returncode == 0 and wid.stdout.strip():
            name = subprocess.run(
                ["xdotool", "getwindowname", wid.stdout.strip()],
                capture_output=True,
                text=True,
                check=False,
            )
            return (name.stdout or "").strip()
    return ""


def _windows_combo(*, ctrl: bool, key: str) -> bool:
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
    return ctypes.windll.user32.SendInput(len(sequence), ctypes.byref(array), ctypes.sizeof(INPUT)) == len(sequence)


def _windows_paste() -> bool:
    return _windows_combo(ctrl=True, key="v")


def _mac_paste() -> bool:
    script = 'tell application "System Events" to keystroke "v" using {command down}'
    result = subprocess.run(["osascript", "-e", script], check=False)
    return result.returncode == 0


def _linux_paste() -> bool:
    for helper in linux_helpers():
        if not shutil.which(helper):
            continue
        if helper == "wtype":
            args = ["wtype", "-M", "ctrl", "v", "-m", "ctrl"]
        elif helper == "xdotool":
            args = ["xdotool", "key", "ctrl+v"]
        else:
            args = ["ydotool", "key", "29:1", "47:1", "47:0", "29:0"]
        result = subprocess.run(args, check=False)
        if result.returncode == 0:
            return True
    log.warning("No paste helper found (install xdotool, wtype, or ydotool)")
    return False
