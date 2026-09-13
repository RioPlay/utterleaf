from __future__ import annotations

import ctypes
import sys
import threading
import time

import pytest

from utterleaf import windows_pipe as pipe_mod
from windows_pipe_server import start_native_pipe_server


NAME = r"\\.\pipe\Utterleaf.OBS.0123456789abcdef0123456789abcdef"


class FakeNative:
    def __init__(self, *, reads: list[bytes] | None = None, writes: list[int] | None = None):
        self.reads = list(reads or [])
        self.writes = list(writes or [])
        self.opened = []
        self.closed = []
        self.written = bytearray()
        self.pid = 99
        self.next_handle = 50
        self.result_count = 0

    def open_pipe(self, name):
        self.opened.append(name)
        return 7

    def create_event(self):
        self.next_handle += 1
        return self.next_handle

    def begin_read(self, handle, buffer, size, overlapped):
        value = self.reads.pop(0)
        for index, byte in enumerate(value):
            buffer[index] = byte
        self.result_count = len(value)
        return True

    def begin_write(self, handle, buffer, size, overlapped):
        count = self.writes.pop(0) if self.writes else size
        self.written.extend(ctypes.string_at(buffer, count))
        self.result_count = count
        return True

    def wait(self, event, milliseconds):
        return pipe_mod._WAIT_OBJECT_0

    def cancel(self, handle, overlapped):
        return 0

    def result(self, handle, overlapped, *, wait):
        return self.result_count

    def server_pid(self, handle):
        return self.pid

    def close(self, handle):
        self.closed.append(handle)


def test_invalid_names_reject_before_native(monkeypatch):
    def forbidden():
        raise AssertionError("native API loaded")
    monkeypatch.setattr(pipe_mod, "_Native", forbidden)
    bad = [
        r"\\server\pipe\Utterleaf.OBS.0123456789abcdef0123456789abcdef",
        r"\\.\pipe\Other.0123456789abcdef0123456789abcdef",
        r"\\.\pipe\Utterleaf.OBS.A123456789abcdef0123456789abcdef",
        r"\\.\pipe\Utterleaf.OBS.0123", NAME + r"\child", "relative",
    ]
    for value in bad:
        with pytest.raises(ValueError):
            pipe_mod.connect(value, cancelled=lambda: False, deadline=time.monotonic() + 1)
    class Text(str):
        pass
    with pytest.raises(ValueError):
        pipe_mod.connect(Text(NAME), cancelled=lambda: False, deadline=time.monotonic() + 1)


def test_connect_retries_only_missing_and_busy(monkeypatch):
    native = FakeNative()
    attempts = iter([pipe_mod._NativeFailure(2), pipe_mod._NativeFailure(231), 11])
    def open_pipe(name):
        value = next(attempts)
        if isinstance(value, Exception):
            raise value
        return value
    native.open_pipe = open_pipe
    monkeypatch.setattr(pipe_mod, "_Native", lambda: native)
    monkeypatch.setattr(pipe_mod.time, "sleep", lambda value: None)
    with pipe_mod.connect(NAME, cancelled=lambda: False, deadline=time.monotonic() + 1) as pipe:
        assert pipe.server_pid() == 99
    assert native.closed == [11]


def test_connect_late_cancellation_closes_open_handle(monkeypatch):
    native = FakeNative()
    checks = iter([False, False, True])
    monkeypatch.setattr(pipe_mod, "_Native", lambda: native)
    with pytest.raises(pipe_mod.WindowsPipeCancelled):
        pipe_mod.connect(NAME, cancelled=lambda: next(checks), deadline=time.monotonic() + 1)
    assert native.closed == [7]


def test_connect_closes_handle_if_pipe_ownership_construction_fails(monkeypatch):
    native = FakeNative()
    monkeypatch.setattr(pipe_mod, "_Native", lambda: native)
    monkeypatch.setattr(
        pipe_mod,
        "WindowsPipe",
        lambda *_args: (_ for _ in ()).throw(MemoryError()),
    )
    with pytest.raises(MemoryError):
        pipe_mod.connect(NAME, cancelled=lambda: False, deadline=time.monotonic() + 1)
    assert native.closed == [7]


