import base64
import ctypes
import io
import json
import subprocess
import sys
import threading

import pytest

from utterleaf import windows_clipboard as wc


REAL_WINDOWS = sys.platform == "win32"
_REAL_CREATE_JOB = wc._create_job


class FakeJob:
    def __init__(self, *, assign=True):
        self.assign_ok = assign
        self.assigned = []
        self.close_calls = 0

    def assign(self, process):
        self.assigned.append(process)
        return self.assign_ok

    def close(self):
        self.close_calls += 1
        return True


@pytest.fixture(autouse=True)
def fake_job(monkeypatch):
    job = FakeJob()
    # Parent/job sequencing tests are platform-independent mocks of the Windows
    # branch. Native lifecycle tests remain gated by REAL_WINDOWS below.
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(wc, "_create_job", lambda: job)
    return job


class FakeApi:
    def __init__(self, *, text="old", sequence=10):
        self.text = text
        self.sequence_value = sequence
        self.calls = []
        self.close_ok = True
        self.set_ok = True
        self.empty_ok = True
        self.destroy_ok = True

    def create_window(self):
        self.calls.append("create")
        return 42

    def destroy_window(self, window):
        self.calls.append(("destroy", window))
        return self.destroy_ok

    def open_clipboard(self, window):
        self.calls.append(("open", window))
        return True

    def close_clipboard(self):
        self.calls.append("close")
        return self.close_ok

    def read_text(self):
        self.calls.append("read")
        return self.text

    def sequence(self):
        self.calls.append("sequence")
        return self.sequence_value

    def allocate_text(self, text):
        self.calls.append(("allocate", text))
        return 99

    def free(self, handle):
        self.calls.append(("free", handle))

    def empty(self):
        self.calls.append("empty")
        return self.empty_ok

    def set_text(self, handle):
        self.calls.append(("set", handle))
        if self.set_ok:
            self.sequence_value += 1
        return self.set_ok


def test_result_is_immutable():
    result = wc.Result("ok", "text", 3)
    with pytest.raises(Exception):
        result.status = "changed"


def test_native_snapshot_reads_text_then_sequence_in_one_open_section():
    api = FakeApi(text="previous", sequence=17)
    result = wc._native_snapshot(api)
    assert result == wc.Result("ok", "previous", 17)
    assert api.calls == ["create", ("open", 42), "read", "sequence", "close",
                         ("destroy", 42)]


def test_native_snapshot_failure_closes_and_destroys():
    api = FakeApi(text=None)
    assert wc._native_snapshot(api).status == "unavailable"
    assert "close" in api.calls
    assert ("destroy", 42) in api.calls


def test_native_snapshot_close_failure_discards_receipt():
    api = FakeApi(text="previous", sequence=17)
    api.close_ok = False
    assert wc._native_snapshot(api).status == "unavailable"


def test_native_conditional_write_checks_sequence_before_mutation():
    api = FakeApi(sequence=22)
    result = wc._native_write(api, "private", 21)
    assert result == wc.Result("changed", sequence=22)
    assert not any(call == "empty" or isinstance(call, tuple) and call[0] == "allocate"
                   for call in api.calls)


def test_native_write_transfers_handle_and_returns_receipt():
    api = FakeApi(sequence=8)
    result = wc._native_write(api, "dictation", 8)
    assert result == wc.Result("ok", sequence=9)
    assert api.calls.index("sequence") < api.calls.index(("allocate", "dictation"))
    assert api.calls.index("empty") < api.calls.index(("set", 99))
    assert ("free", 99) not in api.calls
    assert api.calls[-2:] == ["close", ("destroy", 42)]


def test_native_write_frees_untransferred_handle_and_reports_uncertain_after_empty():
    api = FakeApi()
    api.set_ok = False
    result = wc._native_write(api, "dictation", None)
    assert result.status == "uncertain"
    assert ("free", 99) in api.calls


def test_native_empty_failure_is_uncertain_and_frees_handle():
    api = FakeApi()
    api.empty_ok = False
    result = wc._native_write(api, "dictation", None)
    assert result.status == "uncertain"
    assert ("set", 99) not in api.calls
    assert ("free", 99) in api.calls


def test_native_write_close_failure_makes_confirmed_write_uncertain():
    api = FakeApi()
    api.close_ok = False
    assert wc._native_write(api, "dictation", None).status == "uncertain"


def test_native_write_destroy_failure_makes_confirmed_write_uncertain():
    api = FakeApi()
    api.destroy_ok = False
    assert wc._native_write(api, "dictation", None).status == "uncertain"


