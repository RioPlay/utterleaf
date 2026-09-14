"""Track inspection remains local, bounded and independent of model loading."""
from fractions import Fraction
import os
from pathlib import Path
import subprocess
import sys
import threading
import wave

import pytest

from utterleaf import file_inspection as inspection
from utterleaf import file_decoder as decoder
from utterleaf import file_probe as probe
from utterleaf.file_metadata import MediaAudioTrack, MediaMetadata
from utterleaf.transcript import TranscriptionCancelled


def write_wav(path, *, channels=2, width=2, rate=44100, frames=100):
    with wave.open(str(path), "wb") as output:
        output.setparams((channels, width, rate, 0, "NONE", ""))
        output.writeframes(bytes(frames * channels * width))


@pytest.mark.parametrize("channels,width,rate", [(1, 1, 8000), (2, 2, 44100), (1, 3, 48000), (2, 4, 16000)])
def test_pcm_wave_needs_no_external_probe_or_model(tmp_path, monkeypatch, channels, width, rate):
    path = tmp_path / "audio.wav"
    write_wav(path, channels=channels, width=width, rate=rate)
    monkeypatch.setattr(inspection, "probe_media", lambda *a, **kw: pytest.fail("PCM needs no probe"))
    result = inspection.inspect_file(path)
    assert result.signature == inspection.current_file_signature(path)
    assert result.metadata.origin == 0
    assert result.metadata.origin_kind == "pcm-sample-clock"
    track, = result.metadata.tracks
    assert (track.ordinal, track.stream_index, track.sample_rate, track.channels) == (0, 0, rate, channels)
    assert track.start == 0 and track.time_base == Fraction(1, rate)
    path.rename(tmp_path / "closed.wav")


def test_other_media_keeps_actual_inspected_ordinals_and_global_indexes(tmp_path, monkeypatch):
    path = tmp_path / "audio.mkv"
    path.write_bytes(b"synthetic")
    expected = MediaMetadata(Fraction(-1), "container", (
        MediaAudioTrack(0, 2, "aac", 48000, 2, "stereo", "Mix", "en", True,
                        Fraction(-1), Fraction(1, 48000)),
    ))
    calls = []
    def probe(selected, *, cancel, require_origin):
        assert require_origin is False
        calls.append(selected)
        return expected
    monkeypatch.setattr(inspection, "probe_media", probe)
    assert inspection.inspect_file(path).metadata is expected
    assert calls == [path.resolve()]


def test_changed_source_is_refused_even_when_probe_returns_metadata(tmp_path, monkeypatch):
    path = tmp_path / "audio.mkv"
    path.write_bytes(b"before")
    def probe(selected, **kwargs):
        selected.write_bytes(b"after, modified")
        return MediaMetadata(Fraction(0), "container", ())
    monkeypatch.setattr(inspection, "probe_media", probe)
    with pytest.raises(ValueError, match="changed"):
        inspection.inspect_file(path)


def test_cancel_before_inspection_does_not_open_file_or_probe(monkeypatch):
    event = threading.Event()
    event.set()
    monkeypatch.setattr(inspection, "probe_media", lambda *a, **kw: pytest.fail("cancelled"))
    with pytest.raises(TranscriptionCancelled):
        inspection.inspect_file("absent.wav", cancel=event)


def test_unsupported_wav_variant_uses_selected_probe(tmp_path, monkeypatch):
    path = tmp_path / "surround.wav"
    write_wav(path, channels=6)
    calls = []
    monkeypatch.setattr(inspection, "probe_media", lambda *a, **kw: calls.append(a[0]) or MediaMetadata(Fraction(0), "container", ()))
    inspection.inspect_file(path)
    assert calls == [path.resolve()]


def test_empty_wav_is_refused(tmp_path):
    path = tmp_path / "empty.wav"
    write_wav(path, frames=0)
    with pytest.raises(ValueError, match="no audio samples"):
        inspection.inspect_file(path)


@pytest.mark.parametrize("extension,codec", [
    ("mp3", "libmp3lame"),
    ("m4a", "aac"),
    ("aac", "aac"),
    ("flac", "flac"),
    ("ogg", "libvorbis"),
    ("opus", "libopus"),
    ("mp4", "aac"),
    ("mov", "aac"),
    ("webm", "libopus"),
    ("mkv", "flac"),
])
def test_opt_in_verified_tools_inspect_common_formats(
        tmp_path, monkeypatch, extension, codec):
    ffmpeg = os.environ.get("UTTERLEAF_TEST_FFMPEG")
    ffprobe = os.environ.get("UTTERLEAF_TEST_FFPROBE")
    if not ffmpeg or not ffprobe:
        pytest.skip("Explicitly verified FFmpeg and FFprobe test tools are required")

    decoder_record = tmp_path / "file-decoder.json"
    probe_record = tmp_path / "file-probe.json"
    monkeypatch.setattr(decoder, "_settings_path", lambda: decoder_record)
    monkeypatch.setattr(probe, "_settings_path", lambda: probe_record)
    selected_ffmpeg = decoder.select_decoder(Path(ffmpeg))
    probe.select_probe(Path(ffprobe))
    assert decoder_record.parent == tmp_path and probe_record.parent == tmp_path

    media = tmp_path / f"quarter-second.{extension}"
    environment = os.environ.copy()
    environment.pop("FFREPORT", None)
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0
    subprocess.run(
        [
            str(selected_ffmpeg),
            "-nostdin",
            "-hide_banner",
            "-loglevel", "error",
            "-f", "lavfi",
            "-i", "sine=frequency=440:sample_rate=48000:duration=0.25",
            "-c:a", codec,
            str(media),
        ],
        check=True,
        timeout=20,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        shell=False,
        cwd=selected_ffmpeg.parent,
        env=environment,
        creationflags=flags,
    )

    result = inspection.inspect_file(media)
    track, = result.metadata.tracks
    assert (track.ordinal, track.stream_index) == (0, 0)
    assert (track.sample_rate, track.channels) == (48_000, 1)
    assert result.signature == inspection.current_file_signature(media)
    if extension == "aac":
        assert result.metadata.origin is None
        assert result.metadata.origin_kind == "unavailable"
