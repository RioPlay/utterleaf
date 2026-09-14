import json
import os
from fractions import Fraction
from pathlib import Path
import subprocess
import sys
import threading

import pytest

from utterleaf import file_probe as probe
from utterleaf import file_decoder as decoder
from utterleaf.file_decoder import DecoderSetupError
from utterleaf.transcript import TranscriptionCancelled


@pytest.fixture
def settings(tmp_path, monkeypatch):
    path = tmp_path / "file-probe.json"
    monkeypatch.setattr(probe, "_settings_path", lambda: path)
    return path


def executable(tmp_path, name="ffprobe"):
    if sys.platform == "win32":
        name += ".exe"
    path = tmp_path / name
    path.write_bytes(b"MZ synthetic ffprobe executable")
    return path


def test_selection_persists_hash_and_forget_preserves_executable(settings, tmp_path):
    path = executable(tmp_path)
    assert probe.select_probe(path) == path.absolute()
    record = json.loads(settings.read_text(encoding="utf-8"))
    assert record["version"] == 1
    assert record["path"] == str(path.absolute())
    assert len(record["sha256"]) == 64
    assert probe.probe_selection() == record
    assert probe.verified_probe() == path.absolute()
    probe.forget_probe()
    assert probe.probe_selection() is None
    assert path.exists()


def test_selection_never_executes_or_discovers_from_path(settings, tmp_path, monkeypatch):
    path = executable(tmp_path)
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: pytest.fail("must not execute"))
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: pytest.fail("must not execute"))
    monkeypatch.setenv("PATH", str(tmp_path))
    probe.select_probe(path)
    assert probe.probe_selection()["path"] == str(path.absolute())


def test_changed_or_swapped_executable_requires_reselection(settings, tmp_path):
    path = executable(tmp_path)
    probe.select_probe(path)
    path.write_bytes(b"MZ changed ffprobe executable")
    with pytest.raises(DecoderSetupError, match="changed|again"):
        probe.verified_probe()


def test_failed_replacement_preserves_prior_valid_record(settings, tmp_path):
    valid = executable(tmp_path)
    probe.select_probe(valid)
    before = probe.probe_selection()
    with pytest.raises(DecoderSetupError, match="ffprobe executable"):
        probe.select_probe(tmp_path / ("ffmpeg.exe" if sys.platform == "win32" else "ffmpeg"))
    assert probe.probe_selection() == before


def test_no_selection_is_actionable(settings):
    with pytest.raises(DecoderSetupError, match="Select.*FFprobe"):
        probe.verified_probe()


@pytest.mark.parametrize("payload", [
    b" " * (16 * 1024 + 1),
    b"{}",
    b'{"version":2,"path":"x","sha256":"' + b"0" * 64 + b'"}',
    b'{"version":1,"path":"x","sha256":"' + b"G" * 64 + b'"}',
])
def test_settings_are_bounded_and_strict(settings, payload):
    settings.write_bytes(payload)
    with pytest.raises(DecoderSetupError, match="invalid"):
        probe.probe_selection()


def test_settings_symlink_is_rejected(settings, tmp_path):
    target = tmp_path / "target.json"
    target.write_text("{}", encoding="utf-8")
    settings.unlink(missing_ok=True)
    try:
        settings.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation unavailable")
    with pytest.raises(DecoderSetupError, match="regular local"):
        probe.probe_selection()


@pytest.mark.parametrize("name", ["ffmpeg", "installer.cmd", "ffprobe.zip"])
def test_selection_rejects_non_ffprobe_names(settings, tmp_path, name):
    path = tmp_path / name
    path.write_bytes(b"MZ synthetic")
    with pytest.raises(DecoderSetupError, match="ffprobe executable"):
        probe.select_probe(path)


def test_ffmpeg_selection_does_not_create_or_discover_probe(settings, tmp_path, monkeypatch):
    ffmpeg = tmp_path / ("ffmpeg.exe" if sys.platform == "win32" else "ffmpeg")
    ffmpeg.write_bytes(b"MZ synthetic ffmpeg executable")
    adjacent = executable(tmp_path)
    monkeypatch.setattr(decoder, "_settings_path", lambda: tmp_path / "file-decoder.json")
    monkeypatch.setenv("PATH", str(tmp_path))
    decoder.select_decoder(ffmpeg)
    assert adjacent.exists()
    assert probe.probe_selection() is None
    with pytest.raises(DecoderSetupError, match="Select.*FFprobe"):
        probe.verified_probe()


def test_forget_without_selection_is_safe(settings):
    probe.forget_probe()
    assert not settings.exists()