@pytest.mark.parametrize("text", [
    "a\0b", "x" * (wc.MAX_TEXT_BYTES + 1), "\ud800",
], ids=["embedded-nul", "oversize", "lone-surrogate"])
def test_write_rejects_invalid_text_before_start(monkeypatch, text):
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: pytest.fail("launched"))
    assert wc.write(text).status == "unavailable"


def test_cancelled_before_start_never_launches(monkeypatch):
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: pytest.fail("launched"))
    assert wc.snapshot(cancel=lambda: True).status == "cancelled"
    assert wc.write("secret", cancel=lambda: True).status == "cancelled"


def test_job_setup_failure_never_launches(monkeypatch):
    monkeypatch.setattr(wc, "_create_job", lambda: None)
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: pytest.fail("launched"))
    assert wc.write("secret").status == "unavailable"


class FakeFunction:
    def __init__(self, implementation):
        self.implementation = implementation

    def __call__(self, *args):
        return self.implementation(*args)


def test_job_is_unnamed_noninheritable_and_kill_on_close(monkeypatch):
    calls = []

    class Kernel:
        pass

    kernel = Kernel()
    kernel.CreateJobObjectW = FakeFunction(
        lambda security, name: calls.append(("create", security, name)) or 55)

    def set_limits(handle, info_class, info, size):
        limits = ctypes.cast(info, ctypes.POINTER(wc._EXTENDED_JOB_LIMITS)).contents
        calls.append(("set", handle.value, info_class,
                      limits.BasicLimitInformation.LimitFlags, size))
        return 1

    kernel.SetInformationJobObject = FakeFunction(set_limits)
    kernel.AssignProcessToJobObject = FakeFunction(lambda job, process: 1)
    kernel.CloseHandle = FakeFunction(
        lambda handle: calls.append(("close", handle.value)) or 1)
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(wc.ctypes, "WinDLL", lambda *a, **k: kernel, raising=False)
    job = _REAL_CREATE_JOB()
    assert job is not None
    assert calls[0] == ("create", None, None)
    assert calls[1][0:4] == ("set", 55, 9, 0x00002000)
    assert job.close()
    assert calls[-1] == ("close", 55)


@pytest.mark.parametrize("failure", ["false", "exception", "wrapper"])
def test_job_setup_failure_closes_created_handle(monkeypatch, failure):
    calls = []

    class Kernel:
        pass

    kernel = Kernel()
    kernel.CreateJobObjectW = FakeFunction(lambda security, name: 77)

    def set_limits(*args):
        if failure == "exception":
            raise OSError("set failed")
        return 0 if failure == "false" else 1

    kernel.SetInformationJobObject = FakeFunction(set_limits)
    kernel.AssignProcessToJobObject = FakeFunction(lambda job, process: 1)
    kernel.CloseHandle = FakeFunction(
        lambda handle: calls.append(handle.value) or 1)
    monkeypatch.setattr(wc.ctypes, "WinDLL", lambda *a, **k: kernel, raising=False)
    if failure == "wrapper":
        monkeypatch.setattr(wc, "_WindowsJob",
                            lambda *a, **k: (_ for _ in ()).throw(MemoryError()))
    assert _REAL_CREATE_JOB() is None
    assert calls == [77]


def test_request_protocol_uses_bounded_base64_and_round_trips_unicode():
    text = "héllo 🪶\n"
    frame = json.dumps({
        "v": 1, "op": "write",
        "text_b64": base64.b64encode(text.encode()).decode(),
        "expected_sequence": 5,
    }, separators=(",", ":")).encode() + b"\n"
    assert wc._decode_request(frame) == ("write", text, 5)
    response = wc._encode_result(wc.Result("ok", text, 7))
    assert wc._parse_response(response, "snapshot") == wc.Result("ok", text, 7)


@pytest.mark.parametrize("raw", [
    b"", b"{}\n", b'{"v":2,"op":"snapshot"}\n',
    b'{"v":true,"op":"snapshot"}\n',
    b'{"v":1,"v":1,"op":"snapshot"}\n',
    b'{"v":1,"op":"snapshot","extra":1}\n',
    b'{"v":1,"op":"write","text_b64":"%%%"}\n',
])
def test_invalid_requests_are_rejected(raw):
    assert wc._decode_request(raw) is None


def test_invalid_worker_input_never_constructs_win32(monkeypatch):
    stdin = io.BytesIO(b'{"v":1,"op":"snapshot","extra":true}\n')
    stdout = io.BytesIO()
    monkeypatch.setattr(sys, "stdin", stdin)
    monkeypatch.setattr(sys, "stdout", stdout)
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(wc, "_win_api", lambda: pytest.fail("clipboard accessed"))
    assert wc.run_worker() == 2
    assert json.loads(stdout.getvalue())["status"] == "unavailable"


