from utterleaf.audio import Recorder, list_input_names, resolve_input_device
import numpy as np


def _devices() -> list[dict]:
    return [
        {"name": "Speakers", "max_input_channels": 0},
        {"name": "Headset Mic", "max_input_channels": 1},
        {"name": "USB Mic", "max_input_channels": 2},
    ]


def test_list_input_names_skips_outputs(monkeypatch) -> None:
    monkeypatch.setattr("utterleaf.audio.sd.query_devices", _devices)
    assert list_input_names() == ["Headset Mic", "USB Mic"]


def test_resolve_input_device(monkeypatch) -> None:
    monkeypatch.setattr("utterleaf.audio.sd.query_devices", _devices)
    assert resolve_input_device("") is None
    assert resolve_input_device("USB Mic") == 2
    assert resolve_input_device("headset") == 1
    assert resolve_input_device("missing") is None


def test_recorder_set_device_reopens() -> None:
    rec = Recorder()
    rec.preferred_device = "Headset Mic"

    class Stream:
        def stop(self) -> None:
            pass

        def close(self) -> None:
            pass

    rec._stream = Stream()
    rec.set_device("USB Mic")
    assert rec.preferred_device == "USB Mic"
    assert rec._stream is None
    rec.set_device("USB Mic")
    assert rec.preferred_device == "USB Mic"


def test_recorder_set_device_keeps_live_take() -> None:
    rec = Recorder(device="Headset Mic")
    rec.recording = True
    rec._stream = object()
    rec.set_device("USB Mic")
    assert rec.preferred_device == "USB Mic"
    assert rec._stream is not None


def test_preview_snapshot_only_copies_requested_tail():
    rec = Recorder()
    rec._chunks = [np.full((512, 1), i, dtype=np.float32) for i in range(200)]
    full = rec.snapshot()
    tail = rec.snapshot(max_seconds=0.05)
    np.testing.assert_array_equal(tail, full[-800:])
    assert rec.snapshot(max_seconds=0).size == 0
    rec.close()
    assert rec.snapshot().size == 0
