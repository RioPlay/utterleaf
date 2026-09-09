"""Record microphone audio while the hotkey is held."""

from __future__ import annotations

import logging
import sys
import threading
import time
from collections import deque

import numpy as np
import sounddevice as sd

log = logging.getLogger("utterleaf")

SAMPLE_RATE = 16000
PREROLL_SECONDS = 0.30
TAIL_SECONDS = 0.16


def resample_audio(audio: np.ndarray, input_rate: float) -> np.ndarray:
    """Convert captured mono PCM to Whisper's 16 kHz outside the callback.

    Apply a windowed-sinc low-pass filter before downsampling to avoid aliasing.
    Padding keeps the filter centered without changing the take's duration.
    """
    audio = np.asarray(audio, dtype=np.float32).reshape(-1)
    if not audio.size or input_rate == SAMPLE_RATE:
        return audio
    if not np.isfinite(input_rate) or input_rate <= 0:
        raise ValueError("Input sample rate must be positive and finite")
    count = int(round(audio.size * SAMPLE_RATE / input_rate))
    if count == 0:
        return np.zeros(0, dtype=np.float32)
    if input_rate > SAMPLE_RATE:
        cutoff = 0.45 * SAMPLE_RATE / input_rate
        offsets = np.arange(-63, 64)
        kernel = 2 * cutoff * np.sinc(2 * cutoff * offsets) * np.hamming(127)
        kernel /= kernel.sum()
        audio = np.convolve(np.pad(audio, (63, 63), mode="edge"), kernel, mode="valid")
    return np.interp(np.arange(count) * input_rate / SAMPLE_RATE,
                     np.arange(audio.size), audio).astype(np.float32)


class Recorder:
    """Capture one take with a short pre-roll; the caller releases the stream."""

    def __init__(self, device: str = "") -> None:
        self._lock = threading.Lock()
        self._chunks: list[np.ndarray] = []
        self._ring: deque[np.ndarray] = deque()
        self._ring_samples = 0
        self._stream: sd.InputStream | None = None
        self._opened_at: float | None = None
        self.recording = False
        self.preferred_device = (device or "").strip()
        self.device_name = ""
        self.input_rate = float(SAMPLE_RATE)
        self._capture_limit = None
        self._captured_samples = 0
        self.limit_reached = threading.Event()

    def set_device(self, name: str) -> None:
        name = (name or "").strip()
        if name == self.preferred_device:
            return
        self.preferred_device = name
        if self.recording:
            return
        self.close()

    def prepare(self) -> None:
        try:
            chosen = resolve_input_device(self.preferred_device)
            info = sd.query_devices(chosen, kind="input")
            chosen, info = shared_input_device(chosen, info, self.preferred_device)
        except Exception:
            self.close()
            raise
        name = str(info.get("name") or self.preferred_device or "default")
        if self._stream is not None and name != self.device_name:
            log.info("Mic changed (%s -> %s); reopening", self.device_name, name)
            self.close()
        if self._stream is not None:
            return
        self.device_name = str(info.get("name") or name)
        self.input_rate = float(info["default_samplerate"])
        log.info("Microphone: %s (%g Hz capture, %d Hz transcription)",
                 self.device_name, self.input_rate, SAMPLE_RATE)
        # ALSA-to-Pulse bridging overflows the small default buffer right at
        # open; dictation never needs low capture latency on Linux.
        extra = {"latency": "high"} if sys.platform.startswith("linux") else {}
        if sys.platform == "win32" and "hostapi" in info:
            host = sd.query_hostapis(info["hostapi"])
            if host["name"] == "Windows WASAPI":
                extra["extra_settings"] = sd.WasapiSettings(exclusive=False)
        # Retry only PortAudio's device-unavailable error. A permission or format
        # error needs a different action, and must not turn into a retry loop.
        for attempt in range(2):
            stream = None
            try:
                stream = sd.InputStream(
                    device=chosen, samplerate=self.input_rate, channels=1,
                    dtype="float32", blocksize=0, callback=self._on_audio, **extra,
                )
                stream.start()
            except Exception as exc:
                if stream is not None:
                    try:
                        stream.close()
                    except Exception:
                        log.warning("Could not close failed microphone stream", exc_info=True)
                        raise exc
                with self._lock:
                    self._ring.clear()
                    self._ring_samples = 0
                if attempt == 0 and device_unavailable(exc):
                    log.info("Microphone temporarily unavailable; retrying once")
                    time.sleep(0.15)
                    continue
                raise
            self._stream = stream
            self._opened_at = time.monotonic()
            break

    def start(self, max_seconds: float | None = None) -> None:
        if max_seconds is not None and (not np.isfinite(max_seconds) or max_seconds <= 0):
            raise ValueError("Recording limit must be positive and finite")
        self.prepare()
        with self._lock:
            self._chunks = [chunk.copy() for chunk in self._ring]
            self._captured_samples = sum(len(chunk) for chunk in self._chunks)
            # The limit measures new speech; keep the small pre-roll as well.
            self._capture_limit = (
                self._captured_samples + int(max_seconds * self.input_rate)
                if max_seconds is not None else None
            )
            self.limit_reached.clear()
            self.recording = True

    def _on_audio(self, indata, frames, timestamp, status) -> None:  # noqa: ARG002
        if status:
            # ALSA-to-Pulse bridging overflows once at stream open before any
            # recording starts; warn only about overflows that matter.
            startup_overflow = (
                getattr(status, "input_overflow", False)
                and self._opened_at is not None
                and time.monotonic() - self._opened_at < 0.5
            )
            (log.debug if startup_overflow else log.warning)("Mic status: %s", status)
        copy = indata.copy()
        with self._lock:
            self._ring.append(copy)
            self._ring_samples += len(copy)
            limit = int(PREROLL_SECONDS * self.input_rate)
            while self._ring and self._ring_samples - len(self._ring[0]) >= limit:
                dropped = self._ring.popleft()
                self._ring_samples -= len(dropped)
            if self.recording:
                remaining = len(copy) if self._capture_limit is None else self._capture_limit - self._captured_samples
                if remaining > 0:
                    chunk = copy[:remaining].copy() if remaining < len(copy) else copy
                    self._chunks.append(chunk)
                    self._captured_samples += len(chunk)
                if self._capture_limit is not None and self._captured_samples >= self._capture_limit:
                    self.limit_reached.set()

    def snapshot(self, max_seconds: float | None = None) -> np.ndarray:
        # Select only the needed tail under the lock, then copy outside the audio
        # callback's critical section. Draft cost stays constant for long takes.
        with self._lock:
            if not self._chunks:
                return np.zeros(0, dtype=np.float32)
            if max_seconds is None:
                chunks = list(self._chunks)
            else:
                limit = max(0, int(max_seconds * self.input_rate))
                if not limit:
                    return np.zeros(0, dtype=np.float32)
                chunks = []
                count = 0
                for chunk in reversed(self._chunks):
                    chunks.append(chunk)
                    count += len(chunk)
                    if count >= limit:
                        break
                chunks.reverse()
        audio = np.concatenate(chunks, axis=0).reshape(-1)
        return resample_audio(audio if max_seconds is None else audio[-limit:], self.input_rate)

    def stop(self) -> np.ndarray:
        with self._lock:
            self.recording = False
            if not self._chunks:
                return np.zeros(0, dtype=np.float32)
            chunks = self._chunks
            self._chunks = []
        return resample_audio(np.concatenate(chunks, axis=0).reshape(-1), self.input_rate)

    def close(self) -> None:
        with self._lock:
            self.recording = False
            stream = self._stream
            self._stream = None
            self._ring.clear()
            self._ring_samples = 0
            self._chunks = []
        if stream is not None:
            try:
                stream.stop()
            except Exception:
                log.warning("Microphone stop failed; releasing the stream", exc_info=True)
            finally:
                stream.close()

    def seconds(self, audio: np.ndarray) -> float:
        return float(len(audio)) / SAMPLE_RATE


