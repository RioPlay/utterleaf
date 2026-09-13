"""Bounded, local live recognition for an explicitly armed OBS capture.

One worker polls committed CaptureStore windows across selected OBS buses. Audio,
recognized text and credentials are never sent to a network service or exported
automatically. Full segment output stays in a private temporary journal until the
owner explicitly reads or closes it; UI snapshots retain only a bounded preview.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
import json
import math
import struct
import tempfile
import threading
import time
from typing import BinaryIO, Callable, Iterator

import numpy as np

from utterleaf.capture_store import CaptureReadState
from utterleaf.config import Config
from utterleaf.local_filesystem import LocalFilesystemError, require_local_filesystem
from utterleaf.obs_protocol import RoutingFrame
from utterleaf.obs_routing_store import ObsRoutingStore, ObsRoutingStoreError
from utterleaf.obs_session import CapturedTrack, ObsCaptureResult
from utterleaf.transcript import Transcript, TranscriptionCancelled


MAX_TRACKS = 6
PREVIEW_CHARS = 4000
MAX_SEGMENTS_PER_WINDOW = 2048
MAX_SEGMENT_TEXT_BYTES = 16 * 1024
MAX_WINDOW_TEXT_BYTES = 64 * 1024
MAX_JOURNAL_RECORD_BYTES = 32 * 1024
POLL_SECONDS = 0.05
_LENGTH = struct.Struct("<I")


class ObsTranscriptionError(RuntimeError):
    """The live transcript cannot continue or be read safely."""


class ObsTranscriptionState(str, Enum):
    WAITING = "waiting"
    RUNNING = "running"
    FINALIZING = "finalizing"
    COMPLETE = "complete"
    INCOMPLETE = "incomplete"
    CANCELLED = "cancelled"
    FAILED = "failed"
    EMPTY = "empty"


@dataclass(frozen=True)
class ObsTranscriptionSnapshot:
    state: ObsTranscriptionState
    message: str
    preview: str
    track_count: int
    completed_tracks: int
    incomplete: bool


@dataclass(frozen=True)
class ObsTranscriptSegment:
    """One model segment on the shared OBS timeline, identified only by bus."""

    bus: int
    start: float
    end: float
    text: str


@dataclass
class _TrackCursor:
    track: CapturedTrack
    origin_ns: int
    sample_rate: float
    primary_bus: int
    source_offset: int = 0
    done: bool = False


Recognizer = Callable[..., Transcript]
RecognizerFactory = Callable[[Config], Recognizer]
JournalFactory = Callable[[], BinaryIO]


def _default_journal() -> BinaryIO:
    try:
        directory = require_local_filesystem(tempfile.gettempdir())
    except LocalFilesystemError:
        raise ObsTranscriptionError(
            "Private OBS transcript storage needs a verified local temporary folder."
        ) from None
    try:
        return tempfile.TemporaryFile(
            mode="w+b", prefix="utterleaf-obs-transcript-", buffering=0, dir=directory
        )
    except OSError as exc:
        raise ObsTranscriptionError("Private OBS transcript storage could not be created.") from exc


def _default_recognizer(config: Config) -> Recognizer:
    from utterleaf.transcribe import CTranslateEngine, load_model

    engine = load_model(config)
    if not isinstance(engine, CTranslateEngine):
        raise ObsTranscriptionError(
            "Timestamped local OBS recognition requires a CPU or CUDA model in Settings."
        )

    def recognize(audio, cfg, *, cancel):
        return engine.transcribe_segments(
            audio, cfg, cancel=cancel,
            max_segments=MAX_SEGMENTS_PER_WINDOW,
            max_segment_text_bytes=MAX_SEGMENT_TEXT_BYTES,
            max_total_text_bytes=MAX_WINDOW_TEXT_BYTES,
        )

    return recognize


class ObsTranscriptionCoordinator:
    """Recognize live committed OBS windows with one round-robin ASR worker."""

    def __init__(self, config: Config, *, recognizer_factory: RecognizerFactory | None = None,
                 journal_factory: JournalFactory | None = None):
        if not isinstance(config, Config):
            raise TypeError("OBS transcription requires a Config snapshot")
        self._config = replace(config, allow_network=False)
        self._recognizer_factory = recognizer_factory or _default_recognizer
        self._journal_factory = journal_factory or _default_journal
        self._condition = threading.Condition()
        self._journal_lock = threading.Lock()
        self._cancel = threading.Event()
        self._discard_requested = threading.Event()
        self._failed = threading.Event()
        self._done = threading.Event()
        self._cleanup_done = threading.Event()
        self._tracks: dict[int, _TrackCursor] = {}
        self._result: ObsCaptureResult | None = None
        self._borrowed_routing_history: ObsRoutingStore | None = None
        self._routing_history: ObsRoutingStore | None = None
        self._routing_error: ObsRoutingStoreError | None = None
        self._routing_cleanup_error: ObsRoutingStoreError | None = None
        self._origin_ns: int | None = None
        self._sample_rate: float | None = None
        self._primary_bus: int | None = None
        self._recognizer: Recognizer | None = None
        self._journal: BinaryIO | None = None
        self._journal_size = 0
        self._preview = ""
        self._track_count = 0
        self._completed_tracks = 0
        self._incomplete = False
        self._fatal = False
        self._closed = False
        self._cleanup_thread: threading.Thread | None = None
        self._cleanup_error: BaseException | None = None
        self._state = ObsTranscriptionState.WAITING
        self._message = "Waiting for OBS audio."
        self._cursor = 0
        self._worker = threading.Thread(
            target=self._run, name="utterleaf-obs-transcription", daemon=True
        )
        try:
            self._worker.start()
        except BaseException:
            self._closed = True
            raise

    def add_track(self, track: CapturedTrack, *, origin_ns: int, sample_rate: int,
                  primary_bus: int) -> None:
        """Register one borrowed live store without running model or disk work."""
        self._validate_track(track, origin_ns, sample_rate, primary_bus)
        with self._condition:
            if self._cancel.is_set() or self._closed or self._result is not None:
                raise ObsTranscriptionError("OBS transcription no longer accepts tracks")
            if track.bus in self._tracks:
                raise ObsTranscriptionError("OBS audio bus was registered more than once")
            if len(self._tracks) >= MAX_TRACKS:
                raise ObsTranscriptionError("OBS transcription supports at most six buses")
            if self._origin_ns is None:
                self._origin_ns = origin_ns
                self._sample_rate = float(sample_rate)
                self._primary_bus = primary_bus
            elif (origin_ns != self._origin_ns or float(sample_rate) != self._sample_rate
                  or primary_bus != self._primary_bus):
                raise ObsTranscriptionError("OBS tracks do not share one capture timeline")
            self._tracks[track.bus] = _TrackCursor(
                track, origin_ns, float(sample_rate), primary_bus
            )
            self._track_count = len(self._tracks)
            if not self._fatal:
                self._state = ObsTranscriptionState.RUNNING
                self._message = "Transcribing OBS audio locally."
            self._condition.notify_all()

    def attach_routing_history(self, history: ObsRoutingStore) -> None:
        """Borrow live failure state until the final capture transfers ownership."""
        if type(history) is not ObsRoutingStore:
            raise TypeError("OBS transcription requires an exact routing history")
        with self._condition:
            if self._cancel.is_set() or self._closed or self._result is not None:
                raise ObsTranscriptionError("OBS transcription cannot attach routing history")
            if self._borrowed_routing_history is not None:
                if self._borrowed_routing_history is history:
                    return
                raise ObsTranscriptionError("OBS transcription already has routing history")
            self._borrowed_routing_history = history
            self._condition.notify_all()

    def finish_capture(self, result: ObsCaptureResult) -> None:
        """Accept ownership of the final capture after validating live registrations."""
        if not isinstance(result, ObsCaptureResult):
            raise TypeError("finish_capture requires an ObsCaptureResult")
        with self._condition:
            if self._cancel.is_set() or self._closed or self._result is not None:
                raise ObsTranscriptionError("OBS transcription cannot accept this result")
            self._validate_result_locked(result)
            try:
                history = result.take_routing_history()
            except Exception:
                raise ObsTranscriptionError(
                    "OBS capture routing history could not be transferred"
                ) from None
            self._routing_history = history
            self._borrowed_routing_history = None
            self._result = result
            self._track_count = len(result.tracks)
            if not self._fatal:
                self._state = ObsTranscriptionState.FINALIZING
                self._message = "Finishing OBS transcription."
            self._condition.notify_all()

    def cancel(self) -> None:
        """Set discard intent; borrowed audio and routing stay with their owner."""
        with self._condition:
            self._cancel.set()
            self._discard_requested.set()
            self._preview = ""
            history = self._routing_history
            if self._cleanup_error is None and self._routing_error is None:
                self._state = ObsTranscriptionState.CANCELLED
                self._message = "OBS transcription cancelled."
            self._condition.notify_all()
        if history is not None:
            history.close()
        self._request_cleanup()

    def wait(self, timeout: float | None = None) -> bool:
        deadline = None if timeout is None else time.monotonic() + max(0.0, timeout)
        if not self._done.wait(timeout):
            return False
        if not self._discard_requested.is_set():
            return True
        remaining = None if deadline is None else max(0.0, deadline - time.monotonic())
        if not self._cleanup_done.wait(remaining):
            return False
        with self._condition:
            history = self._routing_history or self._borrowed_routing_history
        if history is not None:
            remaining = None if deadline is None else max(0.0, deadline - time.monotonic())
            if not history.wait_closed(remaining):
                return False
            self._record_routing_failure(history, cleanup=history.cleanup_failed)
        return True

    @property
    def failed(self) -> bool:
        """Cheap failure signal for control and pipe cancellation predicates."""
        if self._failed.is_set():
            return True
        with self._condition:
            history = self._routing_history or self._borrowed_routing_history
        return history is not None and history.failed

    def snapshot(self) -> ObsTranscriptionSnapshot:
        self._refresh_routing_failure()
        with self._condition:
            return ObsTranscriptionSnapshot(
                state=self._state,
                message=self._message,
                preview=self._preview,
                track_count=self._track_count,
                completed_tracks=self._completed_tracks,
                incomplete=self._incomplete,
            )

    def iter_routing_observations(self) -> Iterator[RoutingFrame]:
        """Stream the owned routing history after recognition completes."""
        if not self._done.is_set():
            raise ObsTranscriptionError(
                "Wait for OBS transcription before reading routing history"
            )
        if self._discard_requested.is_set():
            return
        with self._condition:
            history = self._routing_history
        if history is None:
            return
        try:
            yield from history.iter_observations()
        except ObsRoutingStoreError:
            self._record_routing_failure(history)
            raise ObsTranscriptionError("OBS routing history could not be read") from None

    def iter_segments(self) -> Iterator[ObsTranscriptSegment]:
        """Stream the private journal after recognition has stopped."""
        if not self._done.is_set():
            raise ObsTranscriptionError("Wait for OBS transcription before reading segments")
        self._journal_lock.acquire()
        try:
            if self._closed:
                raise ObsTranscriptionError("OBS transcript journal is closed")
            if self._discard_requested.is_set():
                return
            if self._journal is None:
                return
            self._journal.seek(0)
            remaining = self._journal_size
            while remaining:
                header = self._journal.read(_LENGTH.size)
                if len(header) != _LENGTH.size:
                    raise ObsTranscriptionError("OBS transcript journal is incomplete")
                size = _LENGTH.unpack(header)[0]
                remaining -= _LENGTH.size
                if not 0 < size <= MAX_JOURNAL_RECORD_BYTES or size > remaining:
                    raise ObsTranscriptionError("OBS transcript journal is invalid")
                payload = self._journal.read(size)
                if len(payload) != size:
                    raise ObsTranscriptionError("OBS transcript journal is incomplete")
                remaining -= size
                try:
                    item = json.loads(payload.decode("utf-8"))
                    segment = ObsTranscriptSegment(
                        bus=item["bus"], start=item["start"], end=item["end"], text=item["text"]
                    )
                    self._validate_journal_segment(segment)
                except (KeyError, TypeError, ValueError, UnicodeError, json.JSONDecodeError) as exc:
                    raise ObsTranscriptionError("OBS transcript journal is invalid") from exc
                if self._discard_requested.is_set():
                    return
                yield segment
        finally:
            self._journal_lock.release()

    def close(self, timeout: float | None = None) -> bool:
        """Cancel, wait when requested, and delete the private journal."""
        self.cancel()
        deadline = None if timeout is None else time.monotonic() + max(0.0, timeout)
        stopped = self.wait(timeout)
        if not stopped:
            return False
        remaining = None if deadline is None else max(0.0, deadline - time.monotonic())
        if not self._cleanup_done.wait(remaining):
            return False
        with self._condition:
            self._closed = True
            cleanup_error = self._cleanup_error
            routing_cleanup_error = self._routing_cleanup_error
        if cleanup_error is not None:
            raise ObsTranscriptionError(
                "Private OBS transcript storage could not be deleted"
            ) from cleanup_error
        if routing_cleanup_error is not None:
            raise ObsTranscriptionError(
                "Private OBS routing history could not be discarded"
            ) from None
        return True

    @staticmethod
    def _validate_track(track: CapturedTrack, origin_ns: int, sample_rate: int,
                        primary_bus: int) -> None:
        if not isinstance(track, CapturedTrack):
            raise TypeError("add_track requires a CapturedTrack")
        integers = (track.bus, origin_ns, sample_rate, primary_bus)
        if any(isinstance(value, bool) or not isinstance(value, int) for value in integers):
            raise ValueError("OBS track metadata must use integer clocks and buses")
        if not 0 <= track.bus < MAX_TRACKS or not 0 <= primary_bus < MAX_TRACKS:
            raise ValueError("OBS bus is outside the supported range")
        if (track.first_timestamp_ns is None
                or isinstance(track.first_timestamp_ns, bool)
                or not isinstance(track.first_timestamp_ns, int)
                or track.first_timestamp_ns < origin_ns):
            raise ValueError("OBS track needs a valid first timestamp on its capture timeline")
        if not 8000 <= sample_rate <= 192000 or track.received_frames <= 0:
            raise ValueError("OBS live track has invalid audio metadata")
        if float(track.store.sample_rate) != float(sample_rate):
            raise ValueError("OBS track sample rate does not match its store")

    def _validate_result_locked(self, result: ObsCaptureResult) -> None:
        if result.closed:
            raise ObsTranscriptionError("OBS capture result is already closed")
        if len(result.tracks) > MAX_TRACKS or len({track.bus for track in result.tracks}) != len(result.tracks):
            raise ObsTranscriptionError("OBS capture result has invalid buses")
        registered = set(self._tracks)
        positive = {track.bus for track in result.tracks if track.received_frames > 0}
        if positive != registered:
            raise ObsTranscriptionError("OBS capture result does not match its live tracks")
        for track in result.tracks:
            if track.bus not in range(MAX_TRACKS) or track.received_frames < 0:
                raise ObsTranscriptionError("OBS capture result has invalid track metadata")
            cursor = self._tracks.get(track.bus)
            if cursor is not None and (cursor.track.store is not track.store
                                       or cursor.track.first_timestamp_ns != track.first_timestamp_ns):
                raise ObsTranscriptionError("OBS capture result changed a live track")
        if registered and (result.origin_ns != self._origin_ns
                           or result.primary_bus != self._primary_bus):
            raise ObsTranscriptionError("OBS capture result changed its timeline")
        if not registered and result.tracks and any(track.received_frames > 0 for track in result.tracks):
            raise ObsTranscriptionError("OBS capture result skipped live track registration")
        if result.routing_history is not self._borrowed_routing_history:
            raise ObsTranscriptionError("OBS capture result changed its routing history")

    def _run(self) -> None:
        try:
            while True:
                with self._condition:
                    if self._cancel.is_set():
                        self._finish_cancelled_locked()
                        return
                    result = self._result
                    fatal = self._fatal
                    cursors = tuple(self._tracks.values())
                if fatal:
                    if result is not None:
                        result.close()
                        self._done.set()
                        return
                    with self._condition:
                        self._condition.wait(POLL_SECONDS)
                    continue

                worked = self._poll_round(cursors)
                with self._condition:
                    if self._cancel.is_set():
                        self._finish_cancelled_locked()
                        return
                    result = self._result
                    all_done = all(cursor.done for cursor in self._tracks.values())
                if result is not None and all_done:
                    self._finalize(result)
                    return
                if not worked:
                    with self._condition:
                        self._condition.wait(POLL_SECONDS)
        except TranscriptionCancelled:
            with self._condition:
                self._finish_cancelled_locked()
        except Exception:
            self._set_fatal("OBS transcription failed. No transcript was exported.")
            self._finish_after_failure()
        finally:
            if self._discard_requested.is_set():
                with self._condition:
                    history = self._routing_history
                if history is not None:
                    history.close()
                self._request_cleanup()

    def _poll_round(self, cursors: tuple[_TrackCursor, ...]) -> bool:
        if not cursors:
            return False
        count = len(cursors)
        for step in range(count):
            index = (self._cursor + step) % count
            cursor = cursors[index]
            if cursor.done:
                continue
            outcome = cursor.track.store.read_window(cursor.source_offset, self._cancel.is_set)
            if outcome.state is CaptureReadState.UNAVAILABLE:
                continue
            self._cursor = (index + 1) % count
            if outcome.state is CaptureReadState.READY:
                self._recognize_window(cursor, outcome)
                if self._cancel.is_set():
                    raise TranscriptionCancelled("OBS transcription cancelled")
                cursor.source_offset = outcome.next_source_offset
                return True
            cursor.done = True
            with self._condition:
                self._completed_tracks += 1
                if outcome.state is CaptureReadState.FAILED:
                    self._failed.set()
                    self._incomplete = True
                    self._message = outcome.error or "OBS audio storage failed; the prefix was retained."
            return True
        self._cursor = (self._cursor + 1) % count
        return False

    def _recognize_window(self, cursor: _TrackCursor, outcome) -> None:
        if self._recognizer is None:
            self._recognizer = self._recognizer_factory(self._config)
            if not callable(self._recognizer):
                raise ObsTranscriptionError("OBS recognizer factory returned an invalid recognizer")
        result = self._recognizer(outcome.audio, self._config, cancel=self._cancel)
        if self._cancel.is_set():
            raise TranscriptionCancelled("OBS transcription cancelled")
        segments = self._validate_window_result(cursor, outcome, result)
        self._publish(cursor.track.bus, segments)

    def _validate_window_result(self, cursor: _TrackCursor, outcome,
                                result: Transcript) -> tuple[ObsTranscriptSegment, ...]:
        if not isinstance(result, Transcript):
            raise ObsTranscriptionError("OBS recognizer returned an invalid transcript")
        if len(result.segments) > MAX_SEGMENTS_PER_WINDOW:
            raise ObsTranscriptionError("OBS recognizer returned too many segments")
        duration = outcome.source_samples / cursor.sample_rate
        window_start = ((cursor.track.first_timestamp_ns - cursor.origin_ns) / 1_000_000_000
                        + outcome.source_offset / cursor.sample_rate)
        total_bytes = 0
        checked = []
        for segment in result.segments:
            if not isinstance(segment.text, str):
                raise ObsTranscriptionError("OBS recognizer returned invalid text")
            if (len(segment.text) > MAX_SEGMENT_TEXT_BYTES
                    or len(segment.text) > MAX_WINDOW_TEXT_BYTES - total_bytes):
                raise ObsTranscriptionError("OBS recognizer returned oversized text")
            encoded = segment.text.encode("utf-8")
            total_bytes += len(encoded)
            if len(encoded) > MAX_SEGMENT_TEXT_BYTES or total_bytes > MAX_WINDOW_TEXT_BYTES:
                raise ObsTranscriptionError("OBS recognizer returned oversized text")
            if (not math.isfinite(segment.start) or not math.isfinite(segment.end)
                    or segment.start < 0 or segment.end < segment.start
                    or segment.start >= duration):
                raise ObsTranscriptionError("OBS recognizer returned timestamps outside the audio window")
            checked.append(ObsTranscriptSegment(
                cursor.track.bus,
                window_start + segment.start,
                window_start + min(segment.end, duration),
                segment.text,
            ))
        return tuple(checked)

    def _publish(self, bus: int, segments: tuple[ObsTranscriptSegment, ...]) -> None:
        if not segments:
            return
        records = []
        for segment in segments:
            payload = json.dumps(
                {"bus": segment.bus, "start": segment.start, "end": segment.end,
                 "text": segment.text},
                ensure_ascii=False, separators=(",", ":"), allow_nan=False,
            ).encode("utf-8")
            if len(payload) > MAX_JOURNAL_RECORD_BYTES:
                raise ObsTranscriptionError("OBS transcript journal record is too large")
            records.append(_LENGTH.pack(len(payload)) + payload)

        with self._journal_lock:
            if self._cancel.is_set():
                raise TranscriptionCancelled("OBS transcription cancelled")
            if self._journal is None:
                self._journal = self._journal_factory()
            start = self._journal_size
            try:
                self._journal.seek(start)
                for record in records:
                    self._write_all(record)
                end = self._journal.tell()
                with self._condition:
                    if self._cancel.is_set():
                        raise TranscriptionCancelled("OBS transcription cancelled")
                    additions = [" ".join(segment.text.split()) for segment in segments]
                    additions = [text for text in additions if text]
                    if additions:
                        line = f"Bus {bus}: " + " ".join(additions)
                        self._preview = (
                            self._preview + ("\n" if self._preview else "") + line
                        )[-PREVIEW_CHARS:]
                    self._journal_size = end
            except BaseException:
                try:
                    self._journal.seek(start)
                    self._journal.truncate(start)
                except Exception:
                    pass
                raise

    def _request_cleanup(self) -> None:
        with self._condition:
            if self._cleanup_thread is not None:
                return
            cleanup = threading.Thread(
                target=self._cleanup_journal,
                name="utterleaf-obs-transcript-cleanup",
                daemon=True,
            )
            self._cleanup_thread = cleanup
        try:
            cleanup.start()
        except BaseException as exc:
            self._record_cleanup_failure(exc)
            self._cleanup_done.set()

    def _cleanup_journal(self) -> None:
        try:
            with self._journal_lock:
                journal = self._journal
                if journal is not None:
                    journal.close()
                    self._journal = None
                    self._journal_size = 0
        except BaseException as exc:
            self._record_cleanup_failure(exc)
        finally:
            self._cleanup_done.set()

    def _record_cleanup_failure(self, exc: BaseException) -> None:
        with self._condition:
            if self._cleanup_error is None:
                self._cleanup_error = exc
            self._failed.set()
            self._preview = ""
            self._state = ObsTranscriptionState.FAILED
            self._message = "Private OBS transcript cleanup failed."
            self._condition.notify_all()

    def _refresh_routing_failure(self) -> None:
        with self._condition:
            history = self._routing_history or self._borrowed_routing_history
        if history is not None and history.error is not None:
            self._record_routing_failure(history)

    def _record_routing_failure(self, history: ObsRoutingStore, *, cleanup: bool = False) -> None:
        error = history.error
        if error is None:
            return
        with self._condition:
            if cleanup or self._routing_error is None:
                self._routing_error = error
            if cleanup:
                self._routing_cleanup_error = error
            self._failed.set()
            self._preview = ""
            self._state = ObsTranscriptionState.FAILED
            self._message = str(self._routing_error)
            self._condition.notify_all()

    def _write_all(self, data: bytes) -> None:
        view = memoryview(data)
        written = 0
        while written < len(view):
            count = self._journal.write(view[written:])
            if count is None or count <= 0:
                raise OSError("OBS transcript journal write made no progress")
            written += count

    @staticmethod
    def _validate_journal_segment(segment: ObsTranscriptSegment) -> None:
        if (isinstance(segment.bus, bool) or not isinstance(segment.bus, int)
                or not 0 <= segment.bus < MAX_TRACKS or not isinstance(segment.text, str)
                or not math.isfinite(segment.start) or not math.isfinite(segment.end)
                or segment.start < 0 or segment.end < segment.start
                or len(segment.text.encode("utf-8")) > MAX_SEGMENT_TEXT_BYTES):
            raise ValueError("Invalid journal segment")

    def _finalize(self, result: ObsCaptureResult) -> None:
        try:
            result.wait_ready(self._cancel.is_set)
            if self._cancel.is_set():
                raise TranscriptionCancelled("OBS transcription cancelled")
            empty = result.empty
            complete = result.complete
            reason = result.reason
        except BaseException:
            result.close()
            raise
        result.close()
        with self._condition:
            if self._cancel.is_set():
                self._finish_cancelled_locked()
                return
            if empty:
                self._state = ObsTranscriptionState.EMPTY
                self._message = "OBS transcription disarmed before audio began."
            elif self._incomplete or not complete:
                self._state = ObsTranscriptionState.INCOMPLETE
                self._message = reason
                self._incomplete = True
            else:
                self._state = ObsTranscriptionState.COMPLETE
                self._message = "OBS transcription complete."
            self._completed_tracks = self._track_count
            self._done.set()

    def _set_fatal(self, message: str) -> None:
        with self._condition:
            if self._cancel.is_set():
                return
            self._fatal = True
            self._failed.set()
            self._state = ObsTranscriptionState.FAILED
            self._message = message
            self._condition.notify_all()

    def _finish_after_failure(self) -> None:
        while True:
            with self._condition:
                if self._cancel.is_set():
                    self._finish_cancelled_locked()
                    return
                result = self._result
                if result is None:
                    self._condition.wait(POLL_SECONDS)
                    continue
            result.close()
            self._done.set()
            return

    def _finish_cancelled_locked(self) -> None:
        self._cancel.set()
        self._discard_requested.set()
        self._preview = ""
        result = self._result
        if result is not None:
            result.close()
        if self._cleanup_error is None and self._routing_error is None:
            self._state = ObsTranscriptionState.CANCELLED
            self._message = "OBS transcription cancelled."
        self._done.set()
