from pathlib import Path

import pytest

from utterleaf import startup


def test_frozen_startup_prefers_windowless_entry(tmp_path, monkeypatch):
    monkeypatch.setattr(startup.sys, "platform", "win32")
    monkeypatch.setattr(startup.sys, "frozen", True, raising=False)
    monkeypatch.setattr(startup.sys, "executable", str(tmp_path / "utterleaf-cli.exe"))
    gui = tmp_path / "utterleafw.exe"
    gui.touch()
    assert startup.tray_exe() == gui


def test_install_writes_vbs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # This test exercises the Windows Startup-folder format on every CI host.
    monkeypatch.setattr(startup.sys, "platform", "win32")
    monkeypatch.setattr(startup, "startup_dir", lambda: tmp_path)
    path = startup.install()
    assert path.name == "Utterleaf.vbs"
    text = path.read_text(encoding="utf-8")
    assert "utterleaf" in text.lower()
    assert startup.enabled() is True
    startup.set_enabled(False)
    assert startup.enabled() is False


def test_macos_uses_launch_agent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(startup.sys, "platform", "darwin")
    monkeypatch.setattr(startup, "startup_dir", lambda: tmp_path)
    monkeypatch.setattr(startup.subprocess, "run", lambda *args, **kwargs: None)
    path = startup.install()
    assert path.name == f"{startup.LAUNCH_AGENT_LABEL}.plist"
    text = path.read_text(encoding="utf-8")
    assert "<key>RunAtLoad</key>" in text
    assert "<string>utterleaf</string>" in text
    assert startup.enabled() is True
    assert startup.uninstall() is True
    assert startup.enabled() is False


def test_macos_never_writes_a_desktop_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A .desktop file in ~/.config/autostart is inert on macOS: the old bug.
    monkeypatch.setattr(startup.sys, "platform", "darwin")
    monkeypatch.setattr(startup, "startup_dir", lambda: tmp_path)
    startup.install()
    assert not list(tmp_path.glob("*.desktop"))


def test_linux_writes_desktop_entry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(startup.sys, "platform", "linux")
    monkeypatch.setattr(startup, "startup_dir", lambda: tmp_path)
    monkeypatch.setattr(startup.sys, "executable", str(tmp_path / "venv root" / "bin" / "python3"))
    path = startup.install()
    assert path.name == "utterleaf.desktop"
    text = path.read_text(encoding="utf-8")
    assert "[Desktop Entry]" in text
    assert 'Exec="' in text
    assert '" -m utterleaf' in text


def test_frozen_linux_desktop_omits_module_args(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(startup.sys, "platform", "linux")
    monkeypatch.setattr(startup.sys, "frozen", True, raising=False)
    monkeypatch.setattr(startup.sys, "executable", str(tmp_path / "Utterleaf" / "utterleaf"))
    monkeypatch.setattr(startup, "startup_dir", lambda: tmp_path)
    path = startup.install()
    text = path.read_text(encoding="utf-8")
    assert f"Exec={startup._desktop_quote(str(tmp_path / 'Utterleaf' / 'utterleaf'))}" in text
    assert "-m utterleaf" not in text


def test_frozen_macos_plist_omits_module_args() -> None:
    text = startup.plist_text(Path("/Applications/Utterleaf.app/Contents/MacOS/utterleaf"), frozen=True)
    assert "<string>-m</string>" not in text
    assert "<string>utterleaf</string>" not in text


def test_linux_startup_preserves_interpreter_symlink(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real = tmp_path / "real-python"
    link = tmp_path / "venv-python"
    real.write_text("", encoding="utf-8")
    try:
        link.symlink_to(real)
    except OSError as exc:
        pytest.skip(f"symlinks unavailable: {exc}")
    monkeypatch.setattr(startup.sys, "platform", "linux")
    monkeypatch.setattr(startup.sys, "executable", str(link))
    monkeypatch.setattr(startup, "startup_dir", lambda: tmp_path / "autostart")
    text = startup.install().read_text(encoding="utf-8")
    assert startup._desktop_quote(str(link)) in text


def test_linux_desktop_escapes_exec_reserved_characters(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(startup.sys, "platform", "linux")
    monkeypatch.setattr(startup, "startup_dir", lambda: tmp_path / "autostart")
    executable = tmp_path / '100% "ready"' / ("cost$bin`" + "\\" + "python3")
    monkeypatch.setattr(startup.sys, "executable", str(executable))

    text = startup.install().read_text(encoding="utf-8")
    exec_line = next(line for line in text.splitlines() if line.startswith("Exec="))
    quoted = exec_line.removeprefix("Exec=").removesuffix(" -m utterleaf")

    assert quoted.startswith('"') and quoted.endswith('"')
    assert "100%%" in quoted
    assert r'\"ready\"' in quoted
    assert r"\$bin\`" in quoted
    assert r"\\python3" in quoted


def test_plist_escapes_the_interpreter_path() -> None:
    text = startup.plist_text(Path("/opt/py & co/bin/python3"))
    assert "&amp;" in text
    assert "& co" not in text