VALID_METADATA = json.dumps({
    "streams": [{
        "index": 2,
        "codec_type": "audio",
        "codec_name": "pcm_s16le",
        "sample_rate": "48000",
        "channels": 2,
        "channel_layout": "stereo",
        "time_base": "1/48000",
        "start_pts": "-4800",
        "tags": {"title": "Mix", "language": "en"},
        "disposition": {"default": 1},
    }],
    "format": {"start_time": "-0.1"},
}).encode()


class FakeStdout:
    def __init__(self, owner, payload=b"", *, stalled=False, read_error=False,
                 after_read=None):
        self.owner = owner
        self.payload = payload
        self.offset = 0
        self.stalled = stalled
        self.read_error = read_error
        self.after_read = after_read
        self.started = threading.Event()
        self.released = threading.Event()
        self.closed = False

    def read(self, size):
        self.started.set()
        if self.stalled:
            self.released.wait(5)
        if self.read_error:
            raise OSError("private pipe failure")
        if self.offset < len(self.payload):
            end = min(len(self.payload), self.offset + size)
            block = self.payload[self.offset:end]
            self.offset = end
            if self.offset == len(self.payload) and self.after_read is not None:
                callback, self.after_read = self.after_read, None
                callback()
            return block
        if self.owner.returncode is None:
            self.owner.returncode = self.owner.exit_code
        return b""

    def close(self):
        self.closed = True
        self.released.set()


class FakeProcess:
    def __init__(self, payload=VALID_METADATA, *, exit_code=0, stalled=False,
                 read_error=False, after_read=None):
        self.exit_code = exit_code
        self.returncode = None
        self.killed = False
        self.waited = False
        self.stdout = FakeStdout(
            self,
            payload,
            stalled=stalled,
            read_error=read_error,
            after_read=after_read,
        )

    def poll(self):
        return self.returncode

    def wait(self, timeout=None):
        self.waited = True
        if self.returncode is None:
            raise subprocess.TimeoutExpired("ffprobe", timeout)
        return self.returncode

    def kill(self):
        self.killed = True
        self.returncode = -9
        self.stdout.released.set()


def media_file(tmp_path, suffix=".mkv"):
    path = tmp_path / ("private-recording" + suffix)
    path.write_bytes(b"synthetic local media")
    return path


def launch_probe(settings, tmp_path, monkeypatch, process, *, suffix=".mkv"):
    selected = executable(tmp_path)
    probe.select_probe(selected)
    path = media_file(tmp_path, suffix)
    calls = []

    def popen(command, **kwargs):
        calls.append((command, kwargs))
        return process

    monkeypatch.setattr(probe.subprocess, "Popen", popen)
    return path, selected, calls


def assert_cleaned(process):
    assert process.waited
    assert process.stdout.closed


def assert_preopen_refused(path, monkeypatch):
    path = path.resolve()
    path_type = type(path)
    real_open = path_type.open

    def guarded_open(self, *args, **kwargs):
        if self == path:
            pytest.fail("invalid media source must not be opened")
        return real_open(self, *args, **kwargs)

    monkeypatch.setattr(path_type, "open", guarded_open)
    monkeypatch.setattr(
        probe,
        "verified_probe",
        lambda: pytest.fail("invalid media source must not verify an executable"),
    )
    monkeypatch.setattr(
        probe.subprocess,
        "Popen",
        lambda *_args, **_kwargs: pytest.fail("invalid media source must not launch"),
    )
    with pytest.raises(ValueError, match="nonempty regular"):
        probe.probe_media(path)


def test_probe_media_runs_bounded_command_and_parses_all_stream_metadata(
        settings, tmp_path, monkeypatch):
    process = FakeProcess()
    path, selected, calls = launch_probe(settings, tmp_path, monkeypatch, process, suffix=".mp4")
    monkeypatch.setenv("FFREPORT", "file=private-path.log")

    result = probe.probe_media(path)

    assert result.origin.numerator == -1 and result.origin.denominator == 10
    assert result.tracks[0].stream_index == 2
    command, kwargs = calls[0]
    assert command[0] == str(selected.absolute())
    assert command[-2:] == ["-i", str(path.resolve())]
    assert command[command.index("-format_whitelist") + 1] == "mov"
    assert command[command.index("-protocol_whitelist") + 1] == "file"
    assert [command[command.index(name) + 1] for name in (
        "-max_alloc", "-probesize", "-analyzeduration"
    )] == ["67108864", "8388608", "5000000"]
    assert command[command.index("-show_entries") + 1] == (
        "stream=index,codec_type,codec_name,sample_rate,channels,channel_layout,"
        "time_base,start_pts:stream_tags=language,title:stream_disposition=default:"
        "format=start_time"
    )
    assert "-select_streams" not in command
    assert "-enable_drefs" in command and "-use_absolute_path" in command
    assert kwargs["stdin"] is subprocess.DEVNULL
    assert kwargs["stderr"] is subprocess.DEVNULL
    assert kwargs["stdout"] is subprocess.PIPE
    assert kwargs["shell"] is False and kwargs["cwd"] == selected.parent
    assert "FFREPORT" not in kwargs["env"]
    assert_cleaned(process)


