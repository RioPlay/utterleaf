"""Import-time stand-in for PyAV, bundled only in frozen builds.

faster-whisper imports ``av`` at module load but uses it solely inside
``decode_audio()`` — the file/byte-input path. Utterleaf feeds numpy arrays
from the microphone straight into ``WhisperModel.transcribe``, so PyAV is
never called. PyAV's official wheels ship a GPL build of FFmpeg (libx264 /
libx265); Utterleaf's distribution policy is to exclude GPL-licensed codecs
rather than accept their terms, so the real package is excluded and this
stub satisfies the import.

If a file path ever reaches the engine, any attribute access here fails
loudly instead of silently producing nothing.
"""

from __future__ import annotations


def __getattr__(name: str):
    raise RuntimeError(
        f"PyAV is not bundled (its bundled FFmpeg is GPL), but something "
        f"accessed av.{name}. Pass numpy audio to WhisperModel.transcribe "
        f"instead of a file path."
    )
