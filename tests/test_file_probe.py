import json
from pathlib import Path
import subprocess
import sys

import pytest

from utterleaf import file_probe as probe
from utterleaf import file_decoder as decoder
from utterleaf.file_decoder import DecoderSetupError


@pytest.fixture
def settings(tmp_path, monkeypatch):
    path = tmp_path / "file-probe.json"
    monkeypatch.setattr(probe, "_settings_path", lambda: path)
    return path


def executable(tmp_path, name="ffprobe"):
    if sys.platform == "win32":
        name += ".exe"
    path = tmp_path / name
    path.write_bytes(b"MZ synthetic ffprobe executable")
    return path


def test_selection_persists_hash_and_forget_preserves_executable(settings, tmp_path):
    path = executable(tmp_path)
    assert probe.select_probe(path) == path.absolute()
    record = json.loads(settings.read_text(encoding="utf-8"))
    assert record["version"] == 1
    assert record["path"] == str(path.absolute())
    assert len(record["sha256"]) == 64
    assert probe.probe_selection() == record
    assert probe.verified_probe() == path.absolute()
    probe.forget_probe()
    assert probe.probe_selection() is None
    assert path.exists()


def test_selection_never_executes_or_discovers_from_path(settings, tmp_path, monkeypatch):
    path = executable(tmp_path)
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: pytest.fail("must not execute"))
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: pytest.fail("must not execute"))
    monkeypatch.setenv("PATH", str(tmp_path))
    probe.select_probe(path)
    assert probe.probe_selection()["path"] == str(path.absolute())


def test_changed_or_swapped_executable_requires_reselection(settings, tmp_path):
    path = executable(tmp_path)
    probe.select_probe(path)
    path.write_bytes(b"MZ changed ffprobe executable")
    with pytest.raises(DecoderSetupError, match="changed|again"):
        probe.verified_probe()


def test_failed_replacement_preserves_prior_valid_record(settings, tmp_path):
    valid = executable(tmp_path)
    probe.select_probe(valid)
    before = probe.probe_selection()
    with pytest.raises(DecoderSetupError, match="ffprobe executable"):
        probe.select_probe(tmp_path / ("ffmpeg.exe" if sys.platform == "win32" else "ffmpeg"))
    assert probe.probe_selection() == before


def test_no_selection_is_actionable(settings):
    with pytest.raises(DecoderSetupError, match="Select.*FFprobe"):
        probe.verified_probe()


@pytest.mark.parametrize("payload", [
    b" " * (16 * 1024 + 1),
    b"{}",
    b'{"version":2,"path":"x","sha256":"' + b"0" * 64 + b'"}',
    b'{"version":1,"path":"x","sha256":"' + b"G" * 64 + b'"}',
])
def test_settings_are_bounded_and_strict(settings, payload):
    settings.write_bytes(payload)
    with pytest.raises(DecoderSetupError, match="invalid"):
        probe.probe_selection()


def test_settings_symlink_is_rejected(settings, tmp_path):
    target = tmp_path / "target.json"
    target.write_text("{}", encoding="utf-8")
    settings.unlink(missing_ok=True)
    try:
        settings.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation unavailable")
    with pytest.raises(DecoderSetupError, match="regular local"):
        probe.probe_selection()


@pytest.mark.parametrize("name", ["ffmpeg", "installer.cmd", "ffprobe.zip"])
def test_selection_rejects_non_ffprobe_names(settings, tmp_path, name):
    path = tmp_path / name
    path.write_bytes(b"MZ synthetic")
    with pytest.raises(DecoderSetupError, match="ffprobe executable"):
        probe.select_probe(path)


def test_ffmpeg_selection_does_not_create_or_discover_probe(settings, tmp_path, monkeypatch):
    ffmpeg = tmp_path / ("ffmpeg.exe" if sys.platform == "win32" else "ffmpeg")
    ffmpeg.write_bytes(b"MZ synthetic ffmpeg executable")
    adjacent = executable(tmp_path)
    monkeypatch.setattr(decoder, "_settings_path", lambda: tmp_path / "file-decoder.json")
    monkeypatch.setenv("PATH", str(tmp_path))
    decoder.select_decoder(ffmpeg)
    assert adjacent.exists()
    assert probe.probe_selection() is None
    with pytest.raises(DecoderSetupError, match="Select.*FFprobe"):
        probe.verified_probe()


def test_forget_without_selection_is_safe(settings):
    probe.forget_probe()
    assert not settings.exists()
