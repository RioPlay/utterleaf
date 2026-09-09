from utterleaf.config import Config
from utterleaf.polish import dictionary_text
from utterleaf.settings import apply_form
import pytest


def test_apply_form_writes_hotkey(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("utterleaf.settings.save", lambda cfg: tmp_path / "config.toml")
    monkeypatch.setattr("utterleaf.settings.set_startup", lambda on: None)
    cfg = apply_form(
        Config(),
        hotkey="F8",
        mode="hold",
        model="small",
        device="gpu",
        language="en",
        denoise="auto",
        beep=False,
        indicator=True,
        start_at_login=False,
        microphone="USB Mic",
    )
    assert cfg.hotkey == "f8"
    assert cfg.model == "small"
    assert cfg.device == "gpu"
    assert cfg.beep is False
    assert cfg.microphone == "USB Mic"


def test_apply_form_system_default_mic(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("utterleaf.settings.save", lambda cfg: tmp_path / "config.toml")
    monkeypatch.setattr("utterleaf.settings.set_startup", lambda on: None)
    cfg = apply_form(
        Config(microphone="old"),
        hotkey="ctrl+win",
        mode="hold",
        model="small",
        device="auto",
        language="en",
        denoise="auto",
        beep=True,
        indicator=True,
        start_at_login=False,
        microphone="System default",
    )
    assert cfg.microphone == ""


def test_apply_form_writes_names(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("utterleaf.settings.save", lambda cfg: tmp_path / "config.toml")
    monkeypatch.setattr("utterleaf.settings.set_startup", lambda on: None)
    monkeypatch.setattr("utterleaf.polish.dictionary_path", lambda: tmp_path / "dictionary.txt")
    apply_form(
        Config(),
        hotkey="ctrl+win",
        mode="hold",
        model="small",
        device="auto",
        language="en",
        denoise="auto",
        beep=True,
        indicator=True,
        start_at_login=False,
        names="sarah = Sarah\n",
    )
    assert "sarah = Sarah" in dictionary_text()


def test_apply_form_writes_mode_and_preview(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("utterleaf.settings.save", lambda cfg: tmp_path / "config.toml")
    monkeypatch.setattr("utterleaf.settings.set_startup", lambda on: None)
    cfg = apply_form(
        Config(),
        hotkey="ctrl+win",
        mode="toggle",
        model="small",
        device="auto",
        language="en",
        denoise="auto",
        beep=True,
        indicator=True,
        start_at_login=False,
        live_preview=True,
    )
    assert cfg.mode == "toggle"
    assert cfg.live_preview is True


def test_apply_form_rejects_bad_hotkey(monkeypatch) -> None:
    monkeypatch.setattr("utterleaf.settings.save", lambda cfg: None)
    monkeypatch.setattr("utterleaf.settings.set_startup", lambda on: None)
    try:
        apply_form(
            Config(),
            hotkey="not-a-key",
            mode="hold",
            model="base",
            device="auto",
            language="en",
            denoise="auto",
            beep=True,
            indicator=True,
            start_at_login=False,
        )
    except ValueError:
        return
    raise AssertionError("expected ValueError")


@pytest.mark.parametrize("invalid", [{"model": " "}, {"device": "cloud"}, {"language": ""},
                                     {"denoise": "invalid"}, {"names": "missing separator"}])
def test_invalid_settings_do_not_write_any_files(monkeypatch, invalid):
    written = []
    monkeypatch.setattr("utterleaf.settings.save", lambda cfg: written.append("config"))
    monkeypatch.setattr("utterleaf.settings.save_dictionary", lambda text: written.append("names"))
    monkeypatch.setattr("utterleaf.settings.set_startup", lambda on: written.append("startup"))
    values = dict(hotkey="f8", mode="hold", model="small", device="auto", language="en",
                  denoise="auto", beep=True, indicator=True, start_at_login=False)
    with pytest.raises(ValueError):
        apply_form(Config(), **{**values, **invalid})
    assert not written


def test_relaunch_python_on_posix_keeps_module_entrypoint(monkeypatch):
    from pathlib import Path
    from utterleaf.settings import _relaunch
    monkeypatch.setattr("utterleaf.settings.sys.platform", "linux")
    monkeypatch.setattr("utterleaf.settings.sys.executable", "/opt/utterleaf/python")
    monkeypatch.setattr("utterleaf.settings.sys.frozen", False, raising=False)
    calls = []
    monkeypatch.setattr("utterleaf.settings.subprocess.Popen", lambda cmd, **kw: calls.append(cmd))
    _relaunch("--settings")
    assert calls == [[str(Path("/opt/utterleaf/python")), "-m", "utterleaf", "--settings"]]


def test_frozen_settings_relaunch_uses_gui_and_hides_console(tmp_path, monkeypatch):
    from utterleaf import settings
    monkeypatch.setattr(settings.sys, "platform", "win32")
    monkeypatch.setattr(settings.sys, "frozen", True, raising=False)
    monkeypatch.setattr(settings.sys, "executable", str(tmp_path / "utterleaf-cli.exe"))
    monkeypatch.setattr(settings.subprocess, "CREATE_NO_WINDOW", 0x08000000, raising=False)
    gui = tmp_path / "utterleafw.exe"
    gui.touch()
    calls = []
    monkeypatch.setattr(settings.subprocess, "Popen", lambda cmd, **kw: calls.append((cmd, kw)))
    settings._relaunch("--settings")
    assert calls[0][0] == [str(gui), "--settings"]
    assert calls[0][1]["creationflags"] & 0x08000000


@pytest.mark.parametrize("failure_index", [0, 1, 2])
def test_save_failure_reports_completed_and_unattempted_steps(monkeypatch, failure_index):
    from utterleaf import settings
    labels = ["dictation settings", "vocabulary", "start at login"]
    calls = []
    def action(index):
        def run(*args):
            calls.append(index)
            if index == failure_index:
                raise OSError("Disk is full")
        return run
    monkeypatch.setattr(settings, "save", action(0))
    monkeypatch.setattr(settings, "save_dictionary", action(1))
    monkeypatch.setattr(settings, "set_startup", action(2))
    with pytest.raises(settings.SettingsSaveError) as caught:
        settings.apply_form(Config(), hotkey="f8", mode="hold", model="small", device="auto",
                            language="en", denoise="auto", beep=True, indicator=True,
                            start_at_login=False, names="utter leaf = Utterleaf")
    assert calls == list(range(failure_index + 1))
    assert caught.value.saved == tuple(labels[:failure_index])
    assert caught.value.failed == labels[failure_index]
    assert caught.value.pending == tuple(labels[failure_index + 1:])
    assert "Disk is full" in str(caught.value)


def test_failed_atomic_write_preserves_old_file_and_removes_temporary(tmp_path, monkeypatch):
    from pathlib import Path
    from utterleaf.config import atomic_write_text
    path = tmp_path / "dictionary.txt"
    path.write_text("old vocabulary", encoding="utf-8")
    def fail(*args):
        raise OSError("Destination locked")
    monkeypatch.setattr(Path, "replace", fail)
    with pytest.raises(OSError):
        atomic_write_text(path, "new vocabulary")
    assert path.read_text(encoding="utf-8") == "old vocabulary"
    assert list(tmp_path.iterdir()) == [path]
