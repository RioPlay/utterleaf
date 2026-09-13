from fractions import Fraction
import io
import struct
from types import SimpleNamespace

import pytest

from utterleaf.file_frame_metadata import DecodedAudioFrame
import utterleaf.file_frame_journal as journal_module
from utterleaf.file_frame_journal import (
    FileFrameJournalError,
    FrameTimingEntry,
    FrameTimingJournal,
    MAX_BUFFER_BYTES,
    MAX_JOURNAL_BYTES,
    MIN_FREE_BYTES,
    RECORD,
)
from utterleaf.local_filesystem import LocalFilesystemError


@pytest.fixture
def local_storage(monkeypatch, tmp_path):
    monkeypatch.setattr(journal_module.tempfile, "gettempdir", lambda: str(tmp_path))
    monkeypatch.setattr(journal_module, "require_local_filesystem", lambda _path: tmp_path)
    monkeypatch.setattr(
        journal_module.shutil,
        "disk_usage",
        lambda _path: SimpleNamespace(free=MIN_FREE_BYTES * 2),
    )
    return tmp_path


def frame(pts=0, count=480, *, index=2, fmt="s16", channels=1, layout="mono"):
    return DecodedAudioFrame(index, pts, fmt, count, channels, layout)


def make(*, factory=None, rate=48000, time_base=Fraction(1, 1000),
         origin=Fraction(0), stream_index=2):
    return FrameTimingJournal(
        sample_rate=rate,
        time_base=time_base,
        origin=origin,
        stream_index=stream_index,
        journal_factory=factory,
    )


def test_default_private_file_replays_and_context_closes_it(local_storage):
    with make() as timing:
        handle = timing._file
        timing.append(frame(0))
        timing.append(frame(10))
        timing.seal()
        assert timing.frame_count == 2
        assert timing.total_samples == 960
        assert timing.signature == ("s16", 1, "mono")
        assert list(timing.entries()) == [
            FrameTimingEntry(0, 480, True),
            FrameTimingEntry(10, 480, False),
        ]
        assert not handle.closed
    assert handle.closed


def test_quantized_pts_do_not_reset_the_canonical_run_clock(local_storage):
    timing = make(rate=3000)
    timing.append(frame(0, 1))
    timing.append(frame(1, 1))
    # This timestamp is within one tick of the original run's exact 2/3000 clock.
    # Resetting the clock to the preceding quantized PTS would reject it instead.
    timing.append(frame(0, 1))
    timing.append(frame(3, 1))
    timing.seal()
    assert [entry.run_start for entry in timing.entries()] == [True, False, False, True]


def test_negative_origin_and_pts_are_preserved(local_storage):
    timing = make(origin=Fraction(-11, 1000))
    timing.append(frame(-10))
    timing.seal()
    assert list(timing.entries()) == [FrameTimingEntry(-10, 480, True)]


@pytest.mark.parametrize(
    "changes",
    (
        {"fmt": "flt"},
        {"channels": 2},
        {"layout": "stereo"},
    ),
)
def test_format_signature_cannot_change_midstream(local_storage, changes):
    timing = make()
    timing.append(frame())
    with pytest.raises(FileFrameJournalError, match="Invalid decoded-frame timing journal"):
        timing.append(frame(10, **changes))
    assert timing._file is None
    with pytest.raises(FileFrameJournalError):
        timing.entries()


def test_preroll_and_backward_overlap_poison_partial_results(local_storage):
    preroll = make(origin=Fraction(1, 1000))
    with pytest.raises(FileFrameJournalError):
        preroll.append(frame(0))
    assert preroll._file is None

    overlap = make()
    overlap.append(frame(0, 480))
    with pytest.raises(FileFrameJournalError):
        overlap.append(frame(8, 480))  # Expected 10 ms; two ticks backward.
    assert overlap._file is None


@pytest.mark.parametrize(
    "kwargs",
    (
        {"sample_rate": True},
        {"sample_rate": 0},
        {"sample_rate": 384001},
        {"time_base": Fraction(1, 999)},
        {"time_base": Fraction(0)},
        {"time_base": 0.001},
        {"origin": 0},
        {"origin": Fraction(2**63)},
        {"stream_index": True},
        {"stream_index": -1},
        {"stream_index": 2**63},
    ),
)
def test_constructor_rejects_nonexact_or_unbounded_values(kwargs):
    values = dict(
        sample_rate=48000,
        time_base=Fraction(1, 1000),
        origin=Fraction(0),
        stream_index=2,
    )
    values.update(kwargs)
    with pytest.raises((TypeError, ValueError), match="Invalid decoded-frame timing journal"):
        FrameTimingJournal(**values)


