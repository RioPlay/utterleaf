"""Bounded RAM capture backed by an automatically removed local temporary file.

Only explicitly started recording owns a store. Audio is not encrypted; the OS
temporary-file protections apply. Deletion is lifecycle cleanup, not secure erase.
The callback never waits for disk I/O. One writer owns the file until sealed.
"""

from __future__ import annotations

from collections import deque
import shutil
import tempfile
import threading

import numpy as np

from utterleaf.transcript import TranscriptionCancelled
from utterleaf.local_filesystem import LocalFilesystemError, require_local_filesystem

MAX_PENDING_BYTES = 8 * 1024 * 1024
MAX_BLOCK_BYTES = 1024 * 1024
WINDOW_SECONDS = 30
MIN_FREE_BYTES = 256 * 1024 * 1024


class CaptureStorageError(OSError):
    """The temporary recording cannot start on the selected local filesystem."""


class CaptureStore:
    def __init__(self, sample_rate: float):
        if not np.isfinite(sample_rate) or not 8000 <= sample_rate <= 192000:
            raise ValueError("Unsupported capture sample rate")
        self.sample_rate = float(sample_rate)
        self._condition = threading.Condition()
        self._pending = deque()
        self._pending_bytes = 0
        self._accepted_samples = 0
        self._written_samples = 0
        self._finishing = False
        self._closed = False
        self._error = None
        self._ready = threading.Event()
        try:
            self._directory = require_local_filesystem(tempfile.gettempdir())
        except LocalFilesystemError:
            raise CaptureStorageError(
                "Temporary audio needs a verified local folder on this computer, not a network or shared filesystem."
            ) from None
        try:
            free = shutil.disk_usage(self._directory).free
        except OSError as exc:
            raise CaptureStorageError(
                "Temporary audio storage could not be inspected. Check the temporary folder and its permissions."
            ) from exc
        if free < MIN_FREE_BYTES:
            raise CaptureStorageError("Free some disk space before recording. Temporary audio keeps a 256 MiB reserve.")
        # No transcript, source name, device name or user identity in the filename.
        try:
            self._file = tempfile.TemporaryFile(mode="w+b", prefix="utterleaf-audio-", buffering=0,
                                                dir=self._directory)
        except OSError as exc:
            raise CaptureStorageError(
                "Temporary audio could not be created. Check free space and temporary-folder permissions."
            ) from exc
        try:
            self._worker = threading.Thread(target=self._write, name="utterleaf-audio-store", daemon=True)
            self._worker.start()
        except BaseException as exc:
            self._file.close()
            if isinstance(exc, Exception):
                raise CaptureStorageError(
                    "Temporary audio storage could not start. Try recording again."
                ) from exc
            raise

    def __len__(self):
        with self._condition:
            samples = self._written_samples if self._ready.is_set() else self._accepted_samples
        return int(round(samples * 16000 / self.sample_rate))

    @property
    def error(self):
        with self._condition:
            return self._error

    @property
    def pending_bytes(self):
        with self._condition:
            return self._pending_bytes

    def append(self, audio: np.ndarray) -> bool:
        """Accept a callback block without waiting for storage; refuse atomically."""
        if (not isinstance(audio, np.ndarray) or audio.dtype != np.float32 or
                audio.ndim not in (1, 2) or (audio.ndim == 2 and audio.shape[1] != 1) or
                audio.nbytes > MAX_BLOCK_BYTES):
            raise ValueError("Capture blocks must be bounded mono float32 audio")
        with self._condition:
            if self._closed or self._finishing or self._error:
                return False
            if self._pending_bytes + audio.nbytes > MAX_PENDING_BYTES:
                self._error = "Temporary audio storage could not keep up. Only the stored portion can be recovered."
                self._finishing = True
                self._condition.notify_all()
                return False
            self._pending.append(audio.reshape(-1).copy())
            self._pending_bytes += audio.nbytes
            self._accepted_samples += audio.size
            self._condition.notify()
            return True

    def finish(self):
        """Seal capture without blocking the UI while the writer drains its queue."""
        with self._condition:
            self._finishing = True
            self._condition.notify_all()
        return self

    def wait_ready(self, cancelled=lambda: False):
        while not self._ready.wait(0.05):
            if cancelled():
                raise TranscriptionCancelled("Recording cancelled")
        if cancelled() or self._closed:
            raise TranscriptionCancelled("Recording cancelled")

    def chunks(self, cancelled=lambda: False):
        """Yield at most 30 seconds of mono 16 kHz audio; no whole-take allocation.

        The caller must inspect `error` after wait_ready and label a stored prefix
        as incomplete rather than automatically inserting it as a complete take.
        """
        from utterleaf.audio import resample_audio

        self.wait_ready(cancelled)
        self._file.seek(0)
        block_samples = int(round(WINDOW_SECONDS * self.sample_rate))
        remaining = self._written_samples
        while remaining:
            if cancelled() or self._closed:
                raise TranscriptionCancelled("Recording cancelled")
            count = min(remaining, block_samples)
            data = self._file.read(count * 4)
            if len(data) != count * 4:
                raise OSError("Temporary audio could not be read completely")
            remaining -= count
            yield resample_audio(np.frombuffer(data, dtype=np.float32), self.sample_rate)

    def close(self):
        """Cancel pending writes; the writer closes its handle after in-flight I/O."""
        with self._condition:
            if self._closed:
                return
            self._closed = True
            self._pending.clear()
            self._pending_bytes = 0
            self._condition.notify_all()
            if self._ready.is_set():
                self._file.close()

    def _write(self):
        checked_at = -int(self.sample_rate)
        try:
            while True:
                with self._condition:
                    while not self._pending and not self._finishing and not self._closed:
                        self._condition.wait()
                    if self._closed or (not self._pending and self._finishing):
                        break
                    audio = self._pending.popleft()
                    self._pending_bytes -= audio.nbytes
                    self._condition.notify_all()
                # A short write is not success. Retain only fully written samples.
                if self._written_samples - checked_at >= self.sample_rate:
                    checked_at = self._written_samples
                    if shutil.disk_usage(self._directory).free < MIN_FREE_BYTES + audio.nbytes:
                        raise OSError("Temporary audio reserve reached")
                data = memoryview(audio).cast("B")
                written = 0
                try:
                    while written < len(data):
                        count = self._file.write(data[written:])
                        if count is None or count <= 0:
                            raise OSError("Temporary audio write made no progress")
                        written += count
                finally:
                    with self._condition:
                        self._written_samples += written // 4
        except Exception:
            with self._condition:
                self._error = "Temporary audio storage failed. Only the stored portion can be recovered."
                self._finishing = True
                self._pending.clear()
                self._pending_bytes = 0
        finally:
            with self._condition:
                if self._closed:
                    self._file.close()
                self._ready.set()
