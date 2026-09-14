import io
import json
from fractions import Fraction
from pathlib import Path
import threading
import sys
from types import SimpleNamespace

import numpy as np
import pytest

from utterleaf import file_external as external
from utterleaf.file_frame_journal import FrameTimingJournal, FileFrameJournalError
from utterleaf.file_frame_metadata import DecodedAudioFrame
from utterleaf.file_metadata import MediaAudioTrack
from utterleaf.transcript import TranscriptionCancelled


def track(*, rate=16000, codec="pcm_s16le"):
    return MediaAudioTrack(0, 2, codec, rate, 1, "mono", None, None,
                          True, Fraction(0), Fraction(1, rate))


def journal(frames, *, selected=None, storage=None):
    selected = selected or track()
    storage = storage or io.BytesIO()
    result = FrameTimingJournal(sample_rate=selected.sample_rate,
                                time_base=selected.time_base, origin=Fraction(0),
                                stream_index=2, journal_factory=lambda: storage)
    for pts, count in frames:
        result.append(DecodedAudioFrame(2, pts, "s16", count, 1, "mono"))
    result.seal()
    return result


def raw_runs(data, timing, selected=None):
    return external._RawRuns(iter(data), timing.entries(), selected or track(),
                             None, threading.Event())


def test_run_partition_keeps_every_byte_and_large_gap_without_silence():
    with journal([(1600, 3), (1603, 2), (1600000, 2)]) as timing:
        runs = raw_runs([b"abc", b"defghijk", b"lmn"], timing)
        assert b"".join(runs.run_input()) == b"abcdefghij"
        assert runs.run_samples == 5 and runs.entry.pts == 1600000
        assert b"".join(runs.run_input()) == b"klmn"
        assert runs.finished and runs.run_samples == 2 and runs.entry is None


@pytest.mark.parametrize("data, error", [
    ([b"123"], "ended before"), ([b"12345"], "exceeds"),
    ([b"1234", b"5"], "exceeds"), ([b"x" * 65537], "invalid audio"),
])
def test_raw_length_mismatch_never_completes(data, error):
    with journal([(0, 2)]) as timing:
        runs = raw_runs(data, timing)
        with pytest.raises(ValueError, match=error):
            list(runs.run_input())
        assert not runs.finished and not runs.run_finished


def test_original_decoder_failure_after_exact_byte_count_is_not_success():
    def source():
        yield b"1234"
        raise RuntimeError("synthetic decoder failure")
    with journal([(0, 2)]) as timing:
        runs = raw_runs(source(), timing)
        with pytest.raises(RuntimeError, match="synthetic decoder failure"):
            list(runs.run_input())
        assert not runs.finished


def test_compressed_single_frame_run_is_explicitly_unsupported():
    selected = track(codec="aac")
    with journal([(0, 2)], selected=selected) as timing:
        runs = raw_runs([b"1234"], timing, selected)
        with pytest.raises(ValueError, match="too short"):
            list(runs.run_input())
        assert not runs.finished


def test_compressed_contiguous_progress_is_supported_but_each_gap_needs_evidence():
    selected = track(codec="aac")
    with journal([(0, 2), (2, 2), (100, 2)], selected=selected) as timing:
        runs = raw_runs([b"123456789012"], timing, selected)
        assert b"".join(runs.run_input()) == b"12345678"
        with pytest.raises(ValueError, match="too short"):
            list(runs.run_input())


def test_journal_digest_failure_discards_otherwise_valid_pcm():
    import struct
    storage = io.BytesIO()
    with journal([(0, 2)], storage=storage) as timing:
        storage.seek(0)
        storage.write(struct.pack("!q", 1600))  # Same-size valid later timestamp.
        runs = raw_runs([b"1234"], timing)
        with pytest.raises(FileFrameJournalError):
            list(runs.run_input())
        assert not runs.finished


def test_large_frame_is_streamed_with_only_chunk_sized_lookahead():
    block = b"x" * 65536
    with journal([(0, 960000)]) as timing:
        blocks, remainder = divmod(1920000, len(block))
        runs = raw_runs([block] * blocks + [block[:remainder]], timing)
        sizes = []
        for chunk in runs.run_input():
            sizes.append(len(chunk))
            assert len(runs.pending) <= 65536
        assert sum(sizes) == 1920000 and max(sizes) <= 65536