@pytest.mark.parametrize(
    "bad",
    (
        object(),
        DecodedAudioFrame(True, 0, "s16", 480, 1, "mono"),
        DecodedAudioFrame(3, 0, "s16", 480, 1, "mono"),
        DecodedAudioFrame(2, True, "s16", 480, 1, "mono"),
        DecodedAudioFrame(2, 0, "bogus", 480, 1, "mono"),
        DecodedAudioFrame(2, 0, "s16", 0, 1, "mono"),
        DecodedAudioFrame(2, 0, "s16", 480, True, "mono"),
        DecodedAudioFrame(2, 0, "s16", 480, 1, ""),
        DecodedAudioFrame(2, 0, "s16", 480, 1, "mono|side"),
        DecodedAudioFrame(2, 0, "s16", 480, 1, "mono\\side"),
    ),
)
def test_append_revalidates_dataclass_instances(local_storage, bad):
    timing = make()
    with pytest.raises(FileFrameJournalError, match="Invalid decoded-frame timing journal"):
        timing.append(bad)
    assert timing._file is None


def test_empty_seal_and_read_before_seal_fail_closed(local_storage):
    empty = make()
    with pytest.raises(FileFrameJournalError):
        empty.seal()
    assert empty._file is None

    partial = make()
    partial.append(frame())
    with pytest.raises(FileFrameJournalError):
        partial.entries()
    assert partial._file is None


def test_append_after_seal_invalidates_results(local_storage):
    timing = make()
    timing.append(frame())
    timing.seal()
    with pytest.raises(FileFrameJournalError):
        timing.append(frame(10))
    assert timing._file is None


class ShortWriter(io.BytesIO):
    def __init__(self, limit):
        super().__init__()
        self.limit = limit
        self.calls = []

    def write(self, value):
        count = min(self.limit, len(value))
        self.calls.append(count)
        return super().write(value[:count])


def test_short_writes_are_completed_without_losing_records(local_storage):
    handle = ShortWriter(3)
    timing = make(factory=lambda: handle)
    timing.append(frame())
    timing.seal()
    assert len(handle.calls) > 1
    assert list(timing.entries()) == [FrameTimingEntry(0, 480, True)]


class NoProgress(io.BytesIO):
    def write(self, _value):
        return 0


def test_no_progress_write_is_sanitized_and_poisoned(local_storage):
    handle = NoProgress()
    timing = make(factory=lambda: handle)
    timing.append(frame())
    with pytest.raises(FileFrameJournalError) as failure:
        timing.seal()
    assert str(failure.value) == "Private decoded-frame timing storage failed."
    assert handle.closed


def test_storage_exception_does_not_expose_raw_message(local_storage):
    class Broken(io.BytesIO):
        def write(self, _value):
            raise OSError("secret path and bytes")

    handle = Broken()
    timing = make(factory=lambda: handle)
    timing.append(frame())
    with pytest.raises(FileFrameJournalError) as failure:
        timing.seal()
    assert str(failure.value) == "Private decoded-frame timing storage failed."
    assert "secret" not in str(failure.value)
    assert handle.closed


def test_low_space_is_checked_before_creation_and_before_each_flush(local_storage, monkeypatch):
    created = []
    monkeypatch.setattr(
        journal_module.shutil,
        "disk_usage",
        lambda _path: SimpleNamespace(free=MIN_FREE_BYTES - 1),
    )
    with pytest.raises(FileFrameJournalError):
        make(factory=lambda: created.append(True) or io.BytesIO())
    assert created == []

    free = iter((MIN_FREE_BYTES * 2, MIN_FREE_BYTES))
    monkeypatch.setattr(
        journal_module.shutil,
        "disk_usage",
        lambda _path: SimpleNamespace(free=next(free)),
    )
    handle = io.BytesIO()
    timing = make(factory=lambda: handle)
    timing.append(frame())
    with pytest.raises(FileFrameJournalError) as failure:
        timing.seal()
    assert str(failure.value) == "Private decoded-frame timing storage failed."
    assert handle.closed


