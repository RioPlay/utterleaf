"""Single-use, explicitly armed OBS capture receiver.

The caller must authenticate the transport before creating this receiver and must
deliver a post-arm streaming-start event before its StartFrame. Session IDs are
routing identifiers, not credentials. Nothing here connects to OBS, opens a
microphone, installs a plugin, recognizes speech, or exports a result.

Call from one serialized worker, not an OBS audio callback or the UI thread.
The first audio gap stops this capture and retains only its contiguous prefix.
Native transport, live recognition, and the visible controller remain separate.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

import numpy as np

from utterleaf.capture_store import CaptureStore
from utterleaf.obs_protocol import AudioFrame, EndFrame, EndReason, GapFrame, StartFrame


class ObsSessionError(RuntimeError):
    """The session cannot safely accept more audio."""


@dataclass(frozen=True)
class CapturedTrack:
    bus: int
    first_timestamp_ns: int | None
    received_frames: int
    last_sequence: int | None
    store: CaptureStore = field(repr=False, compare=False)


class ObsCaptureResult:
    """Owned temporary stores; wait before reading, then close on every exit.

    Timeline offsets stay in integer nanoseconds against ``origin_ns``. A track
    that starts late is not silently moved to zero. No output is automatically
    exported, and an incomplete result must be presented as recovered audio.
    """

    def __init__(self, tracks: tuple[CapturedTrack, ...], *, primary_bus: int | None,
                 origin_ns: int | None, clean_end: bool, reason: str):
        self.tracks = tracks
        self.primary_bus = primary_bus
        self.origin_ns = origin_ns
        self._clean_end = clean_end
        self._reason = reason
        self._ready = False
        self.closed = False

    @property
    def complete(self) -> bool:
        return (not self.closed and self._ready and self._clean_end and bool(self.tracks)
                and all(track.received_frames > 0 and track.store.error is None
                        for track in self.tracks))

    @property
    def reason(self) -> str:
        if any(track.store.error for track in self.tracks):
            return "OBS audio storage failed. Only the stored portion can be recovered."
        if self._clean_end and any(track.received_frames == 0 for track in self.tracks):
            return "An OBS audio track supplied no audio. Check the stream mix."
        return self._reason

    def wait_ready(self, cancelled: Callable[[], bool] = lambda: False) -> None:
        if self.closed:
            raise ObsSessionError("OBS capture was closed")
        try:
            for track in self.tracks:
                track.store.wait_ready(cancelled)
        except BaseException:
            self.close()
            raise
        self._ready = True

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        for track in self.tracks:
            track.store.close()


@dataclass
class _Track:
    store: CaptureStore = field(repr=False)
    first_timestamp_ns: int | None = None
    frames: int = 0
    next_sequence: int = 0


class ObsCaptureSession:
    """One manual arm followed by at most one streaming session.

    ``stream_active=False`` must come from the authenticated idle snapshot, not a
    default guess. Create a fresh receiver only after another deliberate arm.
    With ``primary_bus=None``, ``buses`` lists explicitly requested additional
    buses; the authenticated plugin identifies the actual primary in Start.
    ``take_result`` transfers all temporary-file ownership to its caller; otherwise
    ``cancel``/``close`` discard the stores. No implicit rearm exists.
    """

    def __init__(self, session_id: bytes, primary_bus: int | None = None,
                 buses: tuple[int, ...] = (), *,
                 stream_active: bool, store_factory=CaptureStore):
        if type(stream_active) is not bool or stream_active:
            raise ObsSessionError("Arm OBS transcription while the stream is stopped")
        if type(session_id) is not bytes or len(session_id) != 16:
            raise ValueError("Invalid OBS session identifier")
        if (type(buses) is not tuple or not 0 <= len(buses) <= 6
                or any(type(bus) is not int or not 0 <= bus < 6 for bus in buses)
                or buses != tuple(sorted(set(buses)))
                or (primary_bus is not None
                    and (type(primary_bus) is not int or primary_bus not in buses))):
            raise ValueError("Invalid OBS audio bus selection")
        self._session_id = session_id
        self.primary_bus = primary_bus
        self.buses = buses
        self._mask = sum(1 << bus for bus in buses)
        self._factory = store_factory
        self._tracks: dict[int, _Track] = {}
        self._started = False
        self._origin_ns: int | None = None
        self._sample_rate = 0
        self._clean_end = False
        self._taken = False
        self.state = "armed"
        self.reason = "Waiting for the next OBS stream to start."

    def notify_stream_started(self, session_id: bytes) -> None:
        self._check_identity(session_id)
        if self.state != "armed" or self._started:
            self._fail("OBS stream start was stale or repeated")
        self._started = True

    def accept(self, frame: StartFrame | AudioFrame | GapFrame | EndFrame) -> None:
        if type(frame) not in (StartFrame, AudioFrame, GapFrame, EndFrame):
            self._fail("Unexpected OBS audio message")
        self._check_identity(frame.session_id)
        if self.state not in {"armed", "active"}:
            raise ObsSessionError("OBS capture no longer accepts audio")
        if isinstance(frame, StartFrame):
            self._start(frame)
            return
        if self.state != "active":
            self._fail("OBS audio arrived before the armed stream started")
        if isinstance(frame, AudioFrame):
            self._audio(frame)
        elif isinstance(frame, GapFrame):
            self._fail("OBS audio was lost. Capture stopped; only the prefix can be recovered.")
        else:
            self._end(frame)

    def _check_identity(self, session_id: bytes) -> None:
        if type(session_id) is not bytes or session_id != self._session_id:
            self._fail("OBS audio session changed or was stale")

    def _start(self, frame: StartFrame) -> None:
        if self.state != "armed" or not self._started:
            self._fail("OBS audio start requires a new, explicitly armed stream")
        expected_mask = self._mask | (1 << frame.primary_bus) if self.primary_bus is None else self._mask
        if ((self.primary_bus is not None and frame.primary_bus != self.primary_bus)
                or frame.bus_mask != expected_mask):
            self._fail("OBS supplied a different audio mix than the armed selection")
        self.primary_bus = frame.primary_bus
        self.buses = tuple(bus for bus in range(6) if expected_mask & (1 << bus))
        try:
            for bus in self.buses:
                self._tracks[bus] = _Track(self._factory(frame.sample_rate))
        except BaseException as exc:
            self.cancel()
            if isinstance(exc, Exception):
                self.state = "incomplete"
                self.reason = "OBS temporary audio storage could not start. Check local storage."
                raise ObsSessionError(self.reason) from None
            raise
        self._sample_rate = frame.sample_rate
        self._origin_ns = frame.origin_ns
        self.state = "active"
        self.reason = "Receiving the armed OBS stream."

    def _audio(self, frame: AudioFrame) -> None:
        if frame.bus not in self._tracks:
            self._fail("OBS supplied an audio bus that was not selected")
        track = self._tracks[frame.bus]
        if frame.sequence != track.next_sequence:
            self._fail("OBS audio order changed. Capture stopped; only the prefix can be recovered.")
        if frame.timestamp_ns < self._origin_ns:
            self._fail("OBS audio arrived before its declared timeline")
        if track.first_timestamp_ns is not None:
            # OBS floors cumulative frame times to integer nanoseconds. Allow one
            # nanosecond of rounding, without accumulating it once per block.
            difference = ((frame.timestamp_ns - track.first_timestamp_ns) * self._sample_rate
                          - track.frames * 1_000_000_000)
            if abs(difference) > self._sample_rate:
                self._fail("OBS audio timing changed. Capture stopped; only the prefix can be recovered.")
        if any(item.store.error for item in self._tracks.values()):
            self._fail("OBS audio storage failed. Only the stored portion can be recovered.")
        stereo = np.frombuffer(frame.pcm, dtype="<f4").reshape(frame.frames, 2)
        # Float64 accumulation avoids overflow when two finite float32 maxima
        # are combined. The bounded block is copied by CaptureStore.append.
        mono = stereo.mean(axis=1, dtype=np.float64).astype(np.float32)
        try:
            accepted = track.store.append(mono)
        except Exception:
            self._fail("OBS audio storage failed. Only the stored portion can be recovered.")
        if not accepted:
            self._fail("OBS audio storage could not keep up. Only the stored portion can be recovered.")
        if track.first_timestamp_ns is None:
            track.first_timestamp_ns = frame.timestamp_ns
        track.frames += frame.frames
        track.next_sequence += 1

    def _end(self, frame: EndFrame) -> None:
        expected = tuple((bus, item.next_sequence - 1 if item.next_sequence else None)
                         for bus, item in self._tracks.items())
        if frame.last_sequences != expected:
            self._fail("OBS ended before all declared audio arrived. Only the prefix can be recovered.")
        self._clean_end = frame.reason in {EndReason.STREAM_STOPPED, EndReason.DISARMED}
        self.state = "finished" if self._clean_end else "incomplete"
        self.reason = ("OBS capture finished." if self._clean_end
                       else "OBS capture was interrupted. Only the prefix can be recovered.")
        for track in self._tracks.values():
            track.store.finish()

    def _fail(self, reason: str) -> None:
        # A late callback cannot reopen or mutate an already transferred result.
        if self.state in {"armed", "active"}:
            self.state = "incomplete"
            self.reason = reason
            self._clean_end = False
            for track in self._tracks.values():
                track.store.finish()
        raise ObsSessionError(reason)

    def connection_lost(self) -> None:
        """Signal loss of the authenticated audio channel, not control-only lag."""
        self._fail("OBS audio connection ended unexpectedly. Only the prefix can be recovered.")

    def take_result(self) -> ObsCaptureResult:
        if self.state not in {"finished", "incomplete"} or self._taken:
            raise ObsSessionError("OBS capture has no transferable result")
        tracks = tuple(CapturedTrack(bus, item.first_timestamp_ns, item.frames,
                                     item.next_sequence - 1 if item.next_sequence else None,
                                     item.store) for bus, item in self._tracks.items())
        result = ObsCaptureResult(tracks, primary_bus=self.primary_bus, origin_ns=self._origin_ns,
                                  clean_end=self._clean_end, reason=self.reason)
        self._tracks.clear()
        self._taken = True
        return result

    def cancel(self) -> None:
        """Discard this receiver's audio; a transferred result has its own owner."""
        for track in self._tracks.values():
            track.store.close()
        self._tracks.clear()
        self._session_id = b""
        self._clean_end = False
        self.state = "cancelled"
        self.reason = "OBS capture cancelled."

    close = cancel