def test_create_file_uses_local_overlapped_identification_flags(monkeypatch):
    calls = []
    class Function:
        def __init__(self, result=1):
            self.result = result
        def __call__(self, *args):
            calls.append(args)
            return self.result
    class Kernel:
        CreateFileW = Function(7)
        CreateEventW = Function(8)
        ReadFile = Function()
        WriteFile = Function()
        WaitForSingleObject = Function()
        CancelIoEx = Function()
        GetOverlappedResult = Function()
        GetNamedPipeServerProcessId = Function()
        CloseHandle = Function()
    monkeypatch.setattr(pipe_mod.sys, "platform", "win32")
    monkeypatch.setattr(pipe_mod.ctypes, "WinDLL", lambda *args, **kwargs: Kernel())
    native = pipe_mod._Native()
    assert native.open_pipe(NAME) == 7
    name, access, share, security, disposition, flags, template = calls[0]
    assert name == NAME
    assert access == pipe_mod._GENERIC_READ | pipe_mod._GENERIC_WRITE
    assert share == 0 and security is None and disposition == pipe_mod._OPEN_EXISTING
    assert flags == (
        pipe_mod._FILE_FLAG_OVERLAPPED
        | pipe_mod._SECURITY_SQOS_PRESENT
        | pipe_mod._SECURITY_IDENTIFICATION
    )
    assert template is None


def test_partial_write_and_read_preserve_bytes():
    native = FakeNative(reads=[b"abc"], writes=[2, 1, 3])
    pipe = pipe_mod.WindowsPipe(native, 7, lambda: False)
    deadline = time.monotonic() + 1
    pipe.write_all(b"abcdef", deadline=deadline)
    assert native.written == b"abcdef"
    assert pipe.read(8, deadline=deadline) == b"abc"
    pipe.close()


@pytest.mark.parametrize("operation", ["read", "write"])
def test_zero_byte_success_is_terminal(operation):
    native = FakeNative(reads=[b""], writes=[0])
    pipe = pipe_mod.WindowsPipe(native, 7, lambda: False)
    with pytest.raises(pipe_mod.WindowsPipeError):
        if operation == "read":
            pipe.read(1, deadline=time.monotonic() + 1)
        else:
            pipe.write_all(b"x", deadline=time.monotonic() + 1)
    assert 7 in native.closed


def test_server_pid_is_queried_each_time_and_failure_closes():
    native = FakeNative()
    pipe = pipe_mod.WindowsPipe(native, 7, lambda: False)
    assert pipe.server_pid() == 99
    native.pid = 100
    assert pipe.server_pid() == 100
    native.pid = 4
    with pytest.raises(pipe_mod.WindowsPipeError):
        pipe.server_pid()
    assert 7 in native.closed


def test_late_cancellation_after_immediate_read_is_terminal():
    checks = iter([False, True])
    native = FakeNative(reads=[b"secret"])
    pipe = pipe_mod.WindowsPipe(native, 7, lambda: next(checks))
    with pytest.raises(pipe_mod.WindowsPipeCancelled):
        pipe.read(8, deadline=time.monotonic() + 1)
    assert 7 in native.closed


def test_argument_bounds_do_not_touch_native():
    native = FakeNative()
    pipe = pipe_mod.WindowsPipe(native, 7, lambda: False)
    for value in (0, 65_537, True, 1.0):
        with pytest.raises((TypeError, ValueError)):
            pipe.read(value, deadline=time.monotonic() + 1)
    for value in (b"", b"x" * 65_537, bytearray(b"x")):
        with pytest.raises((TypeError, ValueError)):
            pipe.write_all(value, deadline=time.monotonic() + 1)
    assert native.closed == []
    pipe.close()


class PendingNative(FakeNative):
    def __init__(self):
        super().__init__()
        self.actions = []
        self.release = threading.Event()

    def begin_read(self, handle, buffer, size, overlapped):
        self.actions.append("begin")
        return False

    def wait(self, event, milliseconds):
        self.actions.append("wait")
        self.release.wait(0.01)
        return pipe_mod._WAIT_TIMEOUT

    def cancel(self, handle, overlapped):
        self.actions.append("cancel")
        return 0

    def result(self, handle, overlapped, *, wait):
        self.actions.append(("result", wait))
        raise pipe_mod._NativeFailure(995)

    def close(self, handle):
        self.actions.append(("close", handle))
        super().close(handle)


def test_cancel_drains_before_event_and_pipe_close():
    stopped = threading.Event()
    native = PendingNative()
    pipe = pipe_mod.WindowsPipe(native, 7, stopped.is_set)
    errors = []
    thread = threading.Thread(target=lambda: _capture_error(errors, lambda: pipe.read(4, deadline=time.monotonic() + 2)))
    thread.start()
    assert _wait_for(lambda: "begin" in native.actions)
    stopped.set()
    thread.join(2)
    assert not thread.is_alive()
    assert isinstance(errors[0], pipe_mod.WindowsPipeCancelled)
    drain = native.actions.index(("result", True))
    event_close = next(i for i, item in enumerate(native.actions) if item == ("close", 51))
    pipe_close = next(i for i, item in enumerate(native.actions) if item == ("close", 7))
    assert drain < event_close < pipe_close


