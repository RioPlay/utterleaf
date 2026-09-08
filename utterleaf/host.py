"""Facts about the machine Utterleaf is running on. One place for OS forks."""

from __future__ import annotations

import os
import shutil
import sys


def default_hotkey() -> str:
    """Push-to-talk combo that does not fight this OS. Windows keeps Ctrl+Win."""
    if sys.platform == "win32":
        return "ctrl+win"
    return "ctrl+shift+space"


def login_label() -> str:
    if sys.platform == "win32":
        return "Start with Windows"
    return "Start at login"


def ui_font() -> str:
    if sys.platform == "win32":
        return "Segoe UI"
    if sys.platform == "darwin":
        return ".AppleSystemUIFont"
    return "sans-serif"


def session_type() -> str:
    if sys.platform.startswith("linux"):
        session = (os.environ.get("XDG_SESSION_TYPE") or "").lower()
        if session:
            return session
        if os.environ.get("WAYLAND_DISPLAY"):
            return "wayland"
        return "unknown"
    if sys.platform == "darwin":
        return "aqua"
    if sys.platform == "win32":
        return "win32"
    return sys.platform


def is_wayland() -> bool:
    return session_type() == "wayland"


def pill_kind() -> str:
    """win32 = in-process native overlay. tk-subprocess = Tk on its own main thread."""
    if sys.platform == "win32":
        return "win32"
    return "tk-subprocess"


def paste_backend() -> str:
    if sys.platform == "win32":
        return "sendinput"
    if sys.platform == "darwin":
        return "osascript"
    # wtype speaks Wayland; xdotool speaks X11. Prefer the helper that matches
    # the session so an installed-but-incompatible tool does not get reported
    # as usable. ydotool can work without either display protocol.
    for name in linux_helpers():
        if shutil.which(name):
            return name
    return "none"


def linux_helpers() -> tuple[str, ...]:
    """Paste/key helpers ordered for the active Linux display session."""
    if is_wayland():
        return ("wtype", "ydotool", "xdotool")
    return ("xdotool", "ydotool", "wtype")


def accessibility_trusted() -> bool | None:
    """macOS Accessibility for the hotkey and paste. None = not a Mac."""
    if sys.platform != "darwin":
        return None
    try:
        import ctypes

        lib = ctypes.cdll.LoadLibrary(
            "/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices"
        )
        lib.AXIsProcessTrusted.restype = ctypes.c_bool
        lib.AXIsProcessTrusted.argtypes = []
        return bool(lib.AXIsProcessTrusted())
    except Exception:
        return None


def settings_blurb() -> str:
    """One line under the Settings title. Platform-specific, still one window."""
    if sys.platform == "darwin":
        return (
            "Grant Microphone and Accessibility in System Settings, "
            "or the hotkey and paste will do nothing."
        )
    if is_wayland():
        return (
            "On Wayland, bind a desktop shortcut to utterleaf --toggle. "
            "Global key listening is disabled; Settings requires XWayland."
        )
    return "Hold or press the hotkey, speak, and clean text lands in the focused app."


def doctor_host_lines() -> list[str]:
    """Environment facts for --doctor. Missing pieces are spelled out."""
    lines = [
        f"os: {sys.platform}",
        f"session: {session_type()}",
        f"pill: {pill_kind()}",
        f"paste: {paste_backend()}",
        f"default hotkey: {default_hotkey()}",
    ]
    trusted = accessibility_trusted()
    if trusted is True:
        lines.append("accessibility: ok")
    elif trusted is False:
        lines.append("accessibility: MISSING — grant in System Settings")
    if is_wayland():
        lines.append("wayland: bind a desktop shortcut to: utterleaf --toggle")
    if paste_backend() == "none":
        lines.append("paste helper: MISSING (install wtype, xdotool, or ydotool)")
    return lines