@pytest.mark.parametrize("chunks", [
    [b"a\nb\n"], [b"a", b"\nb", b"\n"], [b"a\n", b"b\n"],
])
def test_frame_rows_tolerate_transport_boundaries(chunks):
    assert list(external._frame_lines(chunks)) == [b"a\n", b"b\n"]


@pytest.mark.parametrize("chunks", [[b"a" * 512, b"\n"], [b"a" * 513], [b"a" * 65537]])
def test_frame_rows_reject_oversized_line_or_transport(chunks):
    with pytest.raises(ValueError):
        list(external._frame_lines(chunks))


def stub_media(monkeypatch, raw, resampled=None):
    checks = []
    source = SimpleNamespace(path=Path("synthetic.mkv"), check=lambda: checks.append("source"))
    pair = SimpleNamespace(decoder=SimpleNamespace(path=Path("ffmpeg")),
                           check=lambda: checks.append("tools"))
    events = []
    def transport(_path, args, *, check_identity, **kwargs):
        check_identity()
        try:
            if "-copyts" in args:
                yield from raw
            else:
                data = b"".join(kwargs["input_chunks"])
                yield from resampled(data)
        finally:
            events.append("closed")
    monkeypatch.setattr(external, "iter_tool_output", transport)
    return source, pair, checks, events


def test_timed_output_handles_odd_chunks_and_consumer_resize(monkeypatch):
    pcm = np.arange(12, dtype="<i2").tobytes()
    source, pair, checks, events = stub_media(monkeypatch, [pcm[:3], pcm[3:10], pcm[10:]])
    with journal([(1600, 5), (3200, 7)]) as timing:
        blocks = external._external_blocks(source, pair, track(), timing, None, threading.Event(), None)
        first = next(blocks)
        assert first.start == Fraction(1, 10) and first.samples.size == 1
        first.samples.resize(0, refcheck=False)
        remaining = list(blocks)
        assert remaining[0].start == Fraction(1601, 16000)
        assert remaining[-1].start == Fraction(1, 5)
        np.testing.assert_array_equal(np.concatenate([b.samples for b in remaining]) * 32768,
                                      np.arange(1, 12))
    assert checks == ["source", "tools", "source", "tools"] and events == ["closed"]


@pytest.mark.parametrize("output_samples", [0, 10, 1603])
def test_resampler_missing_or_excess_audio_cannot_complete(monkeypatch, output_samples):
    selected = track(rate=48000)
    source, pair, _, _ = stub_media(monkeypatch, [b"x" * 9600],
                                    lambda data: [b"\0" * (output_samples * 2)])
    with journal([(0, 4800)], selected=selected) as timing:
        with pytest.raises(ValueError, match="complete samples|preserve.*duration"):
            list(external._external_blocks(source, pair, selected, timing, None,
                                           threading.Event(), None))


def test_each_run_flushes_resampler_before_next_run(monkeypatch):
    selected = track(rate=48000)
    inputs = []
    def resample(data):
        inputs.append(data)
        return [data[:3200]]
    source, pair, _, _ = stub_media(monkeypatch, [b"a" * 9600 + b"b" * 9600], resample)
    with journal([(0, 4800), (9600, 4800)], selected=selected) as timing:
        result = list(external._external_blocks(source, pair, selected, timing, None,
                                                threading.Event(), None))
    assert inputs == [b"a" * 9600, b"b" * 9600]
    assert [item.start for item in result] == [Fraction(0), Fraction(1, 5)]


def test_cancel_after_first_yield_closes_original_decoder(monkeypatch):
    source, pair, _, events = stub_media(monkeypatch, [b"x" * 20, b"y" * 20])
    cancel = threading.Event()
    with journal([(0, 20)]) as timing:
        blocks = external._external_blocks(source, pair, track(), timing, cancel,
                                           threading.Event(), None)
        next(blocks)
        cancel.set()
        with pytest.raises(TranscriptionCancelled):
            next(blocks)
    assert events == ["closed"]