@pytest.mark.parametrize("kind", ["directory", "empty"])
def test_nonregular_or_empty_source_is_refused_before_open_or_launch(
        settings, tmp_path, monkeypatch, kind):
    if kind == "directory":
        path = tmp_path / "selected-directory.mkv"
        path.mkdir()
    else:
        path = tmp_path / "empty.mkv"
        path.touch()
    assert_preopen_refused(path, monkeypatch)


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="POSIX FIFO creation unavailable")
def test_fifo_is_refused_before_blocking_open_or_launch(settings, tmp_path, monkeypatch):
    path = tmp_path / "selected-fifo.mkv"
    os.mkfifo(path)
    assert_preopen_refused(path, monkeypatch)


def test_cancel_before_launch_never_starts_process(settings, tmp_path, monkeypatch):
    path = media_file(tmp_path)
    cancelled = threading.Event()
    cancelled.set()
    monkeypatch.setattr(
        probe.subprocess, "Popen", lambda *_a, **_k: pytest.fail("must not launch")
    )
    with pytest.raises(TranscriptionCancelled, match="cancelled"):
        probe.probe_media(path, cancel=cancelled)


def test_cancel_during_read_kills_reaps_and_joins_reader(settings, tmp_path, monkeypatch):
    process = FakeProcess(stalled=True)
    path, _selected, _calls = launch_probe(settings, tmp_path, monkeypatch, process)
    cancelled = threading.Event()
    outcome = []

    def run():
        try:
            probe.probe_media(path, cancel=cancelled)
        except BaseException as exc:
            outcome.append(exc)

    worker = threading.Thread(target=run)
    worker.start()
    assert process.stdout.started.wait(1)
    cancelled.set()
    worker.join(2)
    assert not worker.is_alive()
    assert len(outcome) == 1 and isinstance(outcome[0], TranscriptionCancelled)
    assert process.killed
    assert_cleaned(process)


def test_cancel_after_output_suppresses_parsed_result(settings, tmp_path, monkeypatch):
    cancelled = threading.Event()
    process = FakeProcess(after_read=cancelled.set)
    path, _selected, _calls = launch_probe(settings, tmp_path, monkeypatch, process)
    with pytest.raises(TranscriptionCancelled, match="cancelled"):
        probe.probe_media(path, cancel=cancelled)
    assert_cleaned(process)


def test_wall_timeout_stops_stalled_process(settings, tmp_path, monkeypatch):
    process = FakeProcess(stalled=True)
    path, _selected, _calls = launch_probe(settings, tmp_path, monkeypatch, process)
    now = iter((0.0, 31.0, 31.0, 31.0))
    monkeypatch.setattr(probe.time, "monotonic", lambda: next(now, 31.0))
    with pytest.raises(DecoderSetupError, match="too long"):
        probe.probe_media(path)
    assert process.killed
    assert_cleaned(process)


def test_oversized_output_stops_process_before_parser(settings, tmp_path, monkeypatch):
    process = FakeProcess(b"x" * (probe.MAX_PROBE_BYTES + 1))
    path, _selected, _calls = launch_probe(settings, tmp_path, monkeypatch, process)
    with pytest.raises(DecoderSetupError, match="too much"):
        probe.probe_media(path)
    assert process.killed
    assert_cleaned(process)


@pytest.mark.parametrize("payload,exit_code,match", [
    (b"{", 0, "JSON"),
    (VALID_METADATA, 7, "damaged or unsupported"),
])
def test_invalid_or_nonzero_output_is_sanitized_and_cleaned(
        settings, tmp_path, monkeypatch, payload, exit_code, match):
    process = FakeProcess(payload, exit_code=exit_code)
    path, _selected, _calls = launch_probe(settings, tmp_path, monkeypatch, process)
    with pytest.raises((ValueError, DecoderSetupError), match=match) as raised:
        probe.probe_media(path)
    assert "private-recording" not in str(raised.value)
    assert_cleaned(process)


