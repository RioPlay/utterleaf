from __future__ import annotations

from contextlib import closing
import os
from pathlib import Path
import subprocess
import sys
import threading
import time

import pytest

import utterleaf.media_process as media
from utterleaf.transcript import TranscriptionCancelled


PYTHON = Path(sys.executable)


def child(code: str, **kwargs):
    return media.iter_tool_output(PYTHON, ["-c", code], check_identity=lambda: None, **kwargs)


def capture_process(monkeypatch):
    original = media.subprocess.Popen
    seen = []

    def launch(*args, **kwargs):
        process = original(*args, **kwargs)
        seen.append(process)
        return process

    monkeypatch.setattr(media.subprocess, "Popen", launch)
    return seen


def test_small_output_and_launch_contract(monkeypatch):
    monkeypatch.setenv("FFREPORT", "private-report.log")
    original = media.subprocess.Popen
    calls = []
    identity = []

    def checked():
        identity.append("checked")

    def launch(command, **kwargs):
        assert identity == ["checked"]
        calls.append((command, kwargs))
        return original(command, **kwargs)

    monkeypatch.setattr(media.subprocess, "Popen", launch)
    result = b"".join(media.iter_tool_output(
        PYTHON, ["-c", "import os; os.write(1,b'hello')"], check_identity=checked,
    ))
    assert result == b"hello"
    command, kwargs = calls[0]
    assert command[:2] == [str(PYTHON), "-c"]
    assert kwargs["shell"] is False
    assert kwargs["stdin"] is subprocess.DEVNULL
    assert kwargs["stdout"] is subprocess.PIPE and kwargs["stderr"] is subprocess.PIPE
    assert kwargs["cwd"] == PYTHON.parent
    assert "FFREPORT" not in kwargs["env"]
    assert kwargs["creationflags"] == (getattr(subprocess, "CREATE_NO_WINDOW", 0)
                                         if sys.platform == "win32" else 0)


def test_identity_failure_happens_without_launch(monkeypatch):
    monkeypatch.setattr(media.subprocess, "Popen", lambda *a, **k: pytest.fail("launched"))
    with pytest.raises(RuntimeError, match="identity refusal"):
        list(media.iter_tool_output(
            PYTHON, [], check_identity=lambda: (_ for _ in ()).throw(RuntimeError("identity refusal")),
        ))


def test_nonzero_after_partial_output_is_terminal_and_sanitized(monkeypatch):
    processes = capture_process(monkeypatch)
    stream = child("import os,sys; os.write(1,b'private payload'); sys.exit(7)")
    assert next(stream) == b"private payload"
    with pytest.raises(RuntimeError) as failure:
        next(stream)
    assert "private" not in str(failure.value)
    assert processes[0].poll() == 7


def test_early_close_sets_shared_abort_and_reaps(monkeypatch):
    processes = capture_process(monkeypatch)
    abort = threading.Event()
    stream = child("import os,time; os.write(1,b'x'); time.sleep(30)", abort=abort)
    assert next(stream) == b"x"
    stream.close()
    assert abort.is_set()
    assert processes[0].poll() is not None


def test_user_cancel_is_distinct_from_shared_abort(monkeypatch):
    processes = capture_process(monkeypatch)
    cancel, abort = threading.Event(), threading.Event()
    stream = child("import os,time; os.write(1,b'x'); time.sleep(30)", cancel=cancel, abort=abort)
    assert next(stream) == b"x"
    cancel.set()
    with pytest.raises(TranscriptionCancelled):
        next(stream)
    assert abort.is_set() and processes[0].poll() is not None


def test_abort_only_is_generic_not_user_cancel(monkeypatch):
    processes = capture_process(monkeypatch)
    abort = threading.Event()
    stream = child("import os,time; os.write(1,b'x'); time.sleep(30)", abort=abort)
    assert next(stream) == b"x"
    abort.set()
    with pytest.raises(RuntimeError, match="stopped before completion"):
        next(stream)
    assert processes[0].poll() is not None


def test_inactivity_timeout_reaps_silent_child(monkeypatch):
    processes = capture_process(monkeypatch)
    started = time.monotonic()
    with pytest.raises(RuntimeError, match="no progress"):
        list(child("import time; time.sleep(30)", inactivity_timeout=0.12))
    assert time.monotonic() - started < 2
    assert processes[0].poll() is not None


def test_wall_timeout_stops_child_that_keeps_making_progress(monkeypatch):
    processes = capture_process(monkeypatch)
    code = "import os,time\nwhile True:\n os.write(1,b'x'); time.sleep(.01)"
    with pytest.raises(RuntimeError, match="took too long"):
        list(child(code, inactivity_timeout=1, wall_timeout=0.15))
    assert processes[0].poll() is not None


