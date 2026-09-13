from pathlib import Path

import pytest

from utterleaf.__main__ import main
from utterleaf.config import Config


def test_file_export_is_explicit_and_does_not_print_transcript(tmp_path, monkeypatch, capsys):
    from utterleaf import config, hardware, file_transcription
    from utterleaf.transcript import Segment, Transcript

    source = tmp_path / "speech.wav"
    source.write_bytes(b"synthetic fixture")
    destination = tmp_path / "speech.txt"
    monkeypatch.setattr(config, "config_path", lambda: tmp_path / "config.toml")
    monkeypatch.setattr(config, "ensure_files", lambda: Config())
    monkeypatch.setattr(hardware, "enable_cuda_libs", lambda: None)
    monkeypatch.setattr(file_transcription, "transcribe_file",
                        lambda *args, **kwargs: Transcript((Segment(0, 1, "Private fixture text"),)))
    assert main(["--transcribe-file", str(source), "--output", str(destination)]) == 0
    assert destination.read_text() == "Private fixture text\n"
    assert "Private fixture text" not in capsys.readouterr().out
    assert source.read_bytes() == b"synthetic fixture"


@pytest.mark.parametrize("extra", [[], ["--doctor"], ["--download-model"]])
def test_file_command_rejects_missing_output_or_other_actions(tmp_path, extra):
    source = tmp_path / "speech.wav"
    source.write_bytes(b"fixture")
    args = ["--transcribe-file", str(source)]
    if extra:
        args += ["--output", str(tmp_path / "out.txt")] + extra
    with pytest.raises(SystemExit) as failure:
        main(args)
    assert failure.value.code == 2


def test_output_cannot_replace_source_even_with_overwrite(tmp_path):
    source = tmp_path / "speech.wav"
    source.write_bytes(b"original")
    with pytest.raises(SystemExit):
        main(["--transcribe-file", str(source), "--output", str(source), "--format", "txt", "--overwrite"])
    assert source.read_bytes() == b"original"


def test_existing_output_is_preserved_without_explicit_overwrite(tmp_path):
    source = tmp_path / "speech.wav"
    source.write_bytes(b"original")
    destination = tmp_path / "out.txt"
    destination.write_text("keep me")
    with pytest.raises(SystemExit):
        main(["--transcribe-file", str(source), "--output", str(destination)])
    assert destination.read_text() == "keep me"


def test_file_window_launches_without_initializing_dictation(monkeypatch):
    import sys
    from types import SimpleNamespace
    from utterleaf import config, hardware

    def unwanted():
        pytest.fail("File window must own initialization without loading the dictation app")

    monkeypatch.setattr(config, "ensure_files", unwanted)
    monkeypatch.setattr(hardware, "enable_cuda_libs", unwanted)
    monkeypatch.setitem(sys.modules, "utterleaf.file_ui", SimpleNamespace(run_files=lambda: 0))
    assert main(["--files"]) == 0


@pytest.mark.parametrize("flag", ["--settings", "--download-model", "--doctor", "--toggle"])
def test_file_window_rejects_conflicting_actions(flag):
    with pytest.raises(SystemExit) as failure:
        main(["--files", flag])
    assert failure.value.code == 2


@pytest.mark.parametrize("args", [["--audio-track", "1"], ["--files", "--audio-track", "2"],
                                  ["--transcribe-file", "x.wav", "--audio-track", "0"],
                                  ["--transcribe-file", "x.wav", "--audio-track", "257"]])
def test_track_choice_requires_file_job_and_valid_ordinal(args):
    with pytest.raises(SystemExit) as error:
        main(args)
    assert error.value.code == 2


def test_cli_selected_track_reaches_recognizer_as_zero_based(tmp_path, monkeypatch):
    from utterleaf import config, hardware, file_transcription
    from utterleaf.transcript import Transcript
    source = tmp_path / "stream.mkv"
    source.write_bytes(b"synthetic")
    monkeypatch.setattr(config, "config_path", lambda: tmp_path / "config.toml")
    monkeypatch.setattr(config, "ensure_files", lambda: Config())
    monkeypatch.setattr(hardware, "enable_cuda_libs", lambda: None)
    seen = []
    def recognize(path, cfg, **kwargs):
        seen.append(kwargs["audio_track"])
        return Transcript(())
    monkeypatch.setattr(file_transcription, "transcribe_file", recognize)
    assert main(["--transcribe-file", str(source), "--audio-track", "3",
                 "--output", str(tmp_path / "third.txt")]) == 0
    assert seen == [2]
