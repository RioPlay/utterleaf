"""Opt-in integration checks for the explicitly selected FFmpeg pair."""

from __future__ import annotations

from fractions import Fraction
import os
from pathlib import Path
import subprocess
import threading
import wave

import numpy as np
import pytest

av = pytest.importorskip("av")
from utterleaf import file_external
from utterleaf.config import Config
from utterleaf.file_external import open_ffmpeg_timeline
from utterleaf.file_transcription import transcribe_file
from utterleaf.transcribe import CTranslateEngine
from utterleaf.transcript import (
    Segment, Transcript, TranscriptionCancelled, export_transcript,
)


FFMPEG = os.environ.get("UTTERLEAF_TEST_FFMPEG")
FFPROBE = os.environ.get("UTTERLEAF_TEST_FFPROBE")
if not FFMPEG or not FFPROBE:
    pytest.skip("set UTTERLEAF_TEST_FFMPEG and UTTERLEAF_TEST_FFPROBE for external integration", allow_module_level=True)


def pcm(path: Path, rate: int, samples: int, *, value: int = 1000) -> None:
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(rate)
        output.writeframes((np.full(samples, value, dtype="<i2")).tobytes())


def audio_frame(rate, pts, *, samples, value=1000):
    result = av.AudioFrame.from_ndarray(
        np.full((1, samples), value, dtype=np.int16), format="s16", layout="mono"
    )
    result.sample_rate = rate
    result.time_base = Fraction(1, rate)
    result.pts = pts
    return result


def run_ffmpeg(arguments):
    environment = os.environ.copy()
    environment.pop("FFREPORT", None)
    subprocess.run(
        [FFMPEG, "-nostdin", *arguments],
        check=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        shell=False,
        timeout=20,
        cwd=Path(FFMPEG).parent,
        env=environment,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )


def install_tools(monkeypatch, tmp_path):
    from utterleaf import file_decoder, file_probe
    monkeypatch.setattr(file_decoder, "_settings_path", lambda: tmp_path / "file-decoder.json")
    monkeypatch.setattr(file_probe, "_settings_path", lambda: tmp_path / "file-probe.json")
    file_decoder.select_decoder(FFMPEG)
    file_probe.select_probe(FFPROBE)


def blocks_for(path, monkeypatch, tmp_path, *, audio_track=0, cancel=None):
    install_tools(monkeypatch, tmp_path)
    with open_ffmpeg_timeline(path, audio_track=audio_track, cancel=cancel) as media:
        return list(media.blocks)


def matroska(source: Path, target: Path) -> None:
    run_ffmpeg(["-y", "-i", str(source), "-c:a", "copy", str(target)])


def timed_pcm_tracks(path: Path) -> None:
    rate = 48_000
    with av.open(str(path), "w", format="matroska") as output:
        tracks = [output.add_stream("pcm_s16le", rate=rate) for _ in range(2)]
        for track in tracks:
            track.layout = "mono"
        authored = (
            (tracks[0], audio_frame(rate, rate, samples=4800, value=700)),
            (tracks[0], audio_frame(rate, rate + 4800, samples=4800, value=700)),
            (tracks[1], audio_frame(rate, rate + 9600, samples=4800, value=1400)),
            (tracks[1], audio_frame(rate, rate + 19200, samples=4800, value=1400)),
        )
        for track, frame in authored:
            for packet in track.encode(frame):
                output.mux(packet)
        for track in tracks:
            for packet in track.encode():
                output.mux(packet)


