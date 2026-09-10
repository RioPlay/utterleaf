"""Raise an existing app window after an explicit user activation request."""

import sys


def _user32():
    import ctypes as c
    from ctypes import wintypes as w
    api = c.WinDLL("user32", use_last_error=True)
    api.AllowSetForegroundWindow.argtypes = [w.DWORD]
    api.AllowSetForegroundWindow.restype = w.BOOL
    api.GetAncestor.argtypes = [w.HWND, w.UINT]
    api.GetAncestor.restype = w.HWND
    api.IsIconic.argtypes = [w.HWND]
    api.IsIconic.restype = w.BOOL
    api.ShowWindow.argtypes = [w.HWND, c.c_int]
    api.ShowWindow.restype = w.BOOL
    api.SetForegroundWindow.argtypes = [w.HWND]
    api.SetForegroundWindow.restype = w.BOOL
    return api


def allow_activation(pid: int) -> bool:
    """Pass a tray click's Windows foreground permission to this window owner only.

    https://learn.microsoft.com/windows/win32/api/winuser/nf-winuser-allowsetforegroundwindow
    Never use ASFW_ANY or change global foreground-lock settings.
    """
    if sys.platform != "win32" or type(pid) is not int or not 0 < pid < 0xFFFFFFFF:
        return False
    try:
        return bool(_user32().AllowSetForegroundWindow(pid))
    except (OSError, AttributeError):
        return False


def raise_window(root) -> None:
    """Run on Tk's main thread. Preserve edits and modal dialogs, never pin topmost."""
    if root.state() in {"withdrawn", "iconic"}:
        root.deiconify()
    root.lift()
    root.update_idletasks()
    modal = root.grab_current()
    target = modal.winfo_toplevel() if modal is not None and modal.winfo_exists() else root
    target.lift()
    if sys.platform == "win32":
        try:
            api = _user32()
            hwnd = api.GetAncestor(target.winfo_id(), 2) or target.winfo_id()  # GA_ROOT
            if api.IsIconic(hwnd):
                api.ShowWindow(hwnd, 9)  # SW_RESTORE only for minimized windows.
            if not api.SetForegroundWindow(hwnd):
                # Windows may refuse focus even after a user activation. Raise
                # this requested window visibly without leaving it always-on-top.
                was_topmost = target.attributes("-topmost")
                try:
                    target.attributes("-topmost", True)
                    target.update_idletasks()
                finally:
                    target.attributes("-topmost", was_topmost)
        except (OSError, AttributeError):
            pass
    target.focus_force()
