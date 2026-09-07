"""Record microphone audio while the hotkey is held."""

from __future__ import annotations

import logging
import threading
from collections import deque

import numpy as np
import sounddevice as sd

log = logging.getLogger("utterleaf")

SAMPLE_RATE = 16000
PREROLL_SECONDS = 0.30
TAIL_SECONDS = 0.16


class Recorder:
    """Keeps the mic stream open and a short pre-roll so the first word is not cut."""

    def __init__(self, device: str = "") -> None:
        self._lock = threading.Lock()
        self._chunks: list[np.ndarray] = []
        self._ring: deque[np.ndarray] = deque()
        self._ring_samples = 0
        self._stream: sd.InputStream | None = None
        self.recording = False
        self.preferred_device = (device or "").strip()
        self.device_name = ""

    def set_device(self, name: str) -> None:
        name = (name or "").strip()
        if name == self.preferred_device:
            return
        self.preferred_device = name
        if self.recording:
            return
        self.close()

    def _active_name(self) -> str:
        try:
            resolved = resolve_input_device(self.preferred_device)
            if resolved is None:
                return str(sd.query_devices(kind="input").get("name") or "default")
            info = sd.query_devices(resolved)
            return str(info.get("name") or self.preferred_device or "default")
        except Exception:
            return self.device_name or self.preferred_device or "default"

    def prepare(self) -> None:
        name = self._active_name()
        if self._stream is not None and name != self.device_name:
            log.info("Mic changed (%s -> %s); reopening", self.device_name, name)
            self.close()
        if self._stream is not None:
            return
        self.device_name = name
        chosen = resolve_input_device(self.preferred_device)
        log.info("Microphone: %s", self.device_name)
        stream = sd.InputStream(
            device=chosen,
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype="float32",
            blocksize=512,
            callback=self._on_audio,
        )
        stream.start()
        self._stream = stream

    def start(self) -> None:
        self.prepare()
        with self._lock:
            self._chunks = [chunk.copy() for chunk in self._ring]
            self.recording = True

    def _on_audio(self, indata, frames, time, status) -> None:  # noqa: ARG002
        if status:
            log.warning("Mic status: %s", status)
        copy = indata.copy()
        with self._lock:
            self._ring.append(copy)
            self._ring_samples += len(copy)
            limit = int(PREROLL_SECONDS * SAMPLE_RATE)
            while self._ring and self._ring_samples - len(self._ring[0]) >= limit:
                dropped = self._ring.popleft()
                self._ring_samples -= len(dropped)
            if self.recording:
                self._chunks.append(copy)

    def snapshot(self, max_seconds: float | None = None) -> np.ndarray:
        # Select only the needed tail under the lock, then copy outside the audio
        # callback's critical section. Draft cost stays constant for long takes.
        with self._lock:
            if not self._chunks:
                return np.zeros(0, dtype=np.float32)
            if max_seconds is None:
                chunks = list(self._chunks)
            else:
                limit = max(0, int(max_seconds * SAMPLE_RATE))
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
        return audio if max_seconds is None else audio[-limit:]

    def stop(self) -> np.ndarray:
        with self._lock:
            self.recording = False
            if not self._chunks:
                return np.zeros(0, dtype=np.float32)
            chunks = self._chunks
            self._chunks = []
        return np.concatenate(chunks, axis=0).reshape(-1)

    def close(self) -> None:
        with self._lock:
            self.recording = False
            stream = self._stream
            self._stream = None
            self._ring.clear()
            self._ring_samples = 0
            self._chunks = []
        if stream is not None:
            stream.stop()
            stream.close()

    def seconds(self, audio: np.ndarray) -> float:
        return float(len(audio)) / SAMPLE_RATE


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
    lowered = wanted.lower()
    for index, device in enumerate(devices):
        if device["max_input_channels"] > 0 and lowered in str(device["name"]).lower():
            return index
    log.warning("Microphone %r not found; using system default", wanted)
    return None