def test_held_source_detects_mutation_and_releases_file(tmp_path):
    path = tmp_path / "source.wav"
    path.write_bytes(b"original")
    with external._HeldSource(path) as source:
        source.check()
        path.write_bytes(b"changed-size")
        with pytest.raises(ValueError, match="changed"):
            source.check()
    assert source.file.closed
    path.rename(tmp_path / "renamed.wav")


def test_cancel_and_invalid_track_never_launch_or_read_source(monkeypatch):
    monkeypatch.setattr(external, "_HeldSource", lambda path: pytest.fail("must not open"))
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(TranscriptionCancelled):
        with external.open_ffmpeg_timeline("anything.wav", cancel=cancel):
            pass
    for invalid in (True, -1, 256, "0"):
        with pytest.raises(ValueError, match="valid audio track"):
            with external.open_ffmpeg_timeline("anything.wav", audio_track=invalid):
                pass


@pytest.mark.parametrize("codec,raw,error", [
    ("aac", b"1234", "compressed audio run is too short"),
    ("pcm_s16le", b"12", "ended before"),
    ("pcm_s16le", b"123456", "exceeds"),
])
def test_real_stdin_worker_preserves_safe_local_failure(monkeypatch, codec, raw, error):
    from utterleaf.media_process import iter_tool_output as real_transport
    selected = track(rate=48000, codec=codec)
    source = SimpleNamespace(path=Path("synthetic.mkv"), check=lambda: None)
    pair = SimpleNamespace(decoder=SimpleNamespace(path=Path("ffmpeg")), check=lambda: None)
    baseline = {t.ident for t in threading.enumerate() if t.name.startswith("utterleaf-media-")}
    def transport(_path, args, *, check_identity, **kwargs):
        if "-copyts" in args:
            check_identity()
            yield raw
        else:
            yield from real_transport(Path(sys.executable), ["-c",
                "import sys; data=sys.stdin.buffer.read(); sys.stdout.buffer.write(data)"],
                check_identity=check_identity, **kwargs)
    monkeypatch.setattr(external, "iter_tool_output", transport)
    with journal([(0, 2)], selected=selected) as timing:
        with pytest.raises(ValueError, match=error):
            list(external._external_blocks(source, pair, selected, timing, None,
                                           threading.Event(), None))
    assert {t.ident for t in threading.enumerate() if t.name.startswith("utterleaf-media-")} == baseline


def test_late_identity_failure_discards_context_result_and_closes_journal(tmp_path, monkeypatch):
    path = tmp_path / "source.wav"
    path.write_bytes(b"synthetic media")
    state = {"changed": False}
    def check():
        if state["changed"]:
            raise external.DecoderSetupError("A selected media tool changed")
    pair = SimpleNamespace(decoder=SimpleNamespace(path=Path("ffmpeg")),
                           probe=SimpleNamespace(path=Path("ffprobe")), check=check)
    monkeypatch.setattr(external, "_verified_pair", lambda *args: pair)
    payload = json.dumps({"format": {"start_time": "0"}, "streams": [{
        "index": 2, "codec_type": "audio", "codec_name": "pcm_s16le", "sample_rate": "16000",
        "channels": 1, "channel_layout": "mono", "time_base": "1/16000", "start_pts": 0,
    }]}).encode()
    def collect(_path, _args, *, check_identity, **kwargs):
        check_identity()
        return payload
    def output(_path, args, *, check_identity, **kwargs):
        check_identity()
        if "-show_frames" in args:
            yield b"stream_index=2|pts=0|sample_fmt=s16|nb_samples=2|channels=1|channel_layout=mono\n"
        else:
            yield b"1234"
    monkeypatch.setattr(external, "collect_tool_output", collect)
    monkeypatch.setattr(external, "iter_tool_output", output)
    journals = []
    def create(**kwargs):
        value = FrameTimingJournal(**kwargs)
        journals.append(value)
        return value
    monkeypatch.setattr(external, "FrameTimingJournal", create)
    with pytest.raises(external.DecoderSetupError, match="tool changed"):
        with external.open_ffmpeg_timeline(path) as media:
            assert media.origin == 0 and media.tracks[0].stream_index == 2
            assert next(media.blocks).samples.size == 2
            state["changed"] = True
            list(media.blocks)
    assert journals[0]._state == "closed"
    path.rename(tmp_path / "released.wav")
