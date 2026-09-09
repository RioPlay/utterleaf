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


def pin_tray_backend() -> None:
    """Choose the Linux tray backend before pystray imports.

    pystray's own backend chain treats only ImportError as retryable, but a
    missing GI typelib makes gi.require_version raise ValueError, which would
    kill the app during `from pystray import ...`. Probe the GI stack here
    with broad handling and pin the first backend pystray would have picked.
    With no GI at all, leave pystray's chain untouched — every gi-based import
    then fails with ImportError and it lands on xorg on its own.
    """
    import importlib

    if sys.platform in ("win32", "darwin") or os.environ.get("PYSTRAY_BACKEND"):
        return
    try:
        import gi
    except Exception:
        return
    for name in ("AppIndicator3", "AyatanaAppIndicator3"):
        try:
            gi.require_version("Gtk", "3.0")
            gi.require_version(name, "0.1")
            importlib.import_module("gi.repository.Gtk")
            importlib.import_module(f"gi.repository.{name}")
        except Exception:
            continue
        os.environ["PYSTRAY_BACKEND"] = "appindicator"
        return
    try:
        gi.require_version("Gtk", "3.0")
        importlib.import_module("gi.repository.Gtk")
    except Exception:
        os.environ["PYSTRAY_BACKEND"] = "xorg"
        return
    os.environ["PYSTRAY_BACKEND"] = "gtk"


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
        # XTest can report success against XWayland without delivering keys
        # to the focused native Wayland client. Never treat it as a fallback.
        return ("wtype", "ydotool")
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
        lines.append("wayland shortcuts: press once to start, again to stop; global hold/Esc listening is unavailable")
        lines.append(f"desktop: {os.environ.get('XDG_CURRENT_DESKTOP') or 'unknown'}")
        lines.append("XWayland: " + ("DISPLAY is set (connection not tested)" if os.environ.get("DISPLAY") else "MISSING DISPLAY — Settings requires XWayland"))
        lines.append("wayland paste: wtype requires virtual-keyboard protocol support; ydotool requires its daemon and input permissions")
        lines.append("wayland paste: installed helpers are not proof of successful delivery; xdotool is excluded")
        missing = [name for name in ("wl-copy", "wl-paste") if not shutil.which(name)]
        lines.append("wayland clipboard: " + ("MISSING " + ", ".join(missing) + " (install wl-clipboard)" if missing else "wl-copy and wl-paste installed (access not tested)"))
    if paste_backend() == "none":
        lines.append("paste helper: MISSING (install/configure " + " or ".join(linux_helpers()) + ")")
    return lines
