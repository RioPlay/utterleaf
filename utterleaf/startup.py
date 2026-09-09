"""Enable or disable start at login. Windows Startup folder or Linux autostart."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from utterleaf.config import atomic_write_text


LAUNCH_AGENT_LABEL = "com.utterleaf.agent"


def startup_dir() -> Path:
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA", str(Path.home() / "AppData" / "Roaming"))
        return Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "LaunchAgents"
    xdg = os.environ.get("XDG_CONFIG_HOME")
    config = Path(xdg) if xdg else Path.home() / ".config"
    return config / "autostart"


def startup_script() -> Path:
    if sys.platform == "win32":
        return startup_dir() / "Utterleaf.vbs"
    if sys.platform == "darwin":
        return startup_dir() / f"{LAUNCH_AGENT_LABEL}.plist"
    return startup_dir() / "utterleaf.desktop"


def pythonw_path() -> Path:
    exe = Path(sys.executable)
    candidate = exe.with_name("pythonw.exe")
    return candidate if candidate.exists() else exe


def tray_exe() -> Path | None:
    if getattr(sys, "frozen", False):
        exe = Path(sys.executable)
        if sys.platform == "win32":
            gui = exe.with_name("utterleafw.exe")
            if gui.exists():
                return gui
        return exe
    scripts = Path(sys.executable).parent
    for name in ("utterleaf-tray.exe", "utterleafw.exe"):
        path = scripts / name
        if path.exists():
            return path
    return None


def enabled() -> bool:
    return startup_script().is_file()


def install() -> Path:
    dest = startup_script()
    dest.parent.mkdir(parents=True, exist_ok=True)
    if sys.platform == "win32":
        tray = tray_exe()
        if tray is not None:
            target = str(tray).replace("\\", "\\\\")
            atomic_write_text(dest,
                f'CreateObject("Wscript.Shell").Run """{target}""", 0\n',
            )
            return dest
        pythonw = str(pythonw_path()).replace("\\", "\\\\")
        atomic_write_text(dest,
            f'CreateObject("Wscript.Shell").Run """{pythonw}"" -m utterleaf", 0\n',
        )
        return dest

    exe = Path(sys.executable).absolute()
    frozen = bool(getattr(sys, "frozen", False))
    launch_exe = tray_exe() if frozen else exe
    assert launch_exe is not None

    if sys.platform == "darwin":
        atomic_write_text(dest, plist_text(launch_exe, frozen=frozen))
        # Best effort: without this the agent only starts at the next login.
        try:
            subprocess.run(
                ["launchctl", "load", "-w", str(dest)],
                check=False,
                capture_output=True,
            )
        except Exception:
            pass
        return dest

    command = _desktop_quote(str(launch_exe))
    if not frozen:
        command += " -m utterleaf"
    atomic_write_text(dest,
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Name=Utterleaf\n"
        "Comment=Push-to-talk dictation\n"
        f"Exec={command}\n"
        "X-GNOME-Autostart-enabled=true\n",
    )
    return dest


def _xml_escape(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def plist_text(exe: Path, *, frozen: bool = False) -> str:
    """LaunchAgent that starts Utterleaf at login. Written to ~/Library/LaunchAgents."""
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
        '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
        '<plist version="1.0">\n'
        "<dict>\n"
        "\t<key>Label</key>\n"
        f"\t<string>{LAUNCH_AGENT_LABEL}</string>\n"
        "\t<key>ProgramArguments</key>\n"
        "\t<array>\n"
        f"\t\t<string>{_xml_escape(str(exe))}</string>\n"
        + ("\t\t<string>-m</string>\n\t\t<string>utterleaf</string>\n" if not frozen else "")
        + "\t</array>\n"
        "\t<key>RunAtLoad</key>\n"
        "\t<true/>\n"
        "\t<key>ProcessType</key>\n"
        "\t<string>Interactive</string>\n"
        "</dict>\n"
        "</plist>\n"
    )


def uninstall() -> bool:
    path = startup_script()
    if not path.exists():
        return False
    if sys.platform == "darwin":
        try:
            subprocess.run(
                ["launchctl", "unload", "-w", str(path)],
                check=False,
                capture_output=True,
            )
        except Exception:
            pass
    path.unlink()
    return True


def _desktop_quote(value: str) -> str:
    """Quote one Exec argument using the freedesktop Desktop Entry rules."""
    escaped = value.replace("\\", "\\\\")
    escaped = escaped.replace('"', '\\"').replace("`", "\\`").replace("$", "\\$")
    # A literal percent must not be interpreted as an Exec field code.
    escaped = escaped.replace("%", "%%")
    return f'"{escaped}"'


def set_enabled(on: bool) -> bool:
    if on:
        install()
        return True
    uninstall()
    return False
