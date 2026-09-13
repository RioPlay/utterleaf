"""Bounded private storage for original decoded-frame timing."""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
import hashlib
import shutil
import struct
import tempfile
from typing import BinaryIO, Callable, Iterator

from utterleaf.file_frame_metadata import DecodedAudioFrame
from utterleaf.local_filesystem import LocalFilesystemError, require_local_filesystem


MIN_FREE_BYTES = 256 * 1024 * 1024
RECORD = struct.Struct("!qQB")
MAX_BUFFER_BYTES = (64 * 1024 // RECORD.size) * RECORD.size  # 65,535 bytes.
MAX_JOURNAL_BYTES = 256 * 1024 * 1024

_INT64_MIN = -(2**63)
_INT64_MAX = 2**63 - 1
_UINT64_MAX = 2**64 - 1
_SAMPLE_FORMATS = frozenset({
    "u8", "u8p", "s16", "s16p", "s32", "s32p", "s64", "s64p",
    "flt", "fltp", "dbl", "dblp",
})
_INVALID = "Invalid decoded-frame timing journal."
_STORAGE = "Private decoded-frame timing storage failed."
_LIMIT = "Decoded-frame timing exceeds the private journal storage limit."
_LOCAL = "Private decoded-frame timing needs a verified local temporary folder."

JournalFactory = Callable[[], BinaryIO]


class FileFrameJournalError(RuntimeError):
    """Decoded-frame timing cannot continue or be read safely."""


@dataclass(frozen=True)
class FrameTimingEntry:
    pts: int
    nb_samples: int
    run_start: bool


def _exact_int(value: object, lower: int, upper: int) -> bool:
    return type(value) is int and lower <= value <= upper


def _bounded_fraction(value: object, *, positive: bool = False) -> bool:
    if type(value) is not Fraction:
        return False
    if positive and value <= 0:
        return False
    return (
        _INT64_MIN <= value.numerator <= _INT64_MAX
        and 1 <= value.denominator <= _INT64_MAX
    )


def _default_journal(directory) -> BinaryIO:
    try:
        return tempfile.TemporaryFile(
            mode="w+b",
            prefix="utterleaf-frame-timing-",
            buffering=0,
            dir=directory,
        )
    except OSError:
        raise FileFrameJournalError(_STORAGE) from None


class FrameTimingJournal:
    """Store validated frame timing using at most 65,535 buffered record bytes.

    One worker owns the journal. ``seal`` is called only after the producing
    decoder reaches a successful EOF; partial or failed process output must be
    closed instead. A sealed in-process SHA-256 detects ordinary later byte
    corruption; it is not authentication against modification by this process.
    Iterated entries remain provisional until EOF completes digest validation.
    """

    def __init__(
        self,
        *,
        sample_rate: int,
        time_base: Fraction,
        origin: Fraction,
        stream_index: int,
        journal_factory: JournalFactory | None = None,
    ) -> None:
        if (
            not _exact_int(sample_rate, 1, 384000)
            or not _bounded_fraction(time_base, positive=True)
            or time_base > Fraction(1, 1000)
            or not _bounded_fraction(origin)
            or not _exact_int(stream_index, 0, _INT64_MAX)
        ):
            raise ValueError(_INVALID)
        if journal_factory is not None and not callable(journal_factory):
            raise TypeError(_INVALID)

        self._sample_rate = sample_rate
        self._time_base = time_base
        self._origin = origin
        self._stream_index = stream_index
        self._buffer = bytearray()
        self._frame_count = 0
        self._total_samples = 0
        self._signature: tuple[str, int, str] | None = None
        self._run_pts: int | None = None
        self._run_samples = 0
        self._write_hash = hashlib.sha256()
        self._sealed_digest: bytes | None = None
        self._state = "open"
        try:
            self._directory = require_local_filesystem(tempfile.gettempdir())
        except LocalFilesystemError:
            raise FileFrameJournalError(_LOCAL) from None
        try:
            if shutil.disk_usage(self._directory).free < MIN_FREE_BYTES:
                raise FileFrameJournalError(_STORAGE)
        except OSError:
            raise FileFrameJournalError(_STORAGE) from None
        try:
            self._file = (
                journal_factory() if journal_factory is not None
                else _default_journal(self._directory)
            )
        except FileFrameJournalError:
            raise
        except Exception:
            raise FileFrameJournalError(_STORAGE) from None

    @property
    def frame_count(self) -> int:
        return self._frame_count

    @property
    def total_samples(self) -> int:
        return self._total_samples

    @property
    def signature(self) -> tuple[str, int, str] | None:
        return self._signature

    def append(self, frame: DecodedAudioFrame) -> None:
        if self._state != "open":
            self._fail(_INVALID)
        try:
            self._validate_frame(frame)
            if self._frame_count >= MAX_JOURNAL_BYTES // RECORD.size:
                raise FileFrameJournalError(_LIMIT)
            run_start = self._classify(frame.pts, frame.nb_samples)
            if self._frame_count == _UINT64_MAX:
                raise FileFrameJournalError(_INVALID)
            if frame.nb_samples > _UINT64_MAX - self._total_samples:
                raise FileFrameJournalError(_INVALID)
            self._buffer.extend(RECORD.pack(frame.pts, frame.nb_samples, run_start))
            self._frame_count += 1
            self._total_samples += frame.nb_samples
            if self._signature is None:
                self._signature = (frame.sample_fmt, frame.channels, frame.channel_layout)
            if len(self._buffer) == MAX_BUFFER_BYTES:
                self._write_buffer()
        except FileFrameJournalError:
            self._poison()
            raise
        except Exception:
            self._poison()
            raise FileFrameJournalError(_STORAGE) from None

    def seal(self) -> None:
        if self._state != "open" or self._frame_count == 0:
            self._fail(_INVALID)
        try:
            self._write_buffer()
            self._file.flush()
            self._sealed_digest = self._write_hash.digest()
            self._state = "sealed"
        except FileFrameJournalError:
            self._poison()
            raise
        except Exception:
            self._poison()
            raise FileFrameJournalError(_STORAGE) from None

    def entries(self) -> Iterator[FrameTimingEntry]:
        """Replay provisional entries; the owner must always close the journal.

        This includes early iterator exit, normally by owning the journal with
        its context manager. Integrity is established only when iteration
        reaches EOF.
        """
        if self._state != "sealed":
            self._fail(_INVALID)
        expected_bytes = self._frame_count * RECORD.size
        try:
            self._file.seek(0, 2)
            if self._file.tell() != expected_bytes:
                raise FileFrameJournalError(_INVALID)
            self._file.seek(0)
        except FileFrameJournalError:
            self._poison()
            raise
        except Exception:
            self._poison()
            raise FileFrameJournalError(_STORAGE) from None
        return self._iter_entries(expected_bytes)

    def close(self) -> None:
        if self._state == "closed":
            return
        self._state = "closed"
        self._buffer.clear()
        handle, self._file = getattr(self, "_file", None), None
        if handle is not None:
            try:
                handle.close()
            except Exception:
                raise FileFrameJournalError(_STORAGE) from None

    def __enter__(self) -> "FrameTimingJournal":
        return self

    def __exit__(self, _exc_type, _exc, _traceback) -> None:
        self.close()

    def _validate_frame(self, frame: DecodedAudioFrame) -> None:
        if type(frame) is not DecodedAudioFrame:
            raise FileFrameJournalError(_INVALID)
        if not _exact_int(frame.stream_index, 0, _INT64_MAX) or frame.stream_index != self._stream_index:
            raise FileFrameJournalError(_INVALID)
        if not _exact_int(frame.pts, _INT64_MIN, _INT64_MAX):
            raise FileFrameJournalError(_INVALID)
        if type(frame.sample_fmt) is not str or frame.sample_fmt not in _SAMPLE_FORMATS:
            raise FileFrameJournalError(_INVALID)
        if not _exact_int(frame.nb_samples, 1, 60 * self._sample_rate):
            raise FileFrameJournalError(_INVALID)
        if not _exact_int(frame.channels, 1, 32):
            raise FileFrameJournalError(_INVALID)
        layout = frame.channel_layout
        if (
            type(layout) is not str
            or len(layout) > 128
            or not layout.strip()
            or any(marker in layout for marker in ("=", "\\", "|"))
            or any(not 0x20 <= ord(character) <= 0x7E for character in layout)
        ):
            raise FileFrameJournalError(_INVALID)
        signature = (frame.sample_fmt, frame.channels, layout)
        if self._signature is not None and signature != self._signature:
            raise FileFrameJournalError(_INVALID)

    def _classify(self, pts: int, nb_samples: int) -> bool:
        timestamp = pts * self._time_base
        if self._run_pts is None:
            if timestamp < self._origin:
                raise FileFrameJournalError(_INVALID)
            run_start = True
            self._run_pts = pts
            self._run_samples = 0
        else:
            expected = self._run_pts * self._time_base + Fraction(
                self._run_samples, self._sample_rate
            )
            delta = timestamp - expected
            if delta <= -self._time_base:
                raise FileFrameJournalError(_INVALID)
            run_start = delta >= self._time_base
            if run_start:
                self._run_pts = pts
                self._run_samples = 0
        if nb_samples > _UINT64_MAX - self._run_samples:
            raise FileFrameJournalError(_INVALID)
        self._run_samples += nb_samples
        return run_start

    def _write_buffer(self) -> None:
        if not self._buffer:
            return
        try:
            if shutil.disk_usage(self._directory).free < MIN_FREE_BYTES + len(self._buffer):
                raise FileFrameJournalError(_STORAGE)
            # The immutable copy is also bounded by MAX_BUFFER_BYTES and avoids
            # leaving an exported bytearray view alive in a failing writer.
            data = bytes(self._buffer)
            written = 0
            while written < len(data):
                count = self._file.write(data[written:])
                if type(count) is not int or count <= 0 or count > len(data) - written:
                    raise FileFrameJournalError(_STORAGE)
                written += count
            self._write_hash.update(data)
            self._buffer.clear()
        except FileFrameJournalError:
            raise
        except Exception:
            raise FileFrameJournalError(_STORAGE) from None

    def _iter_entries(self, remaining: int) -> Iterator[FrameTimingEntry]:
        frame_count = 0
        total_samples = 0
        run_pts: int | None = None
        run_samples = 0
        replay_hash = hashlib.sha256()
        try:
            while remaining:
                wanted = min(MAX_BUFFER_BYTES, remaining)
                chunk = bytearray()
                while len(chunk) < wanted:
                    part = self._file.read(wanted - len(chunk))
                    if not isinstance(part, bytes) or not part:
                        raise FileFrameJournalError(_INVALID)
                    chunk.extend(part)
                replay_hash.update(chunk)
                remaining -= wanted
                for pts, nb_samples, flag in RECORD.iter_unpack(chunk):
                    if flag not in (0, 1) or not 1 <= nb_samples <= 60 * self._sample_rate:
                        raise FileFrameJournalError(_INVALID)
                    timestamp = pts * self._time_base
                    if run_pts is None:
                        if timestamp < self._origin:
                            raise FileFrameJournalError(_INVALID)
                        expected_start = True
                        run_pts = pts
                        run_samples = 0
                    else:
                        expected = run_pts * self._time_base + Fraction(
                            run_samples, self._sample_rate
                        )
                        delta = timestamp - expected
                        if delta <= -self._time_base:
                            raise FileFrameJournalError(_INVALID)
                        expected_start = delta >= self._time_base
                        if expected_start:
                            run_pts = pts
                            run_samples = 0
                    if bool(flag) is not expected_start:
                        raise FileFrameJournalError(_INVALID)
                    if nb_samples > _UINT64_MAX - run_samples:
                        raise FileFrameJournalError(_INVALID)
                    if nb_samples > _UINT64_MAX - total_samples:
                        raise FileFrameJournalError(_INVALID)
                    run_samples += nb_samples
                    total_samples += nb_samples
                    frame_count += 1
                    yield FrameTimingEntry(pts, nb_samples, expected_start)
            if (
                frame_count != self._frame_count
                or total_samples != self._total_samples
                or self._sealed_digest is None
                or replay_hash.digest() != self._sealed_digest
            ):
                raise FileFrameJournalError(_INVALID)
        except FileFrameJournalError:
            self._poison()
            raise
        except Exception:
            self._poison()
            raise FileFrameJournalError(_STORAGE) from None

    def _fail(self, message: str) -> None:
        self._poison()
        raise FileFrameJournalError(message)

    def _poison(self) -> None:
        if self._state == "closed":
            return
        self._state = "poisoned"
        self._buffer.clear()
        handle, self._file = getattr(self, "_file", None), None
        if handle is not None:
            try:
                handle.close()
            except Exception:
                pass


__all__ = [
    "FileFrameJournalError",
    "FrameTimingEntry",
    "FrameTimingJournal",
    "MAX_BUFFER_BYTES",
    "MAX_JOURNAL_BYTES",
    "MIN_FREE_BYTES",
]
