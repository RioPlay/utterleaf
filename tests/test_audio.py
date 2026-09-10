from utterleaf.audio import Recorder, SelectedMicrophoneUnavailable, list_input_names, resolve_input_device
import numpy as np
import pytest
from utterleaf.audio import resample_audio
from contextlib import nullcontext


@pytest.fixture(autouse=True)
def synthetic_com(monkeypatch):
    # These tests simulate devices, including Windows hosts on Linux CI.
    monkeypatch.setattr("utterleaf.audio_owner._com_scope", nullcontext)


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
    for name in ("headset", "missing", "Speakers", "usb mic"):
        with pytest.raises(SelectedMicrophoneUnavailable):
            resolve_input_device(name)


def test_missing_selected_microphone_never_opens_default_and_can_retry(monkeypatch):
    from utterleaf import audio
    devices = [{"name": "Laptop Mic", "max_input_channels": 1,
                "default_samplerate": 48000}]
    monkeypatch.setattr(audio.sd, "query_devices", lambda index=None, **kw:
                        devices if index is None else devices[index])
    monkeypatch.setattr(audio, "shared_input_device", lambda chosen, info, preferred: (chosen, info))
    opened = []
    class Stream:
        def __init__(self, **kwargs):
            opened.append(kwargs["device"])
        def start(self):
            pass
        def stop(self):
            pass
        def close(self):
            pass
    monkeypatch.setattr(audio.sd, "InputStream", Stream)
    recorder = Recorder("Headset Mic")
    with pytest.raises(SelectedMicrophoneUnavailable) as failure:
        recorder.start()
    assert not opened
    assert not recorder.recording
    assert "Settings" in audio.microphone_error_hint(failure.value)
    devices.append({**devices[0], "name": "Headset Mic"})
    recorder.start()
    assert opened == [1]
    assert recorder.device_name == "Headset Mic"
    recorder.stop()
    devices.pop()
    with pytest.raises(SelectedMicrophoneUnavailable):
        recorder.start()
    assert recorder._stream is None
    assert not recorder.recording
    assert opened == [1]
    recorder.close()


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


def test_capture_limit_bounds_buffer_even_when_stop_callback_is_delayed(monkeypatch):
    recorder = Recorder()
    monkeypatch.setattr(recorder, "prepare", lambda: None)
    block = np.ones((1600, 1), dtype=np.float32)
    recorder._on_audio(block, len(block), None, None)  # pre-roll
    recorder.start(max_seconds=0.25)
    for _ in range(100):
        recorder._on_audio(block, len(block), None, None)
    assert recorder.limit_reached.is_set()
    assert sum(len(chunk) for chunk in recorder._chunks) == 1600 + 4000
    assert recorder.stop().size == 5600
    recorder.start(max_seconds=1)
    assert not recorder.limit_reached.is_set()


@pytest.mark.parametrize("limit", [0, -1, float("inf"), float("nan")])
def test_invalid_capture_limit_does_not_open_microphone(monkeypatch, limit):
    recorder = Recorder()
    monkeypatch.setattr(recorder, "prepare", lambda: pytest.fail("Must validate before opening"))
    with pytest.raises(ValueError):
        recorder.start(max_seconds=limit)


def test_close_releases_stream_even_when_stop_fails():
    recorder = Recorder()
    closed = []
    class Stream:
        def stop(self):
            raise RuntimeError("Device disconnected")
        def close(self):
            closed.append(True)
    recorder._stream = Stream()
    recorder.close()
    assert closed == [True]
    assert recorder._stream is None


def test_windows_shared_host_selection_preserves_named_mic(monkeypatch):
    from utterleaf import audio
    monkeypatch.setattr(audio.sys, "platform", "win32")
    legacy = {"name": "USB microphone", "hostapi": 0, "max_input_channels": 1}
    shared = {**legacy, "hostapi": 1}
    other = {**shared, "name": "Laptop microphone"}
    hosts = [{"name": "MME"}, {"name": "Windows WASAPI", "default_input_device": 2}]
    monkeypatch.setattr(audio.sd, "query_hostapis", lambda: hosts)
    monkeypatch.setattr(audio.sd, "query_devices", lambda i=None: [legacy, shared, other] if i is None else [legacy, shared, other][i])
    assert audio.shared_input_device(None, legacy, "") == (2, other)
    assert audio.shared_input_device(0, legacy, "USB microphone") == (1, shared)
    monkeypatch.setattr(audio.sd, "query_devices", lambda: [legacy, shared, shared])
    assert audio.shared_input_device(0, legacy, "USB microphone") == (0, legacy)


