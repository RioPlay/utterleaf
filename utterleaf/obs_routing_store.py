"""Bounded-memory private storage for OBS routing observations."""

from __future__ import annotations

from collections import deque
import tempfile
import threading
from typing import BinaryIO, Callable, Iterator

from utterleaf.local_filesystem import LocalFilesystemError, require_local_filesystem
from utterleaf.obs_protocol import (
    HEADER_BYTES,
    MAX_ROUTING_BODY_BYTES,
    PROVENANCE_VERSION,
    FrameDecoder,
    ProtocolError,
    RoutingFrame,
    encode_frame,
)
from utterleaf.transcript import TranscriptionCancelled


MAX_PENDING_RECORDS = 8
MAX_ROUTING_RECORD_BYTES = HEADER_BYTES + MAX_ROUTING_BODY_BYTES

_INVALID = "Invalid OBS routing history"
_STORAGE_FAILED = "Private OBS routing history storage failed."
_QUEUE_FAILED = "Private OBS routing history could not keep up."
_CLEANUP_FAILED = "Private OBS routing history cleanup failed."

JournalFactory = Callable[[], BinaryIO]


class ObsRoutingStoreError(RuntimeError):
    """Private routing history cannot continue or be read safely."""


def _default_journal() -> BinaryIO:
    try:
        directory = require_local_filesystem(tempfile.gettempdir())
    except LocalFilesystemError:
        raise ObsRoutingStoreError(
            "Private OBS routing history needs a verified local temporary folder."
        ) from None
    try:
        return tempfile.TemporaryFile(
            mode="w+b",
            prefix="utterleaf-obs-routing-",
            buffering=0,
            dir=directory,
        )
    except OSError:
        raise ObsRoutingStoreError(
            "Private OBS routing history storage could not be created."
        ) from None