def test_worker_rejects_trailing_frame_without_clipboard_access(monkeypatch):
    stdin = io.BytesIO(b'{"v":1,"op":"snapshot"}\nX')
    stdout = io.BytesIO()
    monkeypatch.setattr(sys, "stdin", stdin)
    monkeypatch.setattr(sys, "stdout", stdout)
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(wc, "_win_api", lambda: pytest.fail("clipboard accessed"))
    assert wc.run_worker() == 2


class CaptureInput:
    def __init__(self):
        self.data = b""
        self.closed = False

    def write(self, value):
        self.data += value
        return len(value)

    def close(self):
        self.closed = True


class FakeProcess:
    def __init__(self, output):
        self.stdin = CaptureInput()
        self.stdout = io.BytesIO(output)
        self.returncode = 0
        self._handle = 123
        self.terminated = False
        self.killed = False

    def poll(self):
        return self.returncode

    def wait(self, timeout=None):
        return self.returncode

    def terminate(self):
        self.terminated = True
        self.returncode = -15

    def kill(self):
        self.killed = True
        self.returncode = -9


def test_assignment_failure_sends_no_payload_and_cleans_owned_child(monkeypatch):
    process = BlockingProcess()
    job = FakeJob(assign=False)
    monkeypatch.setattr(wc, "_create_job", lambda: job)
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: process)
    assert wc.write("secret").status == "unavailable"
    assert process.stdin.data == b""
    assert process.terminated
    assert process.stdin.closed
    assert job.close_calls >= 1


def test_parent_command_and_process_metadata_do_not_contain_text(monkeypatch):
    response = wc._encode_result(wc.Result("ok", sequence=44))
    process = FakeProcess(response)
    seen = {}

    def popen(command, **kwargs):
        seen["command"] = command
        seen["kwargs"] = kwargs
        return process

    monkeypatch.setattr(subprocess, "Popen", popen)
    secret = "never in argv or environment"
    assert wc.write(secret) == wc.Result("ok", sequence=44)
    assert secret not in repr(seen)
    assert secret.encode() not in process.stdin.data  # encoded, not plaintext
    decoded = wc._decode_request(process.stdin.data)
    assert decoded == ("write", secret, None)
    assert seen["kwargs"]["stderr"] is subprocess.DEVNULL
    assert seen["kwargs"]["shell"] is False
    assert seen["kwargs"]["close_fds"] is True


def test_job_is_retained_until_normal_child_exit(monkeypatch):
    events = []
    process = FakeProcess(wc._encode_result(wc.Result("ok", sequence=44)))
    original_wait = process.wait

    def wait(timeout=None):
        events.append("wait")
        return original_wait(timeout)

    process.wait = wait

    class OrderedJob(FakeJob):
        def close(self):
            events.append("job-close")
            return super().close()

    job = OrderedJob()
    monkeypatch.setattr(wc, "_create_job", lambda: job)
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: process)
    assert wc.write("private").status == "ok"
    assert events.index("wait") < events.index("job-close")


def test_parent_rejects_oversized_stdout(monkeypatch):
    process = FakeProcess(b"x" * (wc.MAX_FRAME_BYTES + 1))
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: process)
    assert wc.snapshot().status == "unavailable"


@pytest.mark.parametrize("payload", [
    b'{"v":1,"status":[]}\n',
    b'{"v":1,"status":{}}\n',
])
def test_parent_rejects_non_string_status_without_raising(payload):
    assert wc._parse_response(payload, "write") is None


def test_parent_rejects_excessively_nested_json_without_raising():
    payload = (b"[" * 2000) + b"0" + (b"]" * 2000) + b"\n"
    assert wc._parse_response(payload, "snapshot") is None
    assert wc._decode_request(payload) is None


def test_cancel_observed_after_confirmed_write_is_uncertain(monkeypatch):
    process = FakeProcess(wc._encode_result(wc.Result("ok", sequence=44)))
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: process)
    checks = iter([False, False, False, True])
    assert wc.write("private", cancel=lambda: next(checks, True)).status == "uncertain"


class BlockingOutput:
    def __init__(self, unblock):
        self.unblock = unblock
        self.closed = threading.Event()
        self.close_thread = None

    def read(self, size):
        self.unblock.wait(2)
        raise OSError("closed")

    def close(self):
        self.close_thread = threading.get_ident()
        self.closed.set()