def device_unavailable(exc: BaseException) -> bool:
    return isinstance(exc, sd.PortAudioError) and len(exc.args) > 1 and exc.args[1] == -9985


class SelectedMicrophoneUnavailable(RuntimeError):
    """The explicitly selected input is absent; capture must not fall back."""


def microphone_error_hint(exc: BaseException) -> str:
    if isinstance(exc, SelectedMicrophoneUnavailable):
        return ("Your selected microphone is unavailable. Reconnect it, then try again. "
                "To use another input, open Settings → Dictation, refresh devices, "
                "choose an input and Save. If it still does not appear, restart Utterleaf.")
    if device_unavailable(exc):
        return ("Microphone unavailable. Another app may have exclusive access, or the device may be disconnected. "
                "Release it in that app, reconnect it, or choose an input in Settings → Dictation, then try again.")
    return "Could not open the microphone. Check microphone permission and your input in Settings → Dictation, then try again."


def shared_input_device(chosen, info, preferred):
    """Prefer WASAPI without fuzzy matching a named mic to different hardware."""
    if sys.platform != "win32" or "hostapi" not in info:
        return chosen, info
    try:
        hosts = sd.query_hostapis()
        wasapi = next((i for i, host in enumerate(hosts) if host["name"] == "Windows WASAPI"), None)
        if wasapi is None or info["hostapi"] == wasapi:
            return chosen, info
        if not preferred:
            index = hosts[wasapi]["default_input_device"]
            if index >= 0:
                candidate = sd.query_devices(index)
                if candidate["max_input_channels"] > 0 and candidate["hostapi"] == wasapi:
                    return index, candidate
        else:
            matches = [(i, d) for i, d in enumerate(sd.query_devices())
                       if d["max_input_channels"] > 0 and d["hostapi"] == wasapi
                       and d["name"] == info["name"]]
            if len(matches) == 1:
                return matches[0]
    except (sd.PortAudioError, KeyError, IndexError, TypeError):
        log.debug("WASAPI selection unavailable; keeping selected input", exc_info=True)
    return chosen, info


def list_devices() -> list[str]:
    devices = sd.query_devices()
    names = []
    for index, device in enumerate(devices):
        if device["max_input_channels"] > 0:
            names.append(f"{index}: {device['name']}")
    return names


def list_input_names() -> list[str]:
    """Unique input device names for the Settings picker."""
    names: list[str] = []
    seen: set[str] = set()
    for device in sd.query_devices():
        if device["max_input_channels"] <= 0:
            continue
        name = str(device["name"] or "").strip()
        if not name or name in seen:
            continue
        seen.add(name)
        names.append(name)
    return names


def resolve_input_device(name: str) -> int | None:
    """Map a saved device name to a sounddevice index. None = system default."""
    wanted = (name or "").strip()
    if not wanted:
        return None
    devices = sd.query_devices()
    for index, device in enumerate(devices):
        if device["max_input_channels"] > 0 and str(device["name"]) == wanted:
            return index
    raise SelectedMicrophoneUnavailable("Selected microphone is not in the input device list")
