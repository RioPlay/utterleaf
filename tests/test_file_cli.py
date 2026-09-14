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


@pytest.mark.parametrize("option,expected", [(None, "relative"), ("recording", "recording"), ("relative", "relative")])
def test_cli_clock_choice_reaches_recognizer(tmp_path, monkeypatch, option, expected):
    from utterleaf import config, hardware, file_transcription
    from utterleaf.transcript import Transcript
    source = tmp_path / "recording.mkv"
    source.write_bytes(b"synthetic")
    monkeypatch.setattr(config, "config_path", lambda: tmp_path / "config.toml")
    monkeypatch.setattr(config, "ensure_files", lambda: Config())
    monkeypatch.setattr(hardware, "enable_cuda_libs", lambda: None)
    seen = []
    monkeypatch.setattr(file_transcription, "transcribe_file",
                        lambda *args, **kwargs: seen.append(kwargs["timing"]) or Transcript(()))
    args = ["--transcribe-file", str(source), "--output", str(tmp_path / "output.vtt")]
    if option is not None:
        args.extend(["--file-timing", option])
    assert main(args) == 0
    assert seen == [expected]


@pytest.mark.parametrize("args", [["--file-timing", "recording"], ["--files", "--file-timing", "relative"],
                                  ["--file-timing", "invented"]])
def test_cli_clock_requires_explicit_file_job(args):
    with pytest.raises(SystemExit) as failure:
        main(args)
    assert failure.value.code == 2


def test_cli_repeated_tracks_export_grouped_siblings(tmp_path, monkeypatch):
    from fractions import Fraction
    from utterleaf import config, hardware, file_tracks
    from utterleaf.file_metadata import MediaAudioTrack
    from utterleaf.file_tracks import FileTranscripts, TrackTranscript
    from utterleaf.transcript import Segment, Transcript

    source = tmp_path / "stream.mkv"
    source.write_bytes(b"synthetic")
    monkeypatch.setattr(config, "config_path", lambda: tmp_path / "config.toml")
    monkeypatch.setattr(config, "ensure_files", lambda: Config())
    monkeypatch.setattr(hardware, "enable_cuda_libs", lambda: None)
    seen = []

    def recognize(path, cfg, **kwargs):
        seen.append(kwargs["audio_tracks"])
        tracks = (
            MediaAudioTrack(ordinal=0, stream_index=1, codec="pcm_s16le", sample_rate=16000,
                            channels=1, layout="mono", title="Mix", language=None,
                            is_default=True, start=Fraction(0), time_base=Fraction(1, 16000)),
            MediaAudioTrack(ordinal=2, stream_index=3, codec="pcm_s16le", sample_rate=16000,
                            channels=1, layout="mono", title="Guest", language=None,
                            is_default=False, start=Fraction(1), time_base=Fraction(1, 16000)),
        )
        return FileTranscripts("recording", Fraction(0), "container", (
            TrackTranscript(tracks[0], Transcript((Segment(0, 1, "mix"),))),
            TrackTranscript(tracks[1], Transcript((Segment(0.2, 1, "guest"),))),
        ))

    monkeypatch.setattr(file_tracks, "transcribe_tracks", recognize)
    destination = tmp_path / "show.vtt"
    assert main(["--transcribe-file", str(source), "--audio-track", "1", "--audio-track", "3",
                 "--file-timing", "recording", "--output", str(destination)]) == 0
    assert seen == [(1, 3)]
    assert not destination.exists()
    assert (tmp_path / "show-track1.vtt").read_text(encoding="utf-8").startswith("WEBVTT")
    assert "00:00:00.200" in (tmp_path / "show-track3.vtt").read_text(encoding="utf-8")


def test_cli_duplicate_or_existing_grouped_outputs_are_rejected(tmp_path):
    source = tmp_path / "stream.mkv"
    source.write_bytes(b"fixture")
    existing = tmp_path / "show-track1.vtt"
    existing.write_text("keep")
    with pytest.raises(SystemExit) as duplicate:
        main(["--transcribe-file", str(source), "--audio-track", "1", "--audio-track", "1",
              "--output", str(tmp_path / "show.vtt")])
    assert duplicate.value.code == 2
    with pytest.raises(SystemExit) as occupied:
        main(["--transcribe-file", str(source), "--audio-track", "1", "--audio-track", "2",
              "--output", str(tmp_path / "show.vtt")])
    assert occupied.value.code == 2
    assert existing.read_text() == "keep"