def test_pipe_read_failure_is_sanitized_and_cleaned(settings, tmp_path, monkeypatch):
    process = FakeProcess(read_error=True)
    path, _selected, _calls = launch_probe(settings, tmp_path, monkeypatch, process)
    with pytest.raises(DecoderSetupError, match="Could not read metadata") as raised:
        probe.probe_media(path)
    assert "private pipe failure" not in str(raised.value)
    assert_cleaned(process)


def test_reader_thread_start_failure_stops_process_without_raw_error(
        settings, tmp_path, monkeypatch):
    process = FakeProcess(stalled=True)
    path, _selected, _calls = launch_probe(settings, tmp_path, monkeypatch, process)

    class ThreadStartFailure:
        ident = None

        def __init__(self, **_kwargs):
            pass

        def start(self):
            raise RuntimeError("private thread error")

        def is_alive(self):
            return False

    monkeypatch.setattr(probe.threading, "Thread", ThreadStartFailure)
    with pytest.raises(DecoderSetupError, match="could not continue") as raised:
        probe.probe_media(path)
    assert "private thread error" not in str(raised.value)
    assert process.killed
    assert_cleaned(process)


def test_in_place_source_change_is_rejected_after_process_cleanup(
        settings, tmp_path, monkeypatch):
    path = media_file(tmp_path)

    def mutate():
        with path.open("ab") as stream:
            stream.write(b"changed")

    process = FakeProcess(after_read=mutate)
    selected = executable(tmp_path)
    probe.select_probe(selected)
    monkeypatch.setattr(probe.subprocess, "Popen", lambda *_a, **_k: process)
    with pytest.raises(ValueError, match="changed during inspection"):
        probe.probe_media(path)
    assert_cleaned(process)


def test_path_replacement_is_rejected_after_process_cleanup(
        settings, tmp_path, monkeypatch):
    if sys.platform == "win32":
        pytest.skip("Windows holds the source open and refuses pathname replacement")
    path = media_file(tmp_path)

    def replace():
        replacement = tmp_path / "replacement.mkv"
        replacement.write_bytes(path.read_bytes())
        os.replace(replacement, path)

    process = FakeProcess(after_read=replace)
    selected = executable(tmp_path)
    probe.select_probe(selected)
    monkeypatch.setattr(probe.subprocess, "Popen", lambda *_a, **_k: process)
    with pytest.raises(ValueError, match="changed during inspection"):
        probe.probe_media(path)
    assert_cleaned(process)


def test_changed_probe_selection_prevents_launch(settings, tmp_path, monkeypatch):
    selected = executable(tmp_path)
    probe.select_probe(selected)
    selected.write_bytes(b"MZ replacement executable")
    path = media_file(tmp_path)
    monkeypatch.setattr(
        probe.subprocess, "Popen", lambda *_a, **_k: pytest.fail("must not launch")
    )
    with pytest.raises(DecoderSetupError, match="changed"):
        probe.probe_media(path)


def test_process_start_failure_is_sanitized(settings, tmp_path, monkeypatch):
    selected = executable(tmp_path)
    probe.select_probe(selected)
    path = media_file(tmp_path)

    def fail_start(*_args, **_kwargs):
        raise OSError("private executable and media paths")

    monkeypatch.setattr(probe.subprocess, "Popen", fail_start)
    with pytest.raises(DecoderSetupError, match="could not start") as raised:
        probe.probe_media(path)
    assert "private" not in str(raised.value)
    assert raised.value.__cause__ is None


def test_opt_in_verified_ffprobe_reads_synthetic_local_media(settings, tmp_path):
    executable_path = os.environ.get("UTTERLEAF_TEST_FFPROBE")
    if not executable_path:
        pytest.skip("UTTERLEAF_TEST_FFPROBE is not configured")
    try:
        import av
        import numpy as np
    except ImportError:
        pytest.skip("Development PyAV is unavailable")

    media = tmp_path / "synthetic-timing.mkv"
    with av.open(str(media), "w") as container:
        stream = container.add_stream("pcm_s16le", rate=48_000)
        stream.layout = "mono"
        frame = av.AudioFrame.from_ndarray(
            np.arange(4_800, dtype=np.int16).reshape(1, -1),
            format="s16",
            layout="mono",
        )
        frame.sample_rate = 48_000
        frame.time_base = Fraction(1, 48_000)
        frame.pts = 0
        for packet in stream.encode(frame):
            container.mux(packet)
        for packet in stream.encode(None):
            container.mux(packet)

    probe.select_probe(Path(executable_path))
    result = probe.probe_media(media)
    assert result.origin == 0
    assert result.origin_kind == "container"
    assert len(result.tracks) == 1
    assert result.tracks[0].stream_index == 0
    assert result.tracks[0].sample_rate == 48_000
    assert result.tracks[0].channels == 1
