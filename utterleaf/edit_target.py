"""Scoped edits for verifiable native fields; never operate on an undo stack.

Unsupported editors return no receipt. Callers can offer a manual clipboard
replacement instead. Field contents stay in memory and are never logged.
"""
from __future__ import annotations

from dataclasses import dataclass
import sys


@dataclass(frozen=True)
class Field:
    identity: tuple[int, int, int]
    text: str
    start: int
    end: int


@dataclass(frozen=True)
class Receipt:
    before: Field
    after: Field


def _units(text: str) -> int:
    return len(text.encode("utf-16-le")) // 2


def _splice(text: str, start: int, end: int, replacement: str) -> str:
    raw = text.encode("utf-16-le")
    return (raw[:start * 2] + replacement.encode("utf-16-le") + raw[end * 2:]).decode("utf-16-le")


def _native_api():
    import ctypes as c
    from ctypes import wintypes as w

    api = c.WinDLL("user32", use_last_error=True)
    api.GetForegroundWindow.restype = w.HWND
    api.GetWindowThreadProcessId.argtypes = [w.HWND, c.POINTER(w.DWORD)]
    api.GetWindowThreadProcessId.restype = w.DWORD
    api.GetClassNameW.argtypes = [w.HWND, w.LPWSTR, c.c_int]
    api.GetWindowLongW.argtypes = [w.HWND, c.c_int]
    api.IsWindowUnicode.argtypes = [w.HWND]
    api.IsWindowEnabled.argtypes = [w.HWND]
    api.SendMessageTimeoutW.argtypes = [w.HWND, w.UINT, c.c_size_t, c.c_ssize_t,
                                      w.UINT, w.UINT, c.POINTER(c.c_size_t)]
    api.SendMessageTimeoutW.restype = c.c_ssize_t
    return api


def _send(api, hwnd, message, wparam=0, lparam=0):
    import ctypes as c
    result = c.c_size_t()
    if not api.SendMessageTimeoutW(hwnd, message, wparam, lparam, 0x3, 150, c.byref(result)):
        raise OSError("The text field did not respond")
    return result.value


def read_field() -> Field | None:
    """Only Unicode Windows Edit controls have a verified adapter so far."""
    if sys.platform != "win32":
        return None
    try:
        import ctypes as c
        from ctypes import wintypes as w

        class GUIInfo(c.Structure):
            _fields_ = [("cbSize", w.DWORD), ("flags", w.DWORD),
                        ("active", w.HWND), ("focus", w.HWND),
                        ("capture", w.HWND), ("menu", w.HWND),
                        ("move", w.HWND), ("caret", w.HWND), ("rect", w.RECT)]

        api = _native_api()
        api.GetGUIThreadInfo.argtypes = [w.DWORD, c.POINTER(GUIInfo)]
        info = GUIInfo(cbSize=c.sizeof(GUIInfo))
        if not api.GetGUIThreadInfo(0, c.byref(info)) or not info.focus:
            return None
        hwnd = info.focus
        name = c.create_unicode_buffer(256)
        api.GetClassNameW(hwnd, name, len(name))
        # Browser canvases, rich editors, password and read-only fields fail closed.
        if (name.value.lower() != "edit" or not api.IsWindowUnicode(hwnd)
                or not api.IsWindowEnabled(hwnd) or api.GetWindowLongW(hwnd, -16) & 0x820):
            return None
        pid = w.DWORD()
        api.GetWindowThreadProcessId(hwnd, c.byref(pid))
        length = _send(api, hwnd, 0xE)  # WM_GETTEXTLENGTH
        if length > 65535:
            return None
        buffer = c.create_unicode_buffer(length + 1)
        _send(api, hwnd, 0xD, length + 1, c.addressof(buffer))  # WM_GETTEXT
        selection = _send(api, hwnd, 0xB0)  # EM_GETSEL, packed offsets below 64K
        start, end = selection & 0xFFFF, selection >> 16
        if selection == 0xFFFFFFFF or end > _units(buffer.value):
            return None
        return Field((int(info.active or 0), int(hwnd), pid.value), buffer.value, start, end)
    except (OSError, ValueError, AttributeError, UnicodeError):
        return None


def capture(before: Field | None, inserted: str) -> Receipt | None:
    """Prove that exactly this insertion happened at the original selection."""
    if before is None:
        return None
    after = read_field()
    inserted = inserted.replace("\r\n", "\n").replace("\n", "\r\n")
    caret = before.start + _units(inserted)
    if (after is not None and before.identity == after.identity
            and after.start == after.end == caret
            and after.text == _splice(before.text, before.start, before.end, inserted)):
        return Receipt(before, after)
    return None


def replace(receipt: Receipt | None, text: str | None) -> tuple[str, Receipt | None]:
    """Replace this insertion, or restore its original selection for scratch.

    Returns replaced, unavailable, or failed. Failed may mean an uncertain
    delivery; never retry automatically after a mutation has been attempted.
    """
    if receipt is None or read_field() != receipt.after:
        return "unavailable", None
    try:
        import ctypes as c
        before, after = receipt.before, receipt.after
        if text is None:
            raw = before.text.encode("utf-16-le")
            text = raw[before.start * 2:before.end * 2].decode("utf-16-le")
        else:
            text = text.replace("\r\n", "\n").replace("\n", "\r\n")
        api = _native_api()
        hwnd = after.identity[1]
        _send(api, hwnd, 0xB1, before.start, after.end)  # EM_SETSEL
        selected = read_field()
        if selected != Field(after.identity, after.text, before.start, after.end):
            return "failed", None
        buffer = c.create_unicode_buffer(text)
        _send(api, hwnd, 0xC2, 1, c.addressof(buffer))  # EM_REPLACESEL, undoable
        current = read_field()
        caret = before.start + _units(text)
        expected = Field(before.identity, _splice(before.text, before.start, before.end, text), caret, caret)
        if current != expected:
            return "failed", None
        return "replaced", Receipt(before, current)
    except (OSError, ValueError, AttributeError, UnicodeError):
        return "failed", None