def test_close_from_another_thread_cancels_then_waits_for_drain():
    native = PendingNative()
    pipe = pipe_mod.WindowsPipe(native, 7, lambda: False)
    errors = []
    reader = threading.Thread(target=lambda: _capture_error(errors, lambda: pipe.read(4, deadline=time.monotonic() + 2)))
    reader.start()
    assert _wait_for(lambda: "begin" in native.actions)
    closer = threading.Thread(target=pipe.close)
    closer.start()
    reader.join(2)
    closer.join(2)
    assert not reader.is_alive() and not closer.is_alive()
    assert ("result", True) in native.actions
    assert native.actions.index(("result", True)) < native.actions.index(("close", 7))


def test_pending_deadline_cancels_and_drains_before_close():
    native = PendingNative()
    pipe = pipe_mod.WindowsPipe(native, 7, lambda: False)
    with pytest.raises(pipe_mod.WindowsPipeTimeout):
        pipe.read(4, deadline=time.monotonic() + 0.02)
    assert ("result", True) in native.actions
    assert native.actions.index(("result", True)) < native.actions.index(("close", 7))


def test_cancel_failure_is_deferred_until_completion_is_observed():
    class CancelFailure(PendingNative):
        def cancel(self, handle, overlapped):
            self.actions.append("cancel-failed")
            raise pipe_mod._NativeFailure(5)

        def result(self, handle, overlapped, *, wait):
            self.actions.append(("result-success", wait))
            return 0

    stopped = threading.Event()
    native = CancelFailure()
    pipe = pipe_mod.WindowsPipe(native, 7, stopped.is_set)
    errors = []
    thread = threading.Thread(
        target=lambda: _capture_error(
            errors,
            lambda: pipe.read(4, deadline=time.monotonic() + 2),
        )
    )
    thread.start()
    assert _wait_for(lambda: "begin" in native.actions)
    stopped.set()
    thread.join(2)
    assert not thread.is_alive()
    assert isinstance(errors[0], pipe_mod.WindowsPipeError)
    assert native.actions.index(("result-success", True)) < native.actions.index(("close", 51))
    assert native.actions.index(("close", 51)) < native.actions.index(("close", 7))


def test_incomplete_drain_retries_before_releasing_owned_storage():
    class IncompleteThenDone(PendingNative):
        def __init__(self):
            super().__init__()
            self.results = 0

        def result(self, handle, overlapped, *, wait):
            self.results += 1
            self.actions.append(("result", wait, self.results))
            if self.results == 1:
                raise pipe_mod._NativeFailure(pipe_mod._ERROR_IO_INCOMPLETE)
            return 0

    stopped = threading.Event()
    native = IncompleteThenDone()
    pipe = pipe_mod.WindowsPipe(native, 7, stopped.is_set)
    errors = []
    thread = threading.Thread(
        target=lambda: _capture_error(
            errors,
            lambda: pipe.read(4, deadline=time.monotonic() + 2),
        )
    )
    thread.start()
    assert _wait_for(lambda: "begin" in native.actions)
    stopped.set()
    thread.join(2)
    assert not thread.is_alive()
    assert isinstance(errors[0], pipe_mod.WindowsPipeCancelled)
    second_result = native.actions.index(("result", True, 2))
    assert native.actions.index(("result", True, 1)) < second_result
    assert second_result < native.actions.index(("close", 51))
    assert native.actions.index(("close", 51)) < native.actions.index(("close", 7))


def test_unexpected_result_failure_is_preserved_but_drain_still_completes():
    class PythonFailureThenDone(PendingNative):
        def __init__(self):
            super().__init__()
            self.results = 0

        def result(self, handle, overlapped, *, wait):
            self.results += 1
            self.actions.append(("result", wait, self.results))
            if self.results == 1:
                raise RuntimeError("injected")
            return 0

    stopped = threading.Event()
    native = PythonFailureThenDone()
    pipe = pipe_mod.WindowsPipe(native, 7, stopped.is_set)
    errors = []
    thread = threading.Thread(
        target=lambda: _capture_error(
            errors,
            lambda: pipe.read(4, deadline=time.monotonic() + 2),
        )
    )
    thread.start()
    assert _wait_for(lambda: "begin" in native.actions)
    stopped.set()
    thread.join(2)
    assert not thread.is_alive()
    assert isinstance(errors[0], pipe_mod.WindowsPipeError)
    second_result = native.actions.index(("result", True, 2))
    assert second_result < native.actions.index(("close", 51))
    assert native.actions.index(("close", 51)) < native.actions.index(("close", 7))