def aac_with_priming(path: Path) -> tuple[Fraction, Fraction]:
    rate = 48_000
    with av.open(str(path), "w", format="mp4") as output:
        track = output.add_stream("aac", rate=rate)
        track.layout = "mono"
        for position in range(0, rate // 2, 1024):
            current = audio_frame(
                rate,
                position,
                samples=min(1024, rate // 2 - position),
                value=8000,
            )
            for packet in track.encode(current):
                output.mux(packet)
        for packet in track.encode():
            output.mux(packet)
    with av.open(str(path)) as container:
        first_packet = next(packet for packet in container.demux(audio=0) if packet.size)
        assert first_packet.pts < 0
        assert container.start_time == 0
    with av.open(str(path)) as container:
        track = container.streams.audio[0]
        presentation_duration = Fraction(track.duration) * track.time_base
        decoded = list(container.decode(audio=0))
    assert decoded[0].pts == 0
    assert np.any(decoded[0].to_ndarray())
    decoded_duration = sum(Fraction(item.samples, item.sample_rate) for item in decoded)
    assert decoded_duration >= presentation_duration
    return presentation_duration, decoded_duration


def muxer_dropped_negative_timestamps(path: Path) -> None:
    wav = path.with_suffix(".wav")
    pcm(wav, 48_000, 4800)
    run_ffmpeg([
        "-y", "-itsoffset", "-1", "-i", str(wav), "-c:a", "copy",
        "-avoid_negative_ts", "disabled", str(path),
    ])


def single_frame_flac(path: Path) -> None:
    rate = 48_000
    with av.open(str(path), "w", format="matroska") as output:
        track = output.add_stream("flac", rate=rate)
        track.layout = "mono"
        for packet in track.encode(audio_frame(rate, 0, samples=1024)):
            output.mux(packet)
        for packet in track.encode():
            output.mux(packet)


def test_real_pcm_frame_journal_and_decode_preserve_count(tmp_path, monkeypatch):
    wav, source = tmp_path / "short.wav", tmp_path / "short.mkv"
    pcm(wav, 16000, 1600)
    matroska(wav, source)
    blocks = blocks_for(source, monkeypatch, tmp_path)
    assert sum(block.samples.size for block in blocks) == 1600
    assert blocks[0].start == 0
    assert np.allclose(np.concatenate([block.samples for block in blocks]), 1000 / 32768)


@pytest.mark.parametrize("rate,samples,expected", [(44100, 4410, 1600), (48000, 4800, 1600)])
def test_resampling_preserves_known_duration(tmp_path, monkeypatch, rate, samples, expected):
    wav, source = tmp_path / f"{rate}.wav", tmp_path / f"{rate}.mkv"
    pcm(wav, rate, samples)
    matroska(wav, source)
    blocks = blocks_for(source, monkeypatch, tmp_path)
    assert abs(sum(block.samples.size for block in blocks) - expected) <= 1


def test_real_mkv_common_origin_late_track_and_internal_gap_are_retained(tmp_path, monkeypatch):
    movie = tmp_path / "tracks.mkv"
    timed_pcm_tracks(movie)
    install_tools(monkeypatch, tmp_path)

    results = []
    for selected in (0, 1):
        with open_ffmpeg_timeline(movie, audio_track=selected) as media:
            assert media.origin == 1 and media.origin_kind == "container"
            assert [track.start for track in media.tracks] == [Fraction(1), Fraction(6, 5)]
            blocks = list(media.blocks)
        results.append(blocks)

    first, second = results
    assert first[0].start == 1
    assert sum(block.samples.size for block in first) == 3200
    assert second[0].start == Fraction(6, 5)
    assert sum(block.samples.size for block in second) == 3200
    runs = []
    prior_end = None
    for block in second:
        if block.start != prior_end:
            runs.append([block.start, None])
        prior_end = block.start + Fraction(block.samples.size, 16000)
        runs[-1][1] = prior_end
    assert runs == [[Fraction(6, 5), Fraction(13, 10)], [Fraction(7, 5), Fraction(3, 2)]]
    assert runs[1][0] - runs[0][1] == Fraction(1, 10)


def test_recording_transcription_and_exports_keep_real_track_timeline(tmp_path, monkeypatch):
    movie = tmp_path / "transcribed-tracks.mkv"
    timed_pcm_tracks(movie)
    install_tools(monkeypatch, tmp_path)
    network_flags = []

    class KnownSegments(CTranslateEngine):
        def __init__(self):
            super().__init__(None)
            self.calls = 0

        def transcribe_segments(self, audio, cfg, **kwargs):
            network_flags.append(cfg.allow_network)
            self.calls += 1
            assert audio.dtype == np.float32 and 0 < audio.size <= 30 * 16000
            return Transcript((Segment(0, 0.05, f"batch {self.calls}"),), "en")

    def recognize(track, timing):
        engine = KnownSegments()
        monkeypatch.setattr("utterleaf.transcribe.load_model", lambda cfg: engine)
        return transcribe_file(
            movie, Config(allow_network=True), audio_track=track, timing=timing
        )

    first = recognize(0, "recording")
    second = recognize(1, "recording")
    relative = recognize(1, "relative")

    assert [segment.start for segment in first.segments] == [0]
    assert [segment.start for segment in second.segments] == pytest.approx([0.2, 0.4])
    assert [segment.start for segment in relative.segments] == [0]
    assert [segment.text for segment in second.segments] == ["batch 1", "batch 2"]
    assert network_flags == [False, False, False, False]

    srt = export_transcript(second, tmp_path / "recording.srt")
    vtt = export_transcript(second, tmp_path / "recording.vtt")
    assert "00:00:00,200 --> 00:00:00,250" in srt.read_text(encoding="utf-8")
    assert "00:00:00,400 --> 00:00:00,450" in srt.read_text(encoding="utf-8")
    assert "00:00:00.200 --> 00:00:00.250" in vtt.read_text(encoding="utf-8")
    assert "00:00:00.400 --> 00:00:00.450" in vtt.read_text(encoding="utf-8")


def test_grouped_recording_job_exports_aligned_sibling_tracks(tmp_path, monkeypatch):
    from utterleaf.file_tracks import export_transcripts, transcribe_tracks

    movie = tmp_path / "grouped-tracks.mkv"
    timed_pcm_tracks(movie)
    install_tools(monkeypatch, tmp_path)
    network_flags = []

    class KnownSegments(CTranslateEngine):
        def __init__(self):
            super().__init__(None)
            self.calls = 0

        def transcribe_segments(self, audio, cfg, **kwargs):
            network_flags.append(cfg.allow_network)
            self.calls += 1
            assert audio.dtype == np.float32 and 0 < audio.size <= 30 * 16000
            return Transcript((Segment(0, 0.05, f"batch {self.calls}"),), "en")

    monkeypatch.setattr("utterleaf.transcribe.load_model", lambda cfg: KnownSegments())
    result = transcribe_tracks(
        movie, Config(allow_network=True), audio_tracks=(1, 2), timing="recording"
    )
    written = export_transcripts(result, tmp_path / "show.vtt")
    assert result.origin == 1 and result.origin_kind == "container"
    assert [item.track.ordinal for item in result.tracks] == [0, 1]
    assert [segment.start for segment in result.tracks[0].transcript.segments] == [0]
    assert [segment.start for segment in result.tracks[1].transcript.segments] == pytest.approx([0.2, 0.4])
    assert "00:00:00.000 --> 00:00:00.050" in written[0].read_text(encoding="utf-8")
    assert "00:00:00.200 --> 00:00:00.250" in written[1].read_text(encoding="utf-8")
    assert "00:00:00.400 --> 00:00:00.450" in written[1].read_text(encoding="utf-8")
    assert network_flags and all(flag is False for flag in network_flags)


def test_real_dropped_negative_timestamps_stay_unavailable_instead_of_zero(tmp_path, monkeypatch):
    from utterleaf.file_inspection import inspect_file
    from utterleaf.file_transcription import transcribe_file

    source = tmp_path / "dropped-negative.mkv"
    muxer_dropped_negative_timestamps(source)
    install_tools(monkeypatch, tmp_path)
    inspected = inspect_file(source)
    assert inspected.metadata.origin is None
    assert inspected.metadata.origin_kind == "unavailable"
    assert inspected.metadata.tracks[0].start is None
    with pytest.raises(ValueError, match="missing or invalid A/V stream timing"):
        with open_ffmpeg_timeline(source) as media:
            list(media.blocks)
    with pytest.raises(ValueError, match="missing or invalid A/V stream timing"):
        transcribe_file(source, Config(allow_network=True), timing="recording")


def test_real_aac_priming_uses_first_decoded_pts_and_duration(tmp_path, monkeypatch):
    source = tmp_path / "priming.m4a"
    presentation_duration, decoded_duration = aac_with_priming(source)
    install_tools(monkeypatch, tmp_path)
    with open_ffmpeg_timeline(source) as media:
        assert media.origin == 0 and media.tracks[0].start == 0
        blocks = list(media.blocks)
    assert blocks[0].start == 0
    actual_duration = Fraction(sum(block.samples.size for block in blocks), 16000)
    assert abs(actual_duration - presentation_duration) <= Fraction(1, 16000)
    # PyAV exposes final AAC padding in its decoded frames. The independently
    # reported presentation duration proves the external path trims that tail.
    assert decoded_duration > actual_duration


def test_real_single_frame_flac_has_actionable_unsupported_reason(tmp_path, monkeypatch):
    source = tmp_path / "single-frame.mkv"
    single_frame_flac(source)
    install_tools(monkeypatch, tmp_path)
    with pytest.raises(ValueError, match="compressed audio run is too short"):
        with open_ffmpeg_timeline(source) as media:
            list(media.blocks)


def test_cancelled_and_early_closed_iterators_release_external_work(tmp_path, monkeypatch):
    wav, source = tmp_path / "cancel.wav", tmp_path / "cancel.mkv"
    pcm(wav, 16000, 160000)
    matroska(wav, source)
    cancel = threading.Event()
    install_tools(monkeypatch, tmp_path)
    prior_threads = {
        thread for thread in threading.enumerate()
        if thread.name.startswith("utterleaf-media-")
    }
    with pytest.raises(TranscriptionCancelled):
        with open_ffmpeg_timeline(source, cancel=cancel) as media:
            iterator = iter(media.blocks)
            next(iterator)
            cancel.set()
            next(iterator)
    assert not {
        thread for thread in threading.enumerate()
        if thread.name.startswith("utterleaf-media-") and thread not in prior_threads
    }
    source.rename(tmp_path / "cancel-released.mkv")

    early_wav, early_source = tmp_path / "early.wav", tmp_path / "early.mkv"
    pcm(early_wav, 16000, 160000)
    matroska(early_wav, early_source)
    install_tools(monkeypatch, tmp_path)
    context = open_ffmpeg_timeline(early_source)
    media = context.__enter__()
    iterator = iter(media.blocks)
    next(iterator)
    context.__exit__(None, None, None)
    assert not {
        thread for thread in threading.enumerate()
        if thread.name.startswith("utterleaf-media-") and thread not in prior_threads
    }
    early_source.rename(tmp_path / "early-released.mkv")
