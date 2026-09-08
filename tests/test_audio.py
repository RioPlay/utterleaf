from utterleaf.audio import Recorder, list_input_names, resolve_input_device
import numpy as np
import pytest
from utterleaf.audio import resample_audio


def _devices() -> list[dict]:
    return [
        {"name": "Speakers", "max_input_channels": 0},
        {"name": "Headset Mic", "max_input_channels": 1},
        {"name": "USB Mic", "max_input_channels": 2},
    ]


def test_list_input_names_skips_outputs(monkeypatch) -> None:
    monkeypatch.setattr("utterleaf.audio.sd.query_devices", _devices)
    assert list_input_names() == ["Headset Mic", "USB Mic"]


def test_startup_input_overflow_is_quiet_but_late_overflow_warns(monkeypatch, caplog) -> None:
    import logging

    recorder = Recorder()
    mono = np.zeros((16, 1), dtype=np.float32)
    overflow = type("Status", (), {"input_overflow": True})()
    monkeypatch.setattr("utterleaf.audio.time.monotonic", lambda: 1000.0)

    recorder._opened_at = 1000.0
    with caplog.at_level(logging.DEBUG, logger="utterleaf"):
        recorder._on_audio(mono, 16, None, overflow)
    assert any(record.levelno == logging.DEBUG for record in caplog.records)
    assert not any(record.levelno >= logging.WARNING for record in caplog.records)

    caplog.clear()
    recorder._opened_at = 990.0
    with caplog.at_level(logging.WARNING, logger="utterleaf"):
        recorder._on_audio(mono, 16, None, overflow)
    assert any(record.levelno >= logging.WARNING for record in caplog.records)


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


@pytest.mark.parametrize("rate", [44100, 48000])
def test_recorder_uses_native_rate_and_returns_16khz(monkeypatch, rate):
    from utterleaf import audio
    monkeypatch.setattr(audio.sd, "query_devices", lambda *a, **k: {
        "name": "ALSA native mic", "default_samplerate": rate,
    })
    opened = []

    class Stream:
        def __init__(self, **kwargs):
            # Reproduce a device that rejects the old fixed 16 kHz rate.
            assert kwargs["samplerate"] == rate
            self.callback = kwargs["callback"]
            self.closed = False
            opened.append(self)

        def start(self):
            pass

        def stop(self):
            pass

        def close(self):
            self.closed = True

    monkeypatch.setattr(audio.sd, "InputStream", Stream)
    recorder = Recorder()
    recorder.start()
    pcm = np.sin(2 * np.pi * 1000 * np.arange(rate) / rate).astype(np.float32)
    # Irregular callback blocks must not change timing.
    for chunk in np.array_split(pcm, 79):
        opened[0].callback(chunk[:, None], len(chunk), None, None)
    assert recorder.snapshot(max_seconds=.1).size == 1600
    take = recorder.stop()
    assert take.dtype == np.float32
    assert take.size == 16000
    assert recorder.seconds(take) == 1.0
    expected = np.sin(2 * np.pi * 1000 * np.arange(16000) / 16000)
    np.testing.assert_allclose(take[100:-100], expected[100:-100], atol=.02)
    recorder.start()
    assert .29 <= recorder.seconds(recorder.stop()) <= .32
    recorder.close()
    assert opened[0].closed


@pytest.mark.parametrize("rate", [44100, 48000])
def test_downsampling_filters_frequencies_above_whisper_nyquist(rate):
    pcm = np.sin(2 * np.pi * 12000 * np.arange(rate) / rate).astype(np.float32)
    converted = resample_audio(pcm, rate)[100:-100]
    assert np.sqrt(np.mean(converted ** 2)) < .01


def test_resampling_handles_short_and_empty_takes():
    assert resample_audio(np.zeros(0), 48000).size == 0
    assert resample_audio(np.ones(3), 48000).shape == (1,)
    pcm = np.arange(20, dtype=np.float32)
    np.testing.assert_array_equal(resample_audio(pcm, 16000), pcm)


def test_failed_stream_start_closes_device(monkeypatch):
    from utterleaf import audio
    monkeypatch.setattr(audio.sd, "query_devices", lambda *a, **k: {
        "name": "mic", "default_samplerate": 48000,
    })
    closed = []

    class Stream:
        def __init__(self, **kwargs):
            pass

        def start(self):
            raise RuntimeError("Device disappeared")

        def close(self):
            closed.append(True)

    monkeypatch.setattr(audio.sd, "InputStream", Stream)
    recorder = Recorder()
    with pytest.raises(RuntimeError, match="Device disappeared"):
        recorder.prepare()
    assert recorder._stream is None
    assert closed == [True]