class BlockingProcess(FakeProcess):
    def __init__(self):
        super().__init__(b"")
        self.unblock = threading.Event()
        self.stdout = BlockingOutput(self.unblock)
        self.returncode = None

    def terminate(self):
        super().terminate()
        self.unblock.set()

    def kill(self):
        super().kill()
        self.unblock.set()

    def wait(self, timeout=None):
        if self.returncode is None:
            raise subprocess.TimeoutExpired("worker", timeout)
        return self.returncode


def test_actual_deadline_stops_worker_and_returns_uncertain(monkeypatch):
    process = BlockingProcess()
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: process)
    monkeypatch.setattr(wc, "OPERATION_TIMEOUT_SECONDS", 0.02)
    assert wc.write("private").status == "uncertain"
    assert process.terminated


class EscalatingProcess(BlockingProcess):
    def terminate(self):
        self.terminated = True

    def wait(self, timeout=None):
        if self.killed:
            self.returncode = -9
            return self.returncode
        raise subprocess.TimeoutExpired("worker", timeout)

    def kill(self):
        self.killed = True
        self.unblock.set()


def test_deadline_escalates_from_terminate_to_kill(monkeypatch):
    process = EscalatingProcess()
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: process)
    monkeypatch.setattr(wc, "OPERATION_TIMEOUT_SECONDS", 0.02)
    assert wc.write("private").status == "uncertain"
    assert process.terminated and process.killed


class FailedReapProcess(EscalatingProcess):
    def wait(self, timeout=None):
        raise subprocess.TimeoutExpired("worker", timeout)


def test_failed_reap_is_not_reported_as_success(monkeypatch):
    process = FailedReapProcess()
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: process)
    monkeypatch.setattr(wc, "OPERATION_TIMEOUT_SECONDS", 0.02)
    assert wc.write("private").status == "uncertain"
    assert process.terminated and process.killed


def test_write_cancellation_after_launch_stops_and_reaps_as_uncertain(monkeypatch):
    process = BlockingProcess()
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: process)
    checks = iter([False, False, False, True])
    result = wc.write("private", cancel=lambda: next(checks, True))
    assert result.status == "uncertain"
    assert process.terminated
    assert process.returncode is not None
    assert process.stdout.closed.is_set()
    assert process.stdout.close_thread != threading.get_ident()


def test_cancellation_closes_job_before_process_fallback(monkeypatch):
    events = []

    class OrderedProcess(BlockingProcess):
        def terminate(self):
            events.append("terminate")
            super().terminate()

    class OrderedJob(FakeJob):
        def close(self):
            events.append("job-close")
            return super().close()

    process = OrderedProcess()
    monkeypatch.setattr(wc, "_create_job", lambda: OrderedJob())
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: process)
    checks = iter([False, False, False, True])
    assert wc.write("private", cancel=lambda: next(checks, True)).status == "uncertain"
    assert events.index("job-close") < events.index("terminate")


def test_snapshot_cancellation_after_launch_is_unavailable(monkeypatch):
    process = BlockingProcess()
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: process)
    checks = iter([False, False, False, True])
    assert wc.snapshot(cancel=lambda: next(checks, True)).status == "unavailable"
    assert process.terminated


class BlockingInput(CaptureInput):
    def __init__(self, unblock):
        super().__init__()
        self.unblock = unblock
        self.write_thread = None
        self.close_thread = None

    def write(self, value):
        self.write_thread = threading.get_ident()
        self.unblock.wait(2)
        raise OSError("child exited")

    def close(self):
        self.close_thread = threading.get_ident()
        self.closed = True


class BlockingWriterProcess(BlockingProcess):
    def __init__(self):
        super().__init__()
        self.stdin = BlockingInput(self.unblock)
        self.stdout = io.BytesIO()


def test_blocked_writer_is_closed_only_by_io_owner_after_child_stop(monkeypatch):
    process = BlockingWriterProcess()
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: process)
    checks = iter([False, False, False, True])
    assert wc.write("private", cancel=lambda: next(checks, True)).status == "uncertain"
    assert process.stdin.closed
    assert process.stdin.close_thread == process.stdin.write_thread


def test_thread_start_failure_stops_child_and_closes_unowned_pipes(monkeypatch, fake_job):
    process = BlockingProcess()
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: process)

    class FailedThread:
        def __init__(self, *args, **kwargs):
            pass

        def start(self):
            raise RuntimeError("thread unavailable")

    monkeypatch.setattr(threading, "Thread", FailedThread)
    assert wc.write("private").status == "unavailable"
    assert process.terminated
    assert process.stdin.data == b""
    assert process.stdin.closed
    assert process.stdout.closed.is_set()
    assert fake_job.close_calls >= 1