class ObsRoutingStore:
    """Write routing frames asynchronously and retain a disk-backed history."""

    def __init__(self, *, journal_factory: JournalFactory | None = None) -> None:
        if journal_factory is not None and not callable(journal_factory):
            raise TypeError("OBS routing history requires a journal factory")
        self._journal_factory = journal_factory or _default_journal
        self._condition = threading.Condition()
        self._file_lock = threading.Lock()
        self._pending: deque[bytes] = deque()
        self._finishing = False
        self._discard = threading.Event()
        self._failed = threading.Event()
        self._cleanup_failed = threading.Event()
        self._ready = threading.Event()
        self._closed = threading.Event()
        self._error: ObsRoutingStoreError | None = None
        self._journal: BinaryIO | None = None
        self._written_bytes = 0
        self._worker = threading.Thread(
            target=self._run,
            name="utterleaf-obs-routing-store",
            daemon=True,
        )
        try:
            self._worker.start()
        except BaseException:
            raise ObsRoutingStoreError(
                "Private OBS routing history storage could not start."
            ) from None

    def append(self, frame: RoutingFrame) -> bool:
        """Queue one exact frame without waiting or performing file I/O."""
        if type(frame) is not RoutingFrame:
            raise TypeError("OBS routing history requires an exact RoutingFrame")
        with self._condition:
            if self._rejecting_locked():
                return False
        try:
            record = encode_frame(frame, version=PROVENANCE_VERSION)
        except Exception:
            raise ObsRoutingStoreError(_INVALID) from None
        if len(record) > MAX_ROUTING_RECORD_BYTES:
            raise ObsRoutingStoreError(_INVALID)
        with self._condition:
            if self._rejecting_locked():
                return False
            if len(self._pending) >= MAX_PENDING_RECORDS:
                self._set_error_locked(_QUEUE_FAILED)
                self._finishing = True
                self._condition.notify_all()
                return False
            self._pending.append(record)
            self._condition.notify_all()
            return True

    def finish(self) -> None:
        """Request an asynchronous drain of every accepted record."""
        with self._condition:
            if not self._finishing and not self._discard.is_set():
                self._finishing = True
                self._condition.notify_all()

    @property
    def error(self) -> ObsRoutingStoreError | None:
        with self._condition:
            return self._error

    @property
    def failed(self) -> bool:
        return self._failed.is_set()

    @property
    def cleanup_failed(self) -> bool:
        return self._cleanup_failed.is_set()

    def wait_ready(self, cancelled: Callable[[], bool] = lambda: False) -> None:
        """Wait for a successful drain, failing on cancellation or storage loss."""
        while not self._ready.wait(0.05):
            if cancelled():
                raise TranscriptionCancelled("OBS routing history cancelled")
        if cancelled() or self._discard.is_set():
            raise TranscriptionCancelled("OBS routing history cancelled")
        error = self.error
        if error is not None:
            raise error

    def iter_observations(self) -> Iterator[RoutingFrame]:
        """Stream verified routing frames after a successful drain."""
        if not self._ready.is_set():
            raise ObsRoutingStoreError("Wait for OBS routing history before reading it")
        self._file_lock.acquire()
        try:
            with self._condition:
                if self._discard.is_set():
                    return
                if self._error is not None:
                    raise self._error
                journal = self._journal
                remaining = self._written_bytes
            if journal is None:
                raise ProtocolError(_INVALID)
            journal.seek(0)
            decoder = FrameDecoder(version=PROVENANCE_VERSION)
            while remaining:
                requested = min(remaining, MAX_ROUTING_RECORD_BYTES)
                data = journal.read(requested)
                if type(data) is not bytes or not data or len(data) > requested:
                    raise ProtocolError(_INVALID)
                remaining -= len(data)
                for frame in decoder.feed(data):
                    if type(frame) is not RoutingFrame:
                        raise ProtocolError(_INVALID)
                    if self._discard.is_set():
                        return
                    yield frame
            decoder.finish()
        except ObsRoutingStoreError:
            raise
        except Exception:
            self._record_error(_INVALID)
            raise ObsRoutingStoreError(_INVALID) from None
        finally:
            self._file_lock.release()

    def close(self) -> None:
        """Set nonblocking discard intent; the writer owns eventual file close."""
        self._discard.set()
        with self._condition:
            self._pending.clear()
            self._condition.notify_all()

    def wait_closed(self, timeout: float | None = None) -> bool:
        """Wait until the sole writer has completed its file-close attempt."""
        return self._closed.wait(timeout)

    def _rejecting_locked(self) -> bool:
        return (
            self._finishing
            or self._discard.is_set()
            or self._error is not None
            or self._ready.is_set()
        )

    def _set_error_locked(self, message: str) -> None:
        if self._error is None:
            self._error = ObsRoutingStoreError(message)
        self._failed.set()

    def _record_error(self, message: str) -> None:
        with self._condition:
            self._set_error_locked(message)
            self._condition.notify_all()

    def _run(self) -> None:
        journal: BinaryIO | None = None
        try:
            try:
                journal = self._journal_factory()
                if not all(
                    callable(getattr(journal, operation, None))
                    for operation in ("close", "read", "seek", "truncate", "write")
                ):
                    raise TypeError("Invalid routing history journal")
                with self._condition:
                    self._journal = journal
                self._drain(journal)
            except BaseException:
                self._record_error(_STORAGE_FAILED)
                with self._condition:
                    self._pending.clear()
        finally:
            self._ready.set()
            with self._condition:
                while not self._discard.is_set():
                    self._condition.wait()
            if journal is not None:
                try:
                    with self._file_lock:
                        journal.close()
                except BaseException:
                    with self._condition:
                        self._error = ObsRoutingStoreError(_CLEANUP_FAILED)
                        self._failed.set()
                        self._cleanup_failed.set()
                        self._condition.notify_all()
            self._closed.set()

    def _drain(self, journal: BinaryIO) -> None:
        while True:
            with self._condition:
                while (
                    not self._pending
                    and not self._finishing
                    and not self._discard.is_set()
                ):
                    self._condition.wait()
                if self._discard.is_set():
                    self._pending.clear()
                    return
                if self._pending:
                    record = self._pending.popleft()
                else:
                    return
            try:
                self._write_record(journal, record)
            except BaseException:
                self._record_error(_STORAGE_FAILED)
                with self._condition:
                    self._pending.clear()
                return

    def _write_record(self, journal: BinaryIO, record: bytes) -> None:
        with self._condition:
            start = self._written_bytes
        with self._file_lock:
            try:
                journal.seek(start)
                view = memoryview(record)
                written = 0
                while written < len(view):
                    count = journal.write(view[written:])
                    if (
                        type(count) is not int
                        or count <= 0
                        or count > len(view) - written
                    ):
                        raise OSError("OBS routing history write made no progress")
                    written += count
            except BaseException:
                try:
                    journal.seek(start)
                    journal.truncate(start)
                except Exception:
                    pass
                raise
        with self._condition:
            self._written_bytes = start + len(record)


__all__ = [
    "MAX_PENDING_RECORDS",
    "MAX_ROUTING_RECORD_BYTES",
    "ObsRoutingStore",
    "ObsRoutingStoreError",
]