def test_consumer_pause_does_not_count_as_inactivity():
    block = b"z" * media._BLOCK_BYTES
    stream = child(
        "import os\nb=b'z'*65536\nfor _ in range(8): os.write(1,b)",
        inactivity_timeout=0.1,
    )
    first = next(stream)
    time.sleep(0.25)
    assert first + b"".join(stream) == block * 8


def test_stderr_is_drained_under_pressure_and_optional_policy():
    code = "import os; os.write(2,b'e'*1048576); os.write(1,b'ok')"
    assert b"".join(child(code)) == b"ok"
    with pytest.raises(RuntimeError, match="unexpected diagnostics"):
        list(child(code, reject_stderr=True))


def test_input_chunks_roundtrip_and_partial_writes(monkeypatch):
    original = media.subprocess.Popen

    class PartialWriter:
        def __init__(self, stream):
            self.stream = stream

        def write(self, value):
            return self.stream.write(value[:3])

        def close(self):
            self.stream.close()

    def launch(*args, **kwargs):
        process = original(*args, **kwargs)
        process.stdin = PartialWriter(process.stdin)
        return process

    monkeypatch.setattr(media.subprocess, "Popen", launch)
    payload = [b"abcdef", b"0123456789"]
    result = b"".join(child(
        "import sys; sys.stdout.buffer.write(sys.stdin.buffer.read())",
        input_chunks=payload,
    ))
    assert result == b"".join(payload)


@pytest.mark.parametrize("value", [b"", b"x" * (media._BLOCK_BYTES + 1), bytearray(b"x")],
                         ids=("empty", "oversized", "not-bytes"))
def test_invalid_input_chunk_fails_and_aborts(value):
    abort = threading.Event()
    with pytest.raises(RuntimeError, match="input could not be delivered"):
        list(child("import sys; sys.stdin.buffer.read()", input_chunks=[value], abort=abort))
    assert abort.is_set()


def test_source_iteration_error_is_not_swallowed_by_its_abort():
    abort = threading.Event()

    def chunks():
        yield b"prefix"
        raise RuntimeError("private source detail")

    with pytest.raises(RuntimeError, match="input could not be delivered") as failure:
        list(child("import sys; sys.stdout.buffer.write(sys.stdin.buffer.read())",
                   input_chunks=chunks(), abort=abort))
    assert "private source" not in str(failure.value)
    assert abort.is_set()


def test_collect_limit_abandons_and_reaps(monkeypatch):
    processes = capture_process(monkeypatch)
    with pytest.raises(RuntimeError, match="too much output"):
        media.collect_tool_output(
            PYTHON, ["-c", "import os,time; os.write(1,b'x'*100); time.sleep(30)"],
            check_identity=lambda: None, max_bytes=10,
        )
    assert processes[0].poll() is not None


def test_popen_failure_is_generic(monkeypatch):
    monkeypatch.setattr(media.subprocess, "Popen",
                        lambda *a, **k: (_ for _ in ()).throw(OSError("private path")))
    with pytest.raises(RuntimeError, match="could not start") as failure:
        list(child("pass"))
    assert "private path" not in str(failure.value)


def test_thread_start_failure_reaps_process(monkeypatch):
    processes = capture_process(monkeypatch)
    original = media.threading.Thread.start

    def start(thread):
        if thread.name == "utterleaf-media-stderr":
            raise RuntimeError("private thread detail")
        return original(thread)

    monkeypatch.setattr(media.threading.Thread, "start", start)
    with pytest.raises(RuntimeError) as failure:
        list(child("import time; time.sleep(30)"))
    assert "private thread" not in str(failure.value)
    assert processes[0].poll() is not None


@pytest.mark.parametrize("field,value", [
    ("inactivity_timeout", 0), ("inactivity_timeout", float("nan")),
    ("wall_timeout", 0), ("wall_timeout", float("inf")),
])
def test_invalid_timeout_rejected_before_identity(field, value):
    called = False

    def identity():
        nonlocal called
        called = True

    with pytest.raises(ValueError):
        list(media.iter_tool_output(PYTHON, [], check_identity=identity, **{field: value}))
    assert not called


def test_abort_must_be_writable_before_identity():
    class ReadOnlyEvent:
        def is_set(self):
            return False

    with pytest.raises(TypeError, match="set"):
        list(media.iter_tool_output(
            PYTHON, [], check_identity=lambda: pytest.fail("identity called"),
            abort=ReadOnlyEvent(),
        ))


def test_input_source_is_closed_when_output_consumer_abandons():
    closed = threading.Event()

    def chunks():
        try:
            while True:
                yield b"x" * media._BLOCK_BYTES
        finally:
            closed.set()

    stream = child(
        "import os,time; os.write(1,b'ready'); time.sleep(30)",
        input_chunks=chunks(), abort=threading.Event(),
    )
    assert next(stream) == b"ready"
    stream.close()
    assert closed.wait(1)
