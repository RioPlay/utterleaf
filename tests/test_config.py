from utterleaf.config import Config, _dump_toml, _parse_toml, ensure_files
from utterleaf.host import default_hotkey
import pytest


def test_round_trip_defaults() -> None:
    text = _dump_toml(Config())
    parsed = _parse_toml(text)
    loaded = Config(**{k: v for k, v in parsed.items() if hasattr(Config, k)})
    assert loaded.hotkey == default_hotkey()
    assert loaded.model == "small"
    assert loaded.microphone == ""
    assert loaded.remove_fillers is True
    assert not hasattr(loaded, "polish")


def test_live_preview_defaults_off() -> None:
    cfg = Config()
    assert cfg.live_preview is False
    parsed = _parse_toml(_dump_toml(cfg))
    assert parsed["live_preview"] is False
    loaded = Config(**{k: v for k, v in parsed.items() if hasattr(Config, k)})
    assert loaded.live_preview is False


def test_unchanged_transcript_preference_survives_config_roundtrip():
    values = _parse_toml(_dump_toml(Config(text_cleanup=False)))
    assert Config(**values).text_cleanup is False


def test_markdown_output_preference_survives_config_roundtrip():
    values = _parse_toml(_dump_toml(Config(output_format="markdown")))
    assert Config(**values).output_format == "markdown"


def test_speech_end_preferences_survive_config_roundtrip():
    values = _parse_toml(_dump_toml(Config(
        speech_end_enabled=True, speech_end_pause_seconds=1.8, speech_end_insert=True)))
    loaded = Config(**values)
    assert loaded.speech_end_enabled is True
    assert loaded.speech_end_pause_seconds == 1.8
    assert loaded.speech_end_insert is True


def test_invalid_speech_end_config_fails_closed(tmp_path, monkeypatch):
    monkeypatch.setattr("utterleaf.config.config_path", lambda: tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(
        'speech_end_enabled = "true"\nspeech_end_insert = "true"\n'
        'speech_end_pause_seconds = 99\n', encoding="utf-8")
    from utterleaf.config import load

    loaded = load()
    assert loaded.speech_end_enabled is False
    assert loaded.speech_end_insert is False
    assert loaded.speech_end_pause_seconds == 1.2


def test_first_run_does_not_enable_startup(tmp_path, monkeypatch) -> None:
    called = {"n": 0}
    monkeypatch.setattr("utterleaf.config.data_dir", lambda: tmp_path)
    monkeypatch.setattr("utterleaf.config.config_path", lambda: tmp_path / "config.toml")
    monkeypatch.setattr("utterleaf.config.dictionary_path", lambda: tmp_path / "dictionary.txt")
    monkeypatch.setattr("sys.platform", "win32")

    def fake_install():
        called["n"] += 1
        return tmp_path / "Utterleaf.vbs"

    monkeypatch.setattr("utterleaf.startup.install", fake_install)
    ensure_files()
    assert called["n"] == 0
    ensure_files()
    assert called["n"] == 0


def test_legacy_cloud_polish_keys_are_ignored(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("utterleaf.config.data_dir", lambda: tmp_path)
    monkeypatch.setattr("utterleaf.config.config_path", lambda: tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(
        'polish = "ollama"\nollama_model = "llama3.2"\nhotkey = "f8"\n',
        encoding="utf-8",
    )
    from utterleaf.config import load

    cfg = load()
    assert cfg.hotkey == "f8"
    assert not hasattr(cfg, "polish")
    assert not hasattr(cfg, "ollama_model")


def test_new_config_uses_this_os_hotkey(monkeypatch) -> None:
    monkeypatch.setattr("utterleaf.host.sys.platform", "darwin")
    assert Config().hotkey == "ctrl+shift+space"


def test_strings_with_quotes_and_paths_round_trip():
    cfg = Config(microphone='USB "Studio" \\ Input', model='C:\\models\\small', language="en\n")
    values = _parse_toml(_dump_toml(cfg))
    assert values["microphone"] == cfg.microphone
    assert values["model"] == cfg.model
    assert values["language"] == cfg.language


def test_failed_atomic_save_preserves_previous_config(tmp_path, monkeypatch):
    from pathlib import Path
    from utterleaf.config import save
    target = tmp_path / "config.toml"
    target.write_text('hotkey = "f8"', encoding="utf-8")
    monkeypatch.setattr("utterleaf.config.config_path", lambda: target)
    def fail(*_):
        raise OSError("disk unavailable")
    monkeypatch.setattr(Path, "replace", fail)
    with pytest.raises(OSError):
        save(Config())
    assert target.read_text() == 'hotkey = "f8"'
    assert list(tmp_path.iterdir()) == [target]
