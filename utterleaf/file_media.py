"""Presentation-aware development decoder; never discovers external executables.

This adapter is separate from the legacy relative-time file API. Its source
iterator is context-owned, and audio stays bounded even for very long gaps.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import closing, contextmanager
from dataclasses import dataclass, field
from fractions import Fraction
import os
from pathlib import Path
import stat

import numpy as np

from utterleaf.file_timeline import MAX_INPUT_SAMPLES, SAMPLE_RATE, TimelineAudioBlock
from utterleaf.local_filesystem import require_local_filesystem
from utterleaf.transcript import TranscriptionCancelled

MAX_FRAME_BYTES = 64 * 1024 * 1024
MAX_TIMESTAMP_TICK = Fraction(1, 1000)


def _check_cancel(cancel):
    if cancel is not None and cancel.is_set():
        raise TranscriptionCancelled("File transcription cancelled")


def _presentation_time(pts, time_base) -> Fraction:
    if (type(pts) is not int or not -(2**63) < pts < 2**63
            or type(time_base) is not Fraction or time_base <= 0
            or time_base.numerator >= 2**63 or time_base.denominator >= 2**63):
        raise ValueError("The media has missing or invalid presentation timestamps")
    return pts * time_base


@dataclass(frozen=True)
class AudioTrack:
    ordinal: int
    stream_index: int
    codec: str
    channels: int
    sample_rate: int
    start: Fraction | None


@dataclass(frozen=True)
class TimedMedia:
    origin: Fraction
    origin_kind: str
    tracks: tuple[AudioTrack, ...]
    blocks: Iterator[TimelineAudioBlock] = field(repr=False, compare=False)


def _media_clock(container) -> tuple[Fraction, str]:
    # Container start_time uses microseconds; stream start_time uses its own
    # rational time base. The fallback includes all A/V streams so selecting a
    # different audio track cannot independently zero that track.
    if container.start_time is not None:
        return _presentation_time(container.start_time, Fraction(1, 1_000_000)), "container"
    starts = []
    for stream in container.streams:
        if stream.type in {"audio", "video"}:
            starts.append(_presentation_time(stream.start_time, stream.time_base))
    if not starts:
        raise ValueError("The file has no shared presentation clock")
    return min(starts), "all-stream-starts"


def resample_timed_frames(frames, *, origin: Fraction, cancel=None, progress=None):
    """Keep a run's first source PTS and advance by exact output sample counts.

    Input rounding smaller than one timestamp tick (at most 1 ms) is treated as clock
    quantization, measured against the run's sample clock, never cumulatively.
    Larger forward jumps flush/reset the resampler; backward jumps fail. Missing
    timestamps, coarser clocks, format changes and audio before the common origin
    are unsupported rather than silently trimmed or re-timed. The caller owns
    ``frames``. PyAV's decoder handles codec skip/priming before these frames.
    """
    import av

    if type(origin) is not Fraction:
        raise TypeError("Media origin must be a Fraction")
    resampler = None
    run_start = Fraction(0)
    input_duration = Fraction(0)
    output_samples = 0
    previous_tick = Fraction(0)
    signature = None
    output_end = None
    emitted = False

    def output(frame):
        nonlocal output_samples, output_end, emitted
        _check_cancel(cancel)
        if (frame.sample_rate != SAMPLE_RATE or frame.format.name != "s16"
                or frame.layout.name != "mono" or not 0 < frame.samples <= MAX_INPUT_SAMPLES):
            raise ValueError("The decoder returned invalid or oversized audio")
        array = frame.to_ndarray()
        if array.dtype != np.dtype("int16") or array.size != frame.samples:
            raise ValueError("The decoder returned invalid audio samples")
        start = run_start + Fraction(output_samples, SAMPLE_RATE)
        output_samples += frame.samples
        output_end = run_start + Fraction(output_samples, SAMPLE_RATE)
        # Capture the size before handing writable audio to the consumer.
        emitted = True
        return TimelineAudioBlock(start, array.reshape(-1).astype(np.float32) / 32768.0)

    def flush():
        for decoded in resampler.resample(None):
            yield output(decoded)
        # libswresample rounds fractional target samples. More than one target
        # sample's difference would conceal loss, insertion or failed flushing.
        if abs(Fraction(output_samples, SAMPLE_RATE) - input_duration) > Fraction(1, SAMPLE_RATE):
            raise ValueError("The resampler did not preserve the audio run duration")

    for frame in frames:
        _check_cancel(cancel)
        start = _presentation_time(frame.pts, frame.time_base)
        tick = frame.time_base
        if tick > MAX_TIMESTAMP_TICK:
            raise ValueError("The audio presentation clock is too coarse for aligned transcription")
        if start < origin:
            raise ValueError("Audio starts before the shared file origin; pre-roll timing is unsupported")
        rate, count = frame.sample_rate, frame.samples
        if (type(rate) is not int or not 1 <= rate <= 384_000
                or type(count) is not int or not 1 <= count <= 60 * rate
                or not 1 <= len(frame.layout.channels) <= 32
                or sum(plane.buffer_size for plane in frame.planes) > MAX_FRAME_BYTES):
            raise ValueError("The decoder returned invalid or oversized audio")
        current_signature = (rate, frame.format.name, frame.layout.name, tick)
        if signature is not None and current_signature != signature:
            raise ValueError("Changing audio formats or timestamp units within one track are unsupported")
        signature = current_signature
        if resampler is not None:
            delta = start - (run_start + input_duration)
            tolerance = max(previous_tick, tick)
            if delta <= -tolerance:
                raise ValueError("Audio presentation timestamps overlap or move backward")
            if delta >= tolerance:
                # Flush before admitting the new frame: buffered old samples
                # must not inherit the later frame's timestamp across a gap.
                yield from flush()
                resampler = None
        if resampler is None:
            if output_end is not None and start < output_end:
                raise ValueError("The timestamp gap is too small to preserve after resampling")
            run_start, input_duration, output_samples = start, Fraction(0), 0
            resampler = av.AudioResampler(format="s16", layout="mono", rate=SAMPLE_RATE)
        input_duration += Fraction(count, rate)
        previous_tick = tick
        # Retain frame.pts/time_base. Only our exact run clock is used to label
        # output; PyAV's integer output PTS can round the initial source offset.
        for decoded in resampler.resample(frame):
            yield output(decoded)
        if progress is not None:
            progress("decoding", None)
    if resampler is not None:
        yield from flush()
    _check_cancel(cancel)
    if not emitted:
        raise ValueError("The selected file contains no decodable audio")


def _file_identity(info):
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns


@contextmanager
def open_pyav_timeline(path: str | Path, *, audio_track: int = 0, cancel=None, progress=None):
    """Open an explicitly selected local file with one common clock and cleanup.

    Metadata fallback requires starts for every A/V stream. A file with unknown
    timing fails explicitly; this API never advertises inferred zero-based time.
    No external executable, source path or decoder diagnostic is logged.
    """
    from utterleaf.file_decoder import DecoderSetupError
    try:
        import av
    except ImportError:
        av = None
    if av is None or av.__dict__.get("UTTERLEAF_MEDIA_STUB", False):
        raise DecoderSetupError("The development timeline decoder is unavailable")
    if type(audio_track) is not int or not 0 <= audio_track <= 255:
        raise ValueError("Choose an audio track from 1 to 256")
    _check_cancel(cancel)
    path = require_local_filesystem(Path(path))

    def deny_external(*args, **kwargs):
        raise ValueError("Media referencing external files or network sources is unsupported")

    with path.open("rb") as source:
        info = os.fstat(source.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size <= 0:
            raise ValueError("Select a nonempty regular local file")
        original = _file_identity(info)
        # On Windows fstat and path.stat can expose different creation/change
        # time values as ctime. Compare each API with its own baseline; device,
        # inode, size and mtime still establish that both initially name one file.
        original_path = _file_identity(path.stat())
        if original[:4] != original_path[:4]:
            raise RuntimeError("The selected media file changed during transcription")

        def unchanged():
            _check_cancel(cancel)
            try:
                same = (_file_identity(os.fstat(source.fileno())) == original
                        and _file_identity(path.stat()) == original_path)
            except OSError:
                same = False
            if not same:
                raise RuntimeError("The selected media file changed during transcription")

        try:
            with av.open(source, mode="r", io_open=deny_external,
                         options={"protocol_whitelist": ""}) as container:
                if len(container.streams) > 256:
                    raise ValueError("The file contains too many streams")
                if audio_track >= len(container.streams.audio):
                    raise ValueError("The selected audio track does not exist in this file")
                origin, kind = _media_clock(container)
                tracks = tuple(AudioTrack(
                    index, stream.index, stream.codec_context.name,
                    stream.codec_context.channels, stream.codec_context.sample_rate,
                    None if stream.start_time is None else _presentation_time(stream.start_time, stream.time_base),
                ) for index, stream in enumerate(container.streams.audio))

                def frames():
                    for frame in container.decode(audio=audio_track):
                        unchanged()
                        yield frame
                    unchanged()

                with closing(frames()) as decoded, closing(resample_timed_frames(
                        decoded, origin=origin, cancel=cancel, progress=progress)) as blocks:
                    yield TimedMedia(origin, kind, tracks, blocks)
                    unchanged()
        except av.error.FFmpegError:
            raise RuntimeError("Cannot decode this media file; it may be damaged or unsupported") from None