def test_worker_with_windowed_missing_stdio_fails_without_native_access(monkeypatch):
    monkeypatch.setattr(sys, "stdin", None)
    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(wc, "_win_api", lambda: pytest.fail("clipboard accessed"))
    assert wc.run_worker() == 2


def test_source_and_frozen_commands(monkeypatch):
    monkeypatch.setattr(sys, "executable", "utterleaf.exe")
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    assert wc._child_command() == ["utterleaf.exe", "-m", "utterleaf", "--clipboard-worker"]
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    assert wc._child_command() == ["utterleaf-cli.exe", "--clipboard-worker"]


@pytest.mark.skipif(not REAL_WINDOWS, reason="Windows job-object lifecycle")
def test_native_job_close_terminates_owned_sleeping_child():
    job = _REAL_CREATE_JOB()
    assert job is not None
    child = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(30)"],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL, close_fds=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    try:
        if not job.assign(child):
            pytest.skip("host job policy prevents nested assignment")
        assert job.close()
        child.wait(timeout=3)
    finally:
        job.close()
        if child.poll() is None:
            child.kill()
            child.wait(timeout=3)


@pytest.mark.skipif(not REAL_WINDOWS, reason="Windows job-object lifecycle")
def test_native_abrupt_parent_exit_terminates_assigned_sleeping_child():
    script = r'''import os, subprocess, sys
from utterleaf.windows_clipboard import _create_job
job = _create_job()
child = subprocess.Popen(
    [sys.executable, "-c", "import time; time.sleep(30)"],
    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL, close_fds=True,
    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
if job is None or not job.assign(child):
    child.kill()
    child.wait()
    print("skip", flush=True)
    raise SystemExit(0)
print(child.pid, flush=True)
if sys.stdin.readline() != "exit\n":
    child.kill()
    child.wait()
    raise SystemExit(2)
os._exit(0)
'''
    parent = subprocess.Popen(
        [sys.executable, "-c", script], stdin=subprocess.PIPE,
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
        close_fds=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))

    def stop_parent():
        if parent.poll() is not None:
            return
        parent.terminate()
        try:
            parent.wait(timeout=3)
        except subprocess.TimeoutExpired:
            parent.kill()
            parent.wait(timeout=3)

    line_holder = []
    read_done = threading.Event()

    def read_pid():
        try:
            assert parent.stdout is not None
            line_holder.append(parent.stdout.readline(64).strip())
        finally:
            read_done.set()

    reader = threading.Thread(target=read_pid, daemon=True)
    reader.start()
    if not read_done.wait(3):
        stop_parent()
        reader.join(timeout=3)
        pytest.fail("job-owning parent did not report its child")
    reader.join(timeout=3)
    assert not reader.is_alive()
    if not line_holder:
        stop_parent()
        pytest.fail("job-owning parent produced no child receipt")
    line = line_holder[0]
    if line == "skip":
        assert parent.wait(timeout=3) == 0
        pytest.skip("host job policy prevents nested assignment")

    # Acquire an exact kernel process object while the parent and child are both
    # still alive. Keeping this handle prevents PID reuse from redirecting either
    # the wait or the failure cleanup to an unrelated process.
    if not line.isdecimal():
        stop_parent()
        pytest.fail("job-owning parent produced an invalid child receipt")
    pid = int(line)
    from ctypes import wintypes
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = ctypes.c_void_p
    kernel32.WaitForSingleObject.argtypes = [ctypes.c_void_p, wintypes.DWORD]
    kernel32.WaitForSingleObject.restype = wintypes.DWORD
    kernel32.TerminateProcess.argtypes = [ctypes.c_void_p, wintypes.UINT]
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    child_handle = kernel32.OpenProcess(0x00100001, False, pid)  # SYNCHRONIZE | TERMINATE
    if not child_handle:
        stop_parent()
        pytest.fail("could not acquire the owned child process handle")
    try:
        assert parent.stdin is not None
        parent.stdin.write("exit\n")
        parent.stdin.flush()
        parent.stdin.close()
        assert parent.wait(timeout=3) == 0
        result = kernel32.WaitForSingleObject(child_handle, 3000)
        if result != 0:
            kernel32.TerminateProcess(child_handle, 1)
            kernel32.WaitForSingleObject(child_handle, 3000)
        assert result == 0
    finally:
        stop_parent()
        kernel32.CloseHandle(child_handle)
