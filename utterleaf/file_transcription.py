"""Explicit, bounded local media transcription; never saves audio or downloads models."""

from __future__ import annotations

from dataclasses import replace
import io
from pathlib import Path
import stat
import wave

import numpy as np

from utterleaf.config import Config
from utterleaf.transcript import Transcript, TranscriptionCancelled

MAX_FILE_BYTES = 256 * 1024 * 1024
MAX_AUDIO_SECONDS = 600
SAMPLE_RATE = 16000


def _check_cancel(cancel):
    if cancel is not None and cancel.is_set():
        raise TranscriptionCancelled("File transcription cancelled")


def _decode_pcm_wav(path, *, cancel=None, progress=None):
    """Small packaged decoder: integer PCM WAV, mono/stereo, 8–48 kHz."""
    import os
    from utterleaf.audio import resample_audio

    with path.open("rb") as source:
        info = os.fstat(source.fileno())
        if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= MAX_FILE_BYTES:
            raise ValueError("Select a nonempty local file no larger than 256 MiB")
        try:
            with wave.open(source, "rb") as stream:
                channels, width, rate, frames, compression, _ = stream.getparams()
                if channels not in (1, 2) or width not in (1, 2, 3, 4) or not 8000 <= rate <= 48000 or compression != "NONE":
                    raise ValueError("Packaged WAV support requires mono/stereo integer PCM, 8–32 bit, 8–48 kHz")
                if frames > MAX_AUDIO_SECONDS * rate:
                    raise ValueError("File audio exceeds the current 10-minute limit; select a shorter clip")
                chunks = []
                read_frames = 0
                while read_frames < frames:
                    _check_cancel(cancel)
                    data = stream.readframes(min(rate, frames - read_frames))
                    if not data or len(data) % (channels * width):
                        raise ValueError("The WAV audio is truncated or malformed")
                    read_frames += len(data) // (channels * width)
                    if read_frames > MAX_AUDIO_SECONDS * rate:
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
                    chunks.append(resample_audio(mono, rate))
                    if progress is not None:
                        progress("decoding", read_frames / frames)
                _check_cancel(cancel)
                if not chunks:
                    raise ValueError("The selected file contains no decodable audio")
                return np.concatenate(chunks)
        except (wave.Error, EOFError) as exc:
            raise RuntimeError("This build supports integer PCM WAV files only; other media requires a source installation with PyAV") from exc


def decode_local_file(path: str | Path, *, cancel=None, progress=None) -> np.ndarray:
    """Decode the first audio track, downmixed to mono, within fixed RAM bounds."""
    _check_cancel(cancel)
    path = Path(path)
    if not path.is_file():
        raise ValueError("Select an existing local audio or video file")
    try:
        import av
    except ImportError:
        return _decode_pcm_wav(path, cancel=cancel, progress=progress)
    if av.__dict__.get("UTTERLEAF_MEDIA_STUB", False):
        return _decode_pcm_wav(path, cancel=cancel, progress=progress)

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


def transcribe_file(path: str | Path, cfg: Config, *, cancel=None, progress=None) -> Transcript:
    """Return unsaved model segments. Offline even when dictation permits downloads.

    Progress receives (phase, fraction_or_none). Cancellation is cooperative between
    decoder frames/model segments; an active native model call cannot be interrupted.
    """
    from utterleaf.transcribe import (
        CPU, CTranslateEngine, _cuda_runtime_error, load_model,
        mark_cuda_unusable, reset_engine,
    )

    audio = decode_local_file(path, cancel=cancel, progress=progress)
    _check_cancel(cancel)
    if progress is not None:
        progress("loading", None)
    offline_cfg = replace(cfg, allow_network=False)
    engine = load_model(offline_cfg)
    _check_cancel(cancel)
    if not isinstance(engine, CTranslateEngine):
        raise RuntimeError("Timestamped file transcription requires the CPU or CUDA engine; select CPU in Settings")
    try:
        result = engine.transcribe_segments(audio, offline_cfg, cancel=cancel, progress=progress)
    except RuntimeError as exc:
        if isinstance(exc, TranscriptionCancelled) or not _cuda_runtime_error(exc):
            raise
        _check_cancel(cancel)
        mark_cuda_unusable()
        reset_engine()
        result = load_model(offline_cfg, CPU).transcribe_segments(
            audio, offline_cfg, cancel=cancel, progress=progress,
        )
    _check_cancel(cancel)
    if progress is not None:
        progress("complete", 1.0)
    return result