@pytest.mark.parametrize("failures", [1, 2])
@pytest.mark.parametrize("native_code", [None, 0x8889000A, 0x88890004, 0x88890026, -2004287478])
def test_unavailable_stream_retries_once_and_closes_failures(monkeypatch, failures, native_code):
    from utterleaf import audio
    monkeypatch.setattr(audio.sys, "platform", "win32")
    monkeypatch.setattr(audio.sd, "query_devices", lambda *a, **k: {
        "name": "mic", "default_samplerate": 48000, "hostapi": 0,
    })
    monkeypatch.setattr(audio, "shared_input_device", lambda chosen, info, preferred: (chosen, info))
    monkeypatch.setattr(audio.sd, "query_hostapis", lambda _: {"name": "Windows WASAPI"})
    sentinel = object()
    modes, streams, waits = [], [], []
    monkeypatch.setattr(audio.sd, "WasapiSettings", lambda **kw: modes.append(kw) or sentinel)
    def wait(delay):
        assert streams[-1].closed
        waits.append(delay)
    monkeypatch.setattr(audio.time, "sleep", wait)
    class Stream:
        def __init__(self, **kwargs):
            assert kwargs["extra_settings"] is sentinel
            self.closed = False
            streams.append(self)
        def start(self):
            if len(streams) <= failures:
                if native_code is not None:
                    raise audio.sd.PortAudioError("Host error", -9999, (0, native_code, "native message"))
                raise audio.sd.PortAudioError("Device unavailable", -9985)
        def close(self):
            self.closed = True
        def stop(self):
            pass
    monkeypatch.setattr(audio.sd, "InputStream", Stream)
    recorder = Recorder()
    if failures == 2:
        with pytest.raises(audio.sd.PortAudioError):
            recorder.prepare()
        assert recorder._stream is None
    else:
        recorder.prepare()
        assert recorder._stream is streams[1]
    assert len(streams) == 2
    assert all(s.closed for s in streams[:failures])
    assert waits == [.15]
    assert modes == [{"exclusive": False}]
    recorder.close()


@pytest.mark.parametrize("code,transient,hint", [
    (0x8889000A, True, "exclusive"), (0x88890004, True, "invalidated"),
    (0x88890026, True, "invalidated"), (0x80070005, False, "desktop apps"),
    (0x88890008, False, "audio format"),
])
@pytest.mark.parametrize("signed", [False, True])
def test_wasapi_known_hresult_classification(monkeypatch, code, transient, hint, signed):
    from utterleaf import audio
    monkeypatch.setattr(audio.sys, "platform", "win32")
    queried = []
    monkeypatch.setattr(audio.sd, "query_hostapis", lambda index: queried.append(index) or {"name": "Windows WASAPI"})
    error = audio.sd.PortAudioError("Host error", -9999, (2, code - 2**32 if signed else code, "details"))
    assert audio.device_unavailable(error) is transient
    assert hint in audio.microphone_error_hint(error)
    assert queried and set(queried) == {2}


@pytest.mark.parametrize("host_error", [
    None, (), (0, 0x8889000A), [0, 0x8889000A, "text"],
    (True, 0x8889000A, "text"), (-1, 0x8889000A, "text"),
    (0, True, "text"), (0, "0x8889000A", "text"), (0, float(0x8889000A), "text"),
    (0, 0x18889000A, "text"), (0, -0x80000001, "text"), (0, 0x8889000A, None),
])
def test_malformed_host_error_fails_closed(monkeypatch, host_error):
    from utterleaf import audio
    monkeypatch.setattr(audio.sys, "platform", "win32")
    monkeypatch.setattr(audio.sd, "query_hostapis", lambda *a: pytest.fail("Malformed input must not query host"))
    assert not audio.device_unavailable(audio.sd.PortAudioError("error", -9999, host_error))


@pytest.mark.parametrize("platform,host", [("linux", "Windows WASAPI"), ("win32", "MME"), ("win32", "Windows DirectSound")])
def test_native_code_never_classifies_other_platform_or_host(monkeypatch, platform, host):
    from utterleaf import audio
    monkeypatch.setattr(audio.sys, "platform", platform)
    monkeypatch.setattr(audio.sd, "query_hostapis", lambda *a: {"name": host})
    assert not audio.device_unavailable(audio.sd.PortAudioError("error", -9999, (0, 0x8889000A, "text")))


def test_native_host_query_failure_fails_closed(monkeypatch):
    from utterleaf import audio
    monkeypatch.setattr(audio.sys, "platform", "win32")
    def unavailable(*args):
        raise audio.sd.PortAudioError("host disappeared")
    monkeypatch.setattr(audio.sd, "query_hostapis", unavailable)
    error = audio.sd.PortAudioError("error", -9999, (0, 0x8889000A, "text"))
    assert not audio.device_unavailable(error)
    assert "Could not open" in audio.microphone_error_hint(error)


def test_capture_interruption_hint_is_actionable_and_does_not_echo_exception():
    from utterleaf import audio
    hint = audio.microphone_error_hint(audio.MicrophoneCaptureInterrupted("private device details"))
    assert "Microphone capture was interrupted" in hint
    assert "retry the microphone check" in hint
    assert "private device details" not in hint


@pytest.mark.parametrize("code", [0x80070005, 0x88890008, 0x88890001])
def test_permission_format_unknown_errors_close_without_retry(monkeypatch, code):
    from utterleaf import audio
    monkeypatch.setattr(audio.sys, "platform", "win32")
    monkeypatch.setattr(audio, "resolve_input_device", lambda *a: 0)
    monkeypatch.setattr(audio.sd, "query_devices", lambda *a, **kw: {"name": "mic", "default_samplerate": 48000})
    monkeypatch.setattr(audio, "shared_input_device", lambda chosen, info, preferred: (chosen, info))
    monkeypatch.setattr(audio.sd, "query_hostapis", lambda *a: {"name": "Windows WASAPI"})
    monkeypatch.setattr(audio.time, "sleep", lambda *a: pytest.fail("Must not retry"))
    events = []
    class Stream:
        def __init__(self, **kwargs):
            events.append("open")
        def start(self):
            raise audio.sd.PortAudioError("error", -9999, (0, code, "text"))
        def close(self):
            events.append("close")
    monkeypatch.setattr(audio.sd, "InputStream", Stream)
    recorder = Recorder()
    with pytest.raises(audio.sd.PortAudioError):
        recorder.prepare()
    assert events == ["open", "close"]
    assert recorder._stream is None
