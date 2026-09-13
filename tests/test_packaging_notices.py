"""The reviewed bundled model must carry full upstream and runtime notices."""
import importlib.util
from pathlib import Path
import shutil

import pytest


@pytest.fixture
def notices(tmp_path, monkeypatch):
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location("utterleaf_notices_test", root / "packaging" / "collect_notices.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "DIST", tmp_path / "bundle")
    monkeypatch.setattr(module, "SITE", tmp_path / "site")
    model = module.DIST / "_internal" / "faster_whisper" / "assets" / "silero_vad_v6.onnx"
    model.parent.mkdir(parents=True)
    for package, version in (("faster_whisper", "1.2.1"), ("onnxruntime", "1.28.0")):
        for base in (module.SITE, module.DIST / "_internal"):
            info = base / f"{package}-{version}.dist-info"
            info.mkdir(parents=True)
            (info / "METADATA").write_text(f"Name: {package}\nVersion: {version}\n", encoding="utf-8")
    installed = root / ".venv" / "Lib" / "site-packages" / "faster_whisper" / "assets" / model.name
    if not installed.is_file():
        from importlib.resources import files
        installed = Path(str(files("faster_whisper").joinpath("assets", model.name)))
    if not installed.is_file():
        pytest.skip("Reviewed local asset unavailable; never download for a notice test")
    shutil.copy2(installed, model)
    runtime = module.SITE / "onnxruntime"
    runtime.mkdir(parents=True)
    (runtime / "LICENSE").write_text("Full runtime license fixture", encoding="utf-8")
    (runtime / "ThirdPartyNotices.txt").write_text("Full dependency notices fixture", encoding="utf-8")
    return module, model, tmp_path / "licenses"


def test_model_and_runtime_receive_full_notices(notices):
    module, model, output = notices
    row = module.copy_vad_notices(output)
    assert row[0] == "Silero VAD"
    assert "Copyright (c) 2020-present Silero Team" in (output / "silero_vad" / "LICENSE.txt").read_text()
    assert "Permission is hereby granted" in (output / "silero_vad" / "LICENSE.txt").read_text()
    assert (output / "onnxruntime" / "LICENSE").read_text() == "Full runtime license fixture"
    assert (output / "onnxruntime" / "ThirdPartyNotices.txt").read_text() == "Full dependency notices fixture"


def test_wrong_model_bytes_prevent_distribution(notices):
    module, model, output = notices
    data = bytearray(model.read_bytes())
    data[-1] ^= 1
    model.write_bytes(data)
    with pytest.raises(SystemExit, match="identity is unreviewed"):
        module.copy_vad_notices(output)
    assert not output.exists()


def test_missing_full_runtime_notice_prevents_distribution(notices):
    module, model, output = notices
    (module.SITE / "onnxruntime" / "ThirdPartyNotices.txt").rename(module.SITE / "unexpected-name.txt")
    with pytest.raises(SystemExit, match="required VAD/runtime notice missing"):
        module.copy_vad_notices(output)


def test_unreviewed_bundled_wrapper_prevents_distribution(notices):
    module, model, output = notices
    info = module.DIST / "_internal" / "faster_whisper-1.2.1.dist-info" / "METADATA"
    info.write_text("Name: faster-whisper\nVersion: 2.0.0\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="unreviewed faster_whisper version"):
        module.copy_vad_notices(output)
    assert not output.exists()
