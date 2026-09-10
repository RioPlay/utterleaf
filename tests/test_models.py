from pathlib import Path

import pytest

from utterleaf.models import ct2_ready, ensure_ct2, ov_ready


def test_ct2_ready_needs_bin_and_config(tmp_path: Path) -> None:
    dest = tmp_path / "m"
    dest.mkdir()
    assert not ct2_ready(dest)
    (dest / "model.bin").write_bytes(b"x")
    assert not ct2_ready(dest)
    (dest / "config.json").write_text("{}")
    assert ct2_ready(dest)


def test_ov_ready_needs_xml(tmp_path: Path) -> None:
    dest = tmp_path / "ov"
    dest.mkdir()
    assert not ov_ready(dest)
    (dest / "openvino_model.xml").write_text("<net/>")
    assert ov_ready(dest)


def test_ensure_ct2_uses_local_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("utterleaf.models.models_dir", lambda: tmp_path)
    dest = tmp_path / "faster-whisper-tiny.en"
    dest.mkdir()
    (dest / "model.bin").write_bytes(b"x")
    (dest / "config.json").write_text("{}")

    def fail(*_args, **_kwargs):
        raise AssertionError("must not download when the model is already local")

    monkeypatch.setattr("faster_whisper.utils.download_model", fail)
    assert ensure_ct2("tiny.en", allow_network=True) == dest


def test_ensure_ct2_offline_missing_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("utterleaf.models.models_dir", lambda: tmp_path)
    with pytest.raises(RuntimeError, match="Settings.*Model & installation"):
        ensure_ct2("tiny.en", allow_network=False)
