"""Local speech-end detection during explicitly started, bounded dictation.

Sample-clock snapshots prevent slow inference from manufacturing a quiet pause.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from importlib import metadata
from importlib.resources import files
import logging
import math
import threading
from typing import Callable

import numpy as np

SAMPLE_RATE = 16000
FRAME_SAMPLES = 512
WINDOW_SAMPLES = SAMPLE_RATE * 8
SILERO_SHA256 = "4cbf549b8326f60f80f2536d9eefeb450a9abe83365a098031c89719f1be17d2"
SILERO_BYTES = 1245151
REVIEWED_PACKAGES = {"faster-whisper": "1.2.1", "onnxruntime": "1.28.0"}
log = logging.getLogger("utterleaf")


def _notify(callback: Callable, *args: object) -> None:
    try:
        callback(*args)
    except Exception:
        # Do not leave the worker stuck or log transcript/target content from
        # consumer exceptions. The microphone watchdog/manual controls remain.
        log.warning("Speech-end notification failed; use manual stop")


def local_silero_detector() -> Callable[[np.ndarray], np.ndarray] | None:
    """Load the reviewed package asset on a worker, with no network fallback.

    This instance does not share transcription's cached VAD session. Unknown
    dependency/model updates need review before this endpoint path loads them.
    """
    try:
        if any(metadata.version(name) != version for name, version in REVIEWED_PACKAGES.items()):
            return None
        path = files("faster_whisper").joinpath("assets", "silero_vad_v6.onnx")
        with path.open("rb") as source:
            raw = source.read(SILERO_BYTES + 1)
        if len(raw) != SILERO_BYTES or hashlib.sha256(raw).hexdigest() != SILERO_SHA256:
            return None
        from faster_whisper.vad import SileroVADModel
        # ONNX Runtime accepts serialized model bytes. Load the exact buffer we
        # checked, so replacing the package file between hash and load is inert.
        return SileroVADModel(raw)
    except Exception:
        return None


@dataclass(frozen=True)
class EndpointOptions:
    pause_seconds: float = 1.2

    def __post_init__(self) -> None:
        if not math.isfinite(self.pause_seconds) or not 0.5 <= self.pause_seconds <= 3.0:
            raise ValueError("Speech-end pause must be between 0.5 and 3 seconds")


class SpeechEndpoint:
    """One inference and one newest pending snapshot per instance.

    Four consecutive positive frames establish onset (128 ms); hysteresis then
    treats >=0.35 as continuing speech. Silence before onset never ends a take.
    Unobserved audio intervals reset onset rather than counting toward a pause.
    The app must guard session/target and result freshness before stopping.
    Cancellation cannot recall a callback already handed to the consumer. App
    integration binds callbacks to an instance/take identity and rejects old ones.
    """

    def __init__(self, detector: Callable[[np.ndarray], np.ndarray],
                 on_end: Callable[[int], None], *,
                 options: EndpointOptions = EndpointOptions(),
                 on_error: Callable[[], None] | None = None) -> None:
        self._detector, self._on_end = detector, on_end
        self._options, self._on_error = options, on_error
        self._lock = threading.Lock()
        self._active = False
        self._generation = 0
        self._onset = 0
        self._last_speech: int | None = None
        self._processed_end = self._submitted_end = 0
        self._running = False
        self._latest: tuple[int, np.ndarray, int] | None = None

    @property
    def active(self) -> bool:
        with self._lock:
            return self._active

    @property
    def processed_samples(self) -> int:
        with self._lock:
            return self._processed_end

    def start(self) -> int:
        with self._lock:
            self._generation += 1
            self._active = True
            self._onset = self._processed_end = self._submitted_end = 0
            self._last_speech = self._latest = None
            return self._generation

    def cancel(self) -> None:
        with self._lock:
            self._active = False
            self._latest = None
            self._onset = 0
            self._last_speech = None

    def submit(self, audio: np.ndarray, generation: int, *, end_sample: int) -> None:
        """Queue a mono 16 kHz tail with the take's absolute sample count.

        Caller polls at most four times per second. Duplicate/stale sample counts
        do no inference. Copying protects capture from upstream in-place work.
        """
        if type(end_sample) is not int or end_sample < 0:
            raise ValueError("Invalid endpoint sample clock")
        audio = np.asarray(audio)
        if audio.ndim != 1 or audio.size > end_sample:
            raise ValueError("Endpoint audio must be a mono tail within the take")
        if audio.size < FRAME_SAMPLES:
            return
        with self._lock:
            if not self._active or generation != self._generation or end_sample <= self._submitted_end:
                return
            self._latest = (generation, np.asarray(audio[-WINDOW_SAMPLES:], dtype=np.float32).copy(), end_sample)
            self._submitted_end = end_sample
            if self._running:
                return
            self._running = True
        try:
            threading.Thread(target=self._run, name="utterleaf-speech-end", daemon=True).start()
        except Exception:
            with self._lock:
                self._running = False
                self._active = False
                self._latest = None
            if self._on_error is not None:
                _notify(self._on_error)

    def _run(self) -> None:
        while True:
            with self._lock:
                if self._latest is None:
                    self._running = False
                    return
                generation, audio, end_sample = self._latest
                self._latest = None
            start_sample = end_sample - audio.size
            # Global alignment avoids double-counting overlapping frame grids.
            skip = (-start_sample) % FRAME_SAMPLES
            start_sample += skip
            count = (audio.size - skip) // FRAME_SAMPLES * FRAME_SAMPLES
            audio = audio[skip:skip + count]
            if not count:
                continue
            try:
                if not np.isfinite(audio).all():
                    raise ValueError("Non-finite capture samples")
                probabilities = np.asarray(self._detector(audio)).reshape(-1)
                if (probabilities.size != count // FRAME_SAMPLES
                        or not np.isfinite(probabilities).all()
                        or np.any((probabilities < 0) | (probabilities > 1))):
                    raise ValueError("Invalid speech probabilities")
            except Exception:
                with self._lock:
                    failed = self._active and generation == self._generation
                    if failed:
                        self._active = False
                        self._latest = None
                if failed and self._on_error is not None:
                    _notify(self._on_error)
                continue
            fire = False
            with self._lock:
                if not self._active or generation != self._generation:
                    continue
                if start_sample > self._processed_end:
                    self._onset = 0
                    self._last_speech = None
                for index, probability in enumerate(probabilities):
                    frame_end = start_sample + (index + 1) * FRAME_SAMPLES
                    if frame_end <= self._processed_end:
                        continue
                    if probability >= 0.5:
                        self._onset += 1
                        if self._onset >= 4 or self._last_speech is not None:
                            self._last_speech = frame_end
                    elif self._last_speech is not None and probability >= 0.35:
                        self._last_speech = frame_end
                    else:
                        self._onset = 0
                    self._processed_end = frame_end
                # Resumed speech later in the newest batch cancels an earlier
                # pause. Pending fresher audio must be analyzed before ending.
                if (self._last_speech is not None and self._latest is None
                        and self._processed_end - self._last_speech >= self._options.pause_seconds * SAMPLE_RATE):
                    self._active = False
                    fire = True
                result_end = self._processed_end
            # Session guards in the app arbitrate cancellation immediately
            # before this callback; no external call runs under this lock.
            if fire:
                _notify(self._on_end, result_end)
