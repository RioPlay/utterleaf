"""Ensure WAV support does not accidentally reintroduce excluded codec binaries."""

import importlib.util
from pathlib import Path

import pytest


def checker():
    path = Path(__file__).resolve().parents[1] / "packaging" / "collect_notices.py"
    spec = importlib.util.spec_from_file_location("utterleaf_notices", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.verify_media_policy


@pytest.mark.parametrize("name", ["avcodec-62.dll", "libavformat.so.62", "libswresample.6.dylib", "ffmpeg.exe"])
def test_packaging_rejects_excluded_codecs(tmp_path, name):
    (tmp_path / name).write_bytes(b"binary placeholder")
    with pytest.raises(SystemExit, match="Excluded media"):
        checker()(tmp_path)


def test_packaging_allows_codec_notice_text_and_numpy(tmp_path):
    (tmp_path / "avcodec-license.txt").write_text("notice", encoding="utf-8")
    (tmp_path / "numpy.dll").write_bytes(b"binary placeholder")
    checker()(tmp_path)
