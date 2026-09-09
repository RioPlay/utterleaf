"""One short-lived recovery slot, with no disk writes or audio history."""
from __future__ import annotations

import threading
import time


class RecentDictation:
    def __init__(self, ttl: float = 120, *, clock=time.monotonic, timer_factory=threading.Timer, on_expire=None):
        self.ttl = ttl
        self._clock = clock
        self._timer_factory = timer_factory
        self._lock = threading.Lock()
        self._text = ""
        self._deadline = 0.0
        self._generation = 0
        self._timer = None
        self._on_expire = on_expire

    def put(self, text: str) -> int:
        with self._lock:
            self._generation += 1
            generation = self._generation
            if self._timer is not None:
                self._timer.cancel()
            self._text = text
            self._deadline = self._clock() + self.ttl
            # The timer captures a generation number, never the transcript.
            timer = self._timer_factory(self.ttl, self._expire, args=(generation,))
            timer.daemon = True
            self._timer = timer
            timer.start()
            return generation

    def _expire(self, generation: int) -> None:
        expired = False
        with self._lock:
            if generation == self._generation:
                self._text = ""
                self._timer = None
                expired = True
        if expired and self._on_expire is not None:
            self._on_expire(generation)

    def get(self) -> str:
        expired = None
        with self._lock:
            if self._text and self._clock() >= self._deadline:
                self._text = ""
                expired = self._generation
            text = self._text
        if expired is not None and self._on_expire is not None:
            self._on_expire(expired)
        return text

    def clear(self) -> None:
        with self._lock:
            self._generation += 1
            self._text = ""
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None
