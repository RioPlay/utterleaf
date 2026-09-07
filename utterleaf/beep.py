"""Short status tones rendered as WAV data, played without blocking the caller."""

from __future__ import annotations

import logging
import sys
import threading

log = logging.getLogger("utterleaf")

_TONE_CACHE: dict[str, bytes] = {}
_TONE_FILES: dict[str, str] = {}
_TONE_FREQS = {"start": 760, "stop": 560, "ok": 680, "err": 310}


def tone_wav(freq: float, duration_ms: int = 90, sample_rate: int = 22050) -> bytes:
    """A short sine tone with a fade in/out, so it doesn't click like winsound.Beep's square wave."""
    import io
    import math
    import struct
    import wave

    n = int(sample_rate * duration_ms / 1000)
    fade = max(1, int(sample_rate * 0.012))
    amplitude = 0.28 * 32767
    samples = bytearray()
    for i in range(n):
        env = min(i / fade, (n - i) / fade, 1.0)
        value = int(amplitude * env * math.sin(2 * math.pi * freq * i / sample_rate))
        samples += struct.pack("<h", value)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(bytes(samples))
    return buf.getvalue()


def audio_player() -> list[str] | None:
    """Command prefix that plays a WAV path, or None when the box has no player."""
    import shutil

    if sys.platform == "darwin":
        found = shutil.which("afplay")
        return [found] if found else None
    for name, args in (("paplay", []), ("aplay", ["-q"]), ("play", ["-q"])):
        found = shutil.which(name)
        if found:
            return [found, *args]
    return None


def _tone_file(kind: str) -> str:
    """WAV on disk for players that cannot read stdin. Written once per kind, atomically."""
    import os
    import tempfile
    from pathlib import Path

    path = _TONE_FILES.get(kind)
    if path is not None and Path(path).is_file():
        return path
    dest = Path(tempfile.gettempdir()) / f"utterleaf-{kind}.wav"
    tmp = dest.with_suffix(f".{os.getpid()}.wav")
    tmp.write_bytes(tone_wav(_TONE_FREQS.get(kind, 480)))
    os.replace(tmp, dest)
    _TONE_FILES[kind] = str(dest)
    return str(dest)


def _beep_sync(kind: str) -> None:
    if sys.platform == "win32":
        try:
            import winsound

            data = _TONE_CACHE.get(kind)
            if data is None:
                data = tone_wav(_TONE_FREQS.get(kind, 480))
                _TONE_CACHE[kind] = data
            winsound.PlaySound(data, winsound.SND_MEMORY | winsound.SND_ASYNC)
            return
        except Exception:
            log.debug("winsound beep failed", exc_info=True)
    else:
        player = audio_player()
        if player is not None:
            try:
                import subprocess

                subprocess.Popen(
                    [*player, _tone_file(kind)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                return
            except Exception:
                log.debug("Beep player failed", exc_info=True)
    if sys.stderr is not None:
        sys.stderr.write("\a")
        sys.stderr.flush()


def beep(kind: str, enabled: bool) -> None:
    if not enabled:
        return
    threading.Thread(target=_beep_sync, args=(kind,), daemon=True).start()