def test_unproven_completion_retries_are_paced(monkeypatch):
    class RepeatedFailures(PendingNative):
        def __init__(self):
            super().__init__()
            self.results = 0

        def result(self, handle, overlapped, *, wait):
            self.results += 1
            self.actions.append(("result", wait, self.results))
            if self.results in (1, 3):
                raise pipe_mod._NativeFailure(pipe_mod._ERROR_IO_INCOMPLETE)
            if self.results == 2:
                raise RuntimeError("injected")
            return 0

    sleeps = []
    monkeypatch.setattr(pipe_mod.time, "sleep", sleeps.append)
    native = RepeatedFailures()
    overlapped = pipe_mod._OVERLAPPED()
    with pytest.raises(RuntimeError, match="injected"):
        pipe_mod.WindowsPipe(native, 7, lambda: False)._cancel_and_drain(7, overlapped)
    assert sleeps == [pipe_mod.POLL_SECONDS] * 3
    assert native.results == 4


def test_interrupted_drain_backoff_waits_for_completion_before_cleanup(monkeypatch):
    class IncompleteThenDone(PendingNative):
        def __init__(self):
            super().__init__()
            self.results = 0

        def result(self, handle, overlapped, *, wait):
            self.results += 1
            self.actions.append(("result", wait, self.results))
            if self.results == 1:
                raise pipe_mod._NativeFailure(pipe_mod._ERROR_IO_INCOMPLETE)
            return 0

    def interrupt(_seconds):
        raise KeyboardInterrupt()

    monkeypatch.setattr(pipe_mod.time, "sleep", interrupt)
    checks = iter([False, True])
    native = IncompleteThenDone()
    pipe = pipe_mod.WindowsPipe(native, 7, lambda: next(checks))
    with pytest.raises(KeyboardInterrupt):
        pipe.read(4, deadline=time.monotonic() + 2)
    second_result = native.actions.index(("result", True, 2))
    assert second_result < native.actions.index(("close", 51))
    assert native.actions.index(("close", 51)) < native.actions.index(("close", 7))


def test_overlapped_allocation_failure_occurs_before_event_ownership(monkeypatch):
    native = FakeNative(reads=[b"x"])
    pipe = pipe_mod.WindowsPipe(native, 7, lambda: False)
    monkeypatch.setattr(
        pipe_mod,
        "_OVERLAPPED",
        lambda: (_ for _ in ()).throw(MemoryError()),
    )
    with pytest.raises(pipe_mod.WindowsPipeError):
        pipe.read(1, deadline=time.monotonic() + 1)
    assert native.next_handle == 50
    assert native.closed == [7]


def test_event_closes_if_overlapped_event_assignment_fails(monkeypatch):
    class RejectEvent:
        @property
        def hEvent(self):
            return None

        @hEvent.setter
        def hEvent(self, _value):
            raise MemoryError()

    native = FakeNative(reads=[b"x"])
    pipe = pipe_mod.WindowsPipe(native, 7, lambda: False)
    monkeypatch.setattr(pipe_mod, "_OVERLAPPED", RejectEvent)
    with pytest.raises(pipe_mod.WindowsPipeError):
        pipe.read(1, deadline=time.monotonic() + 1)
    assert native.closed == [51, 7]
    assert native.reads == [b"x"]  # No native I/O was submitted.


def _capture_error(target, action):
    try:
        action()
    except BaseException as exc:
        target.append(exc)


def _wait_for(predicate, timeout=2.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.005)
    return False


@pytest.mark.skipif(sys.platform != "win32", reason="Windows native named-pipe check")
def test_native_pipe_partial_read_write_server_pid_and_broken_pipe():
    server = start_native_pipe_server("exchange", b"abcdef")
    process = server.process
    try:
        with pipe_mod.connect(server.pipe_name, cancelled=lambda: False, deadline=time.monotonic() + 3) as pipe:
            assert pipe.server_pid() == server.server_pid
            assert pipe.read(6, deadline=time.monotonic() + 2) == b"abc"
            assert pipe.read(6, deadline=time.monotonic() + 2) == b"def"
            pipe.write_all(b"reply", deadline=time.monotonic() + 2)
            process.wait(timeout=4)
            with pytest.raises(pipe_mod.WindowsPipeError):
                pipe.read(1, deadline=time.monotonic() + 1)
        assert process.returncode == 0
    finally:
        if process.poll() is None:
            process.wait(timeout=10)


@pytest.mark.skipif(sys.platform != "win32", reason="Windows native named-pipe check")
def test_native_pending_read_cancellation_closes_cleanly():
    server = start_native_pipe_server("stall")
    process = server.process
    stopped = threading.Event()
    try:
        pipe = pipe_mod.connect(server.pipe_name, cancelled=stopped.is_set, deadline=time.monotonic() + 3)
        errors = []
        reader = threading.Thread(target=lambda: _capture_error(errors, lambda: pipe.read(8, deadline=time.monotonic() + 4)))
        reader.start(); time.sleep(.1); stopped.set(); reader.join(3)
        assert not reader.is_alive()
        assert isinstance(errors[0], pipe_mod.WindowsPipeCancelled)
        process.wait(timeout=5)
    finally:
        if process.poll() is None:
            process.wait(timeout=10)