def test_full_buffer_flushes_at_exact_65535_byte_bound(local_storage):
    handle = ShortWriter(MAX_BUFFER_BYTES)
    timing = make(rate=1000, factory=lambda: handle)
    records = MAX_BUFFER_BYTES // RECORD.size
    for pts in range(records - 1):
        timing.append(frame(pts, 1))
    assert handle.calls == []
    assert len(timing._buffer) == MAX_BUFFER_BYTES - RECORD.size
    timing.append(frame(records - 1, 1))
    assert handle.calls == [MAX_BUFFER_BYTES]
    assert len(timing._buffer) == 0
    timing.seal()
    assert timing.frame_count == records
    assert len(list(timing.entries())) == records


def test_total_journal_byte_limit_rejects_before_another_record(local_storage, monkeypatch):
    monkeypatch.setattr(journal_module, "MAX_JOURNAL_BYTES", RECORD.size * 2)
    handle = io.BytesIO()
    timing = make(factory=lambda: handle)
    timing.append(frame(0))
    timing.append(frame(10))

    with pytest.raises(FileFrameJournalError) as failure:
        timing.append(frame(20))

    assert str(failure.value) == "Decoded-frame timing exceeds the private journal storage limit."
    assert timing.frame_count == 2
    assert timing.total_samples == 960
    assert handle.closed


@pytest.mark.parametrize("corruption", ("truncate", "extra", "flag", "count"))
def test_replay_detects_size_count_and_flag_corruption(local_storage, corruption):
    handle = io.BytesIO()
    timing = make(factory=lambda: handle)
    timing.append(frame())
    timing.seal()
    payload = bytearray(handle.getvalue())
    if corruption == "truncate":
        payload.pop()
    elif corruption == "extra":
        payload.append(0)
    elif corruption == "flag":
        payload[-1] = 0
    else:
        payload[:] = struct.pack("!qQB", 0, 481, 1)
    handle.seek(0)
    handle.truncate()
    handle.write(payload)
    with pytest.raises(FileFrameJournalError, match="Invalid decoded-frame timing journal"):
        list(timing.entries())
    assert handle.closed


def test_replay_digest_rejects_structurally_valid_same_size_pts_edit_at_eof(local_storage):
    handle = io.BytesIO()
    timing = make(factory=lambda: handle)
    timing.append(frame(0))
    timing.append(frame(10))
    timing.seal()
    payload = handle.getvalue()
    edited = bytearray()
    for pts, nb_samples, flag in RECORD.iter_unpack(payload):
        edited.extend(RECORD.pack(pts + 1, nb_samples, flag))
    assert len(edited) == len(payload)
    handle.seek(0)
    handle.write(edited)

    # Streaming entries are provisional until EOF verifies the sealed digest.
    iterator = timing.entries()
    assert next(iterator) == FrameTimingEntry(1, 480, True)
    assert next(iterator) == FrameTimingEntry(11, 480, False)
    with pytest.raises(FileFrameJournalError, match="Invalid decoded-frame timing journal"):
        next(iterator)
    assert handle.closed


def test_factory_and_locality_failures_are_sanitized(monkeypatch, tmp_path):
    monkeypatch.setattr(journal_module.tempfile, "gettempdir", lambda: str(tmp_path))
    monkeypatch.setattr(
        journal_module,
        "require_local_filesystem",
        lambda _path: (_ for _ in ()).throw(LocalFilesystemError("remote secret")),
    )
    with pytest.raises(FileFrameJournalError) as failure:
        make()
    assert str(failure.value) == "Private decoded-frame timing needs a verified local temporary folder."

    monkeypatch.setattr(journal_module, "require_local_filesystem", lambda _path: tmp_path)
    monkeypatch.setattr(
        journal_module.shutil,
        "disk_usage",
        lambda _path: SimpleNamespace(free=MIN_FREE_BYTES * 2),
    )
    with pytest.raises(FileFrameJournalError) as failure:
        make(factory=lambda: (_ for _ in ()).throw(OSError("private filename")))
    assert str(failure.value) == "Private decoded-frame timing storage failed."


def test_close_is_idempotent_and_discards_unsealed_records(local_storage):
    handle = io.BytesIO()
    timing = make(factory=lambda: handle)
    timing.append(frame())
    timing.close()
    timing.close()
    assert handle.closed
    with pytest.raises(FileFrameJournalError):
        timing.entries()
