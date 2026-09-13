"""Explicit, bounded local media transcription; never saves audio or downloads models."""

from __future__ import annotations

from dataclasses import replace
from contextlib import closing
import io
from pathlib import Path
import stat
import wave

import numpy as np

from utterleaf.config import Config
from utterleaf.local_filesystem import require_local_filesystem
from utterleaf.transcript import Segment, Transcript, TranscriptionCancelled

# Legacy array-returning API bounds; streaming file transcription does not use them.
MAX_FILE_BYTES = 256 * 1024 * 1024
MAX_AUDIO_SECONDS = 600
SAMPLE_RATE = 16000


class WavFormatUnsupported(RuntimeError):
    """A WAV variant needs an optional decoder, rather than the PCM reader."""


def _check_cancel(cancel):
    if cancel is not None and cancel.is_set():
        raise TranscriptionCancelled("File transcription cancelled")


def _decode_pcm_wav(path, *, cancel=None, progress=None):
    """Compatibility reader for callers that request the original bounded array."""
    return np.concatenate(list(_iter_pcm_wav(path, cancel=cancel, progress=progress,
                                           max_bytes=MAX_FILE_BYTES, max_seconds=MAX_AUDIO_SECONDS)))


def _iter_pcm_wav(path, *, cancel=None, progress=None, max_bytes=None, max_seconds=None):
    """Small packaged decoder: integer PCM WAV, mono/stereo, 8–48 kHz."""
    import os
    from utterleaf.audio import resample_audio

    with path.open("rb") as source:
        info = os.fstat(source.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size <= 0:
            raise ValueError("Select a nonempty regular local file")
        if max_bytes is not None and info.st_size > max_bytes:
            raise ValueError("Select a nonempty local file no larger than 256 MiB")
        try:
            with wave.open(source, "rb") as stream:
                channels, width, rate, frames, compression, _ = stream.getparams()
                if channels not in (1, 2) or width not in (1, 2, 3, 4) or not 8000 <= rate <= 48000 or compression != "NONE":
                    raise WavFormatUnsupported("This WAV variant needs FFmpeg. Open More formats to choose its local installation.")
                if max_seconds is not None and frames > max_seconds * rate:
                    raise ValueError("File audio exceeds the current 10-minute limit; select a shorter clip")
                read_frames = 0
                while read_frames < frames:
                    _check_cancel(cancel)
                    data = stream.readframes(min(rate, frames - read_frames))
                    if not data or len(data) % (channels * width):
                        raise ValueError("The WAV audio is truncated or malformed")
                    read_frames += len(data) // (channels * width)
                    if max_seconds is not None and read_frames > max_seconds * rate:
                        raise ValueError("File audio exceeds the current 10-minute limit; select a shorter clip")
                    if width == 1:
                        pcm = (np.frombuffer(data, dtype=np.uint8).astype(np.float32) - 128) / 128
                    elif width == 3:
                        packed = np.frombuffer(data, dtype=np.uint8).reshape(-1, 3).astype(np.int32)
                        values = packed[:, 0] | (packed[:, 1] << 8) | (packed[:, 2] << 16)
                        pcm = ((values ^ 0x800000) - 0x800000).astype(np.float32) / 8388608
                    else:
                        pcm = np.frombuffer(data, dtype="<i2" if width == 2 else "<i4").astype(np.float32) / (2 ** (width * 8 - 1))
                    mono = pcm.reshape(-1, channels).mean(axis=1)
                    yield resample_audio(mono, rate)
                    if progress is not None:
                        progress("decoding", read_frames / frames)
                _check_cancel(cancel)
                if not read_frames:
                    raise ValueError("The selected file contains no decodable audio")
        except (wave.Error, EOFError) as exc:
            raise WavFormatUnsupported("This WAV variant needs FFmpeg. Open More formats to choose its local installation.") from exc


def decode_local_file(path: str | Path, *, cancel=None, progress=None) -> np.ndarray:
    """Decode the first audio track, downmixed to mono, within fixed RAM bounds."""
    _check_cancel(cancel)
    path = Path(path)
    if not path.is_file():
        raise ValueError("Select an existing local audio or video file")
    from utterleaf.file_decoder import decoder_selection, decode_with_ffmpeg
    if path.suffix.lower() != ".wav" and decoder_selection() is not None:
        return decode_with_ffmpeg(path, max_bytes=MAX_FILE_BYTES, max_seconds=MAX_AUDIO_SECONDS,
                                  cancel=cancel, progress=progress)

    def packaged_decode():
        if path.suffix.lower() == ".wav":
            try:
                return _decode_pcm_wav(path, cancel=cancel, progress=progress)
            except WavFormatUnsupported:
                pass
        return decode_with_ffmpeg(path, max_bytes=MAX_FILE_BYTES, max_seconds=MAX_AUDIO_SECONDS,
                                  cancel=cancel, progress=progress)

    try:
        import av
    except ImportError:
        return packaged_decode()
    if av.__dict__.get("UTTERLEAF_MEDIA_STUB", False):
        return packaged_decode()

    def deny_external(*args, **kwargs):
        raise ValueError("Media referencing external files or network sources is unsupported")

    with path.open("rb") as source:
        import os
        info = os.fstat(source.fileno())
        if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= MAX_FILE_BYTES:
            raise ValueError("Select a nonempty local file no larger than 256 MiB")
        raw = io.BytesIO()
        try:
            with av.open(source, mode="r", io_open=deny_external,
                         options={"protocol_whitelist": ""}) as container:
                if not container.streams.audio:
                    raise ValueError("The selected file has no audio track")
                resampler = av.audio.resampler.AudioResampler(format="s16", layout="mono", rate=SAMPLE_RATE)

                def append(frame):
                    _check_cancel(cancel)
                    array = frame.to_ndarray()
                    if raw.tell() + array.nbytes > MAX_AUDIO_SECONDS * SAMPLE_RATE * 2:
                        raise ValueError("File audio exceeds the current 10-minute limit; select a shorter clip")
                    raw.write(array.tobytes())
                    if progress is not None:
                        progress("decoding", None)

                for frame in container.decode(audio=0):
                    _check_cancel(cancel)
                    frame.pts = None
                    for decoded in resampler.resample(frame):
                        append(decoded)
                for decoded in resampler.resample(None):
                    append(decoded)
        except av.error.FFmpegError as exc:
            raise RuntimeError("Cannot decode this media file; it may be damaged or unsupported") from exc
        except (ValueError, TranscriptionCancelled):
            raise
        except Exception as exc:
            raise RuntimeError("Cannot decode this media file; it may be damaged or unsupported") from exc
        _check_cancel(cancel)
        if not raw.tell():
            raise ValueError("The selected file contains no decodable audio")
        return np.frombuffer(raw.getbuffer(), dtype=np.int16).astype(np.float32) / 32768.0


def iter_local_audio(path: str | Path, *, audio_track: int = 0, cancel=None, progress=None):
    """Yield bounded mono 16 kHz blocks from a finite, explicitly selected file.

    Track numbers are zero-based container audio-stream ordinals, not stereo
    channels or OBS mixer numbers. Timing remains relative to decoded track audio.
    The consumer must close the iterator on early exit.
    """
    import os
    from utterleaf.file_decoder import decoder_selection, iter_ffmpeg_audio

    _check_cancel(cancel)
    if type(audio_track) is not int or not 0 <= audio_track <= 255:
        raise ValueError("Choose an audio track from 1 to 256")
    path = require_local_filesystem(path)
    if not path.is_file():
        raise ValueError("Select an existing local audio or video file")
    if path.stat().st_size <= 0:
        raise ValueError("Select a nonempty regular local file")
    if path.suffix.lower() == ".wav" and audio_track == 0:
        emitted = False
        try:
            with closing(_iter_pcm_wav(path, cancel=cancel, progress=progress)) as blocks:
                for block in blocks:
                    emitted = True
                    yield block
            return
        except WavFormatUnsupported:
            if emitted:
                raise ValueError("The WAV audio became malformed while decoding") from None
    if decoder_selection() is not None:
        yield from iter_ffmpeg_audio(path, audio_track=audio_track, cancel=cancel, progress=progress)
        return
    try:
        import av
    except ImportError:
        av = None
    if av is None or av.__dict__.get("UTTERLEAF_MEDIA_STUB", False):
        yield from iter_ffmpeg_audio(path, audio_track=audio_track, cancel=cancel, progress=progress)
        return

    def deny_external(*args, **kwargs):
        raise ValueError("Media referencing external files or network sources is unsupported")

    with path.open("rb") as source:
        info = os.fstat(source.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size <= 0:
            raise ValueError("Select a nonempty regular local file")
        try:
            with av.open(source, mode="r", io_open=deny_external,
                         options={"protocol_whitelist": ""}) as container:
                if audio_track >= len(container.streams.audio):
                    raise ValueError("The selected audio track does not exist in this file")
                resampler = av.audio.resampler.AudioResampler(format="s16", layout="mono", rate=SAMPLE_RATE)
                emitted = False

                def blocks(frame):
                    _check_cancel(cancel)
                    if frame.samples > 60 * SAMPLE_RATE:
                        raise ValueError("The decoder returned an oversized audio frame")
                    array = frame.to_ndarray()
                    if array.nbytes > 2 * 60 * SAMPLE_RATE:
                        raise ValueError("The decoder returned an oversized audio frame")
                    return array.reshape(-1).astype(np.float32) / 32768.0

                for frame in container.decode(audio=audio_track):
                    _check_cancel(cancel)
                    frame.pts = None
                    for decoded in resampler.resample(frame):
                        block = blocks(decoded)
                        if block.size:
                            emitted = True
                            yield block
                        if progress is not None:
                            progress("decoding", None)
                for decoded in resampler.resample(None):
                    block = blocks(decoded)
                    if block.size:
                        emitted = True
                        yield block
                if not emitted:
                    raise ValueError("The selected file contains no decodable audio")
        except av.error.FFmpegError as exc:
            raise RuntimeError("Cannot decode this media file; it may be damaged or unsupported") from exc
    _check_cancel(cancel)


def audio_windows(blocks, *, cancel=None):
    """Prefer quiet boundaries in bounded batches; adapt the file cancellation event."""
    from utterleaf.audio_batching import audio_windows as batch_audio

    yield from batch_audio(blocks, cancel=cancel.is_set if cancel is not None else None)


def transcribe_file(path: str | Path, cfg: Config, *, cancel=None, progress=None,
                    audio_track: int = 0) -> Transcript:
    """Return unsaved model segments. Offline even when dictation permits downloads.

    Progress receives (phase, fraction_or_none). Cancellation is cooperative between
    decoder frames/model segments; an active native model call cannot be interrupted.
    """
    from utterleaf.transcribe import (
        CPU, CTranslateEngine, _cuda_runtime_error, load_model,
        mark_cuda_unusable, reset_engine,
    )

    _check_cancel(cancel)
    if progress is not None:
        progress("loading", None)
    offline_cfg = replace(cfg, allow_network=False)
    engine = load_model(offline_cfg)
    _check_cancel(cancel)
    if not isinstance(engine, CTranslateEngine):
        raise RuntimeError("Timestamped file transcription requires the CPU or CUDA engine; select CPU in Settings")
    segments = []
    samples = 0
    language = None
    mixed_languages = False
    # A per-window percentage would incorrectly reach 100% on every batch.
    model_progress = (lambda phase, amount: progress(phase, None)) if progress is not None else None
    with closing(iter_local_audio(path, audio_track=audio_track, cancel=cancel, progress=progress)) as blocks:
        for audio in audio_windows(blocks, cancel=cancel):
            try:
                result = engine.transcribe_segments(audio, offline_cfg, cancel=cancel, progress=model_progress)
            except RuntimeError as exc:
                if isinstance(exc, TranscriptionCancelled) or not _cuda_runtime_error(exc):
                    raise
                _check_cancel(cancel)
                mark_cuda_unusable()
                reset_engine()
                engine = load_model(offline_cfg, CPU)
                result = engine.transcribe_segments(audio, offline_cfg, cancel=cancel, progress=model_progress)
            _check_cancel(cancel)
            offset = samples / SAMPLE_RATE
            duration = len(audio) / SAMPLE_RATE
            for segment in result.segments:
                # A model's padded tail can estimate an end beyond real audio.
                # Keep words anchored inside this batch and clip only that end;
                # an out-of-audio start is invalid and must never be hidden.
                if segment.start >= duration:
                    raise ValueError("The model returned timestamps outside the audio batch")
                segments.append(Segment(offset + segment.start,
                                        offset + min(segment.end, duration), segment.text))
            if samples == 0:
                language = result.language
            elif result.language != language:
                mixed_languages = True
            samples += len(audio)
    _check_cancel(cancel)
    if progress is not None:
        progress("complete", 1.0)
    return Transcript(tuple(segments), None if mixed_languages else language)
