"""Ensure WAV support does not accidentally reintroduce excluded codec binaries."""

import importlib.util
import runpy
import sys
from types import ModuleType, SimpleNamespace
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


def test_macos_spec_removes_foreign_asio_data_and_binaries(monkeypatch):
    root = Path(__file__).resolve().parents[1]
    captured = SimpleNamespace(analysis=None)

    def analysis(*_args, **_kwargs):
        captured.analysis = SimpleNamespace(
            pure=[], scripts=[],
            binaries=[("sounddevice/libportaudio64bit-asio.dll", "source", "BINARY"),
                      ("native.dylib", "source", "BINARY")],
            datas=[("_sounddevice_data/libportaudio32bit-asio.dll", "source", "DATA"),
                   ("README.md", "source", "DATA")],
        )
        return captured.analysis

    api = ModuleType("PyInstaller.building.api")
    api.Analysis = analysis
    api.EXE = lambda *_args, **_kwargs: object()
    api.PYZ = lambda *_args, **_kwargs: object()
    api.COLLECT = lambda *_args, **_kwargs: None
    hooks = ModuleType("PyInstaller.utils.hooks")
    hooks.collect_data_files = lambda *_args, **_kwargs: []
    hooks.collect_dynamic_libs = lambda *_args, **_kwargs: []
    hooks.copy_metadata = lambda *_args, **_kwargs: []
    monkeypatch.setitem(sys.modules, "PyInstaller", ModuleType("PyInstaller"))
    monkeypatch.setitem(sys.modules, "PyInstaller.building", ModuleType("PyInstaller.building"))
    monkeypatch.setitem(sys.modules, "PyInstaller.building.api", api)
    monkeypatch.setitem(sys.modules, "PyInstaller.utils", ModuleType("PyInstaller.utils"))
    monkeypatch.setitem(sys.modules, "PyInstaller.utils.hooks", hooks)
    monkeypatch.setattr(sys, "platform", "darwin")

    runpy.run_path(
        root / "packaging" / "utterleaf.spec",
        init_globals={"SPECPATH": str(root / "packaging"), "Analysis": analysis},
    )

    assert [item[0] for item in captured.analysis.binaries] == ["native.dylib"]
    assert [item[0] for item in captured.analysis.datas] == ["README.md"]
