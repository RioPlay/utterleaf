import pytest

from utterleaf import host
from utterleaf.settings import hotkey_presets


def test_windows_default_hotkey_is_ctrl_win(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(host.sys, "platform", "win32")
    assert host.default_hotkey() == "ctrl+win"
    assert host.pill_kind() == "win32"
    assert host.paste_backend() == "sendinput"
    assert host.login_label() == "Start with Windows"
    assert host.ui_font() == "Segoe UI"
    assert host.accessibility_trusted() is None


def test_mac_and_linux_share_a_portable_hotkey(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(host.sys, "platform", "darwin")
    assert host.default_hotkey() == "ctrl+shift+space"
    assert host.pill_kind() == "tk-subprocess"
    assert host.paste_backend() == "osascript"
    assert host.ui_font() == ".AppleSystemUIFont"
    assert "Accessibility" in host.settings_blurb()

    monkeypatch.setattr(host.sys, "platform", "linux")
    assert host.default_hotkey() == "ctrl+shift+space"
    assert host.pill_kind() == "tk-subprocess"
    assert host.login_label() == "Start at login"


def test_wayland_blurb_and_doctor(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(host.sys, "platform", "linux")
    monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
    monkeypatch.setattr(host.shutil, "which", lambda _name: None)
    assert host.is_wayland() is True
    assert "utterleaf --toggle" in host.settings_blurb()
    lines = "\n".join(host.doctor_host_lines())
    assert "wayland:" in lines
    assert "paste helper: MISSING" in lines
    assert host.paste_backend() == "none"


def test_linux_paste_helper_matches_session(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(host.sys, "platform", "linux")
    monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
    monkeypatch.setattr(host.shutil, "which", lambda name: name in {"wtype", "xdotool"})
    assert host.paste_backend() == "wtype"
    monkeypatch.setenv("XDG_SESSION_TYPE", "x11")
    assert host.paste_backend() == "xdotool"


def test_hotkey_presets_lead_with_platform_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("utterleaf.settings.default_hotkey", lambda: "ctrl+shift+space")
    presets = hotkey_presets()
    assert presets[0] == ("Ctrl+Shift+Space", "ctrl+shift+space")
    assert presets[-1] == ("Custom…", "")
    values = [value for _label, value in presets]
    assert values.count("ctrl+shift+space") == 1
