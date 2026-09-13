from __future__ import annotations

import ctypes
import importlib.util
import io
import os
import subprocess
import sys
import types
from pathlib import Path

import pytest


HELPER_PATH = Path(__file__).with_name("windows_clipboard_isolation.py")
SPEC = importlib.util.spec_from_file_location("windows_clipboard_isolation", HELPER_PATH)
assert SPEC is not None and SPEC.loader is not None
iso = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = iso
SPEC.loader.exec_module(iso)


class FakeApi:
    def __init__(self, identity=None):
        self.identity = identity or iso.Identity("Private-1", "Desk-1", 0, False)
        self.calls = []
        self.station_error = 0
        self.desktop_error = 0
        self.station_handle = 11
        self.desktop_handle = 22

    def current_station(self):
        self.calls.append("current_station")
        return self.station_handle

    def current_desktop(self):
        self.calls.append("current_desktop")
        return self.desktop_handle

    def object_name(self, handle):
        self.calls.append(("name", handle))
        return self.identity.station if handle == self.station_handle else self.identity.desktop

    def station_flags(self, handle):
        self.calls.append(("flags", handle))
        return self.identity.station_flags

    def desktop_is_input(self, handle):
        self.calls.append(("input", handle))
        return self.identity.desktop_is_input

    def create_station(self, name):
        self.calls.append(("create_station", name))
        self.identity = iso.Identity(name, self.identity.desktop,
                                     self.identity.station_flags,
                                     self.identity.desktop_is_input)
        return self.station_handle, self.station_error

    def set_station(self, handle):
        self.calls.append(("set_station", handle))
        return True

    def create_desktop(self, name):
        self.calls.append(("create_desktop", name))
        self.identity = iso.Identity(self.identity.station, name, 0, False)
        return self.desktop_handle, self.desktop_error

    def set_desktop(self, handle):
        self.calls.append(("set_desktop", handle))
        return True

    def close_station(self, handle):
        self.calls.append(("close_station", handle))
        return True

    def close_desktop(self, handle):
        self.calls.append(("close_desktop", handle))
        return True

    def process_in_job(self, process):
        self.calls.append("process_in_job")
        return True


class FakeJob:
    def __init__(self, assign=True):
        self.assign_ok = assign
        self.assigned = []
        self.closed = 0

    def assign(self, process):
        self.assigned.append(process)
        return self.assign_ok

    def close(self):
        self.closed += 1
        return True


class FakeProcess:
    def __init__(self):
        self.returncode = 0
        self.requests = []
        self.waits = []
        self.terminated = 0
        self.killed = 0
        self._handle = 123

    def communicate(self, request, timeout):
        self.requests.append((request, timeout))
        return b"", b""

    def wait(self, timeout):
        self.waits.append(timeout)
        self.returncode = 0
        return 0

    def poll(self):
        return self.returncode

    def terminate(self):
        self.terminated += 1

    def kill(self):
        self.killed += 1

    def close(self):
        pass


class Call:
    def __init__(self, callback):
        self.callback = callback
        self.argtypes = None
        self.restype = None

    def __call__(self, *args):
        return self.callback(*args)


class FakeKernel32:
    def __init__(self, fail=None):
        self.fail = fail
        self.pipe_count = 0
        self.closed = []
        self.terminated = []
        self.waited = []
        self.handle_flags = []
        self.attribute_handles = None
        self.desktop = None
        self.creation_flags = None
        self.attributes_deleted = 0
        self.CreatePipe = Call(self._create_pipe)
        self.SetHandleInformation = Call(self._set_handle_information)
        self.CreateProcessW = Call(self._create_process)
        self.WaitForSingleObject = Call(self._wait)
        self.GetExitCodeProcess = Call(self._exit_code)
        self.TerminateProcess = Call(self._terminate)
        self.CloseHandle = Call(self._close)
        self.InitializeProcThreadAttributeList = Call(self._initialize_attributes)
        self.UpdateProcThreadAttribute = Call(self._update_attributes)
        self.DeleteProcThreadAttributeList = Call(self._delete_attributes)

    @staticmethod
    def _value(handle):
        return int(handle.value if hasattr(handle, "value") else handle)

    def _create_pipe(self, read, write, security, size):
        self.pipe_count += 1
        if self.fail == f"pipe{self.pipe_count}":
            return 0
        first = 10 if self.pipe_count == 1 else 12
        read._obj.value = first
        write._obj.value = first + 1
        return 1

    def _set_handle_information(self, handle, mask, flags):
        self.handle_flags.append((self._value(handle), int(mask), int(flags)))
        return 1

    def _initialize_attributes(self, attributes, count, flags, size):
        size._obj.value = 128
        if attributes is None:
            return 0
        return 0 if self.fail == "attributes" else 1

    def _update_attributes(self, attributes, flags, kind, values, size,
                           previous, returned):
        array = ctypes.cast(values, ctypes.POINTER(ctypes.c_void_p * 2)).contents
        self.attribute_handles = tuple(int(value) for value in array)
        return 0 if self.fail == "handle_list" else 1

    def _create_process(self, application, command, process_security,
                        thread_security, inherit, flags, environment, cwd,
                        startup, info):
        startup_value = ctypes.cast(
            startup, ctypes.POINTER(iso._STARTUPINFOEXW)).contents
        self.desktop = startup_value.StartupInfo.lpDesktop
        self.creation_flags = int(flags)
        if self.fail == "create_process":
            return 0
        info._obj.hProcess = 50
        info._obj.hThread = 51
        return 1

    def _wait(self, handle, milliseconds):
        self.waited.append((self._value(handle), int(milliseconds)))
        return 0

    def _exit_code(self, handle, code):
        code._obj.value = 0
        return 1

    def _terminate(self, handle, code):
        self.terminated.append(self._value(handle))
        return 1

    def _close(self, handle):
        self.closed.append(self._value(handle))
        return 1

    def _delete_attributes(self, attributes):
        self.attributes_deleted += 1


class FakeStream:
    def __init__(self, handle, closed):
        self.handle = handle
        self._closed_handles = closed
        self.closed = False

    def close(self):
        if not self.closed:
            self.closed = True
            self._closed_handles.append(self.handle)


def test_protocol_rejects_malformed_and_oversize_frames():
    assert iso._decode(b"") is None
    assert iso._decode(b"[]\n") is None
    assert iso._decode(b"{bad}\n") is None
    assert iso._decode(b"x" * (iso.MAX_FRAME + 1)) is None
    assert iso._parse_identity({"station": None, "desktop": "Desk",
                                "station_flags": 0,
                                "desktop_is_input": False}) is None


def test_request_reader_rejects_a_trailing_frame(monkeypatch):
    class Input:
        def __init__(self, data):
            self.buffer = io.BytesIO(data)

        def isatty(self):
            return False

    monkeypatch.setattr(sys, "stdin", Input(b'{"v":1,"op":"names"}\n{}\n'))
    assert iso._read_request() is None


def test_malformed_request_reaches_no_native_api(monkeypatch):
    class Input:
        buffer = io.BytesIO(b"{}\nextra")

        @staticmethod
        def isatty():
            return False

    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(sys, "stdin", Input())
    monkeypatch.setattr(iso, "NativeApi", lambda: pytest.fail("native API loaded"))
    assert iso.main(["harness"]) == 2


def test_private_identity_rejects_interactive_or_mismatched_objects():
    assert iso._is_private(iso.Identity("Private", "Desk", 0, False), "Private", "Desk")
    assert not iso._is_private(iso.Identity("WinSta0", "Desk", 0, False))
    assert not iso._is_private(iso.Identity("Private", "Desk", iso.WSF_VISIBLE, False))
    assert not iso._is_private(iso.Identity("Private", "Desk", 0, True))
    assert not iso._is_private(iso.Identity("Private", "Other", 0, False), "Private", "Desk")


def test_nested_receipt_requires_exact_private_identity():
    api = FakeApi()
    request = {"v": iso.VERSION, "op": "identify", "station": "Private-1",
               "desktop": "Desk-1"}
    assert iso._nested_receipt(api, request)["status"] == "ok"
    request["station"] = "WinSta0"
    assert iso._nested_receipt(api, request)["status"] == "failed"


def test_harness_creates_new_private_context_before_nested(monkeypatch):
    api = FakeApi()
    nested_calls = []
    monkeypatch.setattr(iso, "_run_nested",
                        lambda supplied_api, identity: nested_calls.append(identity) or identity)
    receipt = iso._harness_receipt(api)
    assert receipt["status"] == "ok"
    assert api.calls[0][0] == "create_station"
    assert ("set_station", api.station_handle) in api.calls
    assert ("set_desktop", api.desktop_handle) in api.calls
    assert nested_calls and nested_calls[0].station.startswith("UtterleafIsolation-")
    assert not any(call[0].startswith("close_") for call in api.calls if isinstance(call, tuple))


@pytest.mark.parametrize("where", ["station", "desktop"])
def test_harness_rejects_existing_objects_and_closes_unselected_handle(monkeypatch, where):
    api = FakeApi()
    if where == "station":
        api.station_error = iso.ERROR_ALREADY_EXISTS
        api.station_handle = 0
    else:
        api.desktop_error = iso.ERROR_ALREADY_EXISTS
        api.desktop_handle = 0
    monkeypatch.setattr(iso, "_run_nested", lambda *_: pytest.fail("nested child started"))
    assert iso._harness_receipt(api)["status"] == "failed"
    assert not any(isinstance(call, tuple) and call[0].startswith("close_")
                   for call in api.calls)


def test_successful_create_ignores_undefined_stale_last_error(monkeypatch):
    api = FakeApi()
    api.station_error = iso.ERROR_ALREADY_EXISTS
    api.desktop_error = iso.ERROR_ALREADY_EXISTS
    monkeypatch.setattr(iso, "_run_nested", lambda supplied_api, identity: identity)
    assert iso._harness_receipt(api)["status"] == "ok"


def test_named_station_access_denial_is_unavailable_without_retry(monkeypatch):
    api = FakeApi()
    api.station_handle = 0
    api.station_error = iso.ERROR_ACCESS_DENIED
    monkeypatch.setattr(iso, "_run_nested", lambda *_: pytest.fail("nested child started"))
    receipt = iso._harness_receipt(api)
    assert receipt == {"v": iso.VERSION, "status": "unavailable",
                       "reason": "station-create", "win32_error": 5}
    creates = [call for call in api.calls
               if isinstance(call, tuple) and call[0] == "create_station"]
    assert len(creates) == 1
    assert creates[0][1].startswith("UtterleafIsolation-")


def test_nested_launch_uses_explicit_desktop_and_checks_job_before_payload(monkeypatch):
    api = FakeApi()
    process = FakeProcess()
    launched = []
    monkeypatch.setattr(iso, "_popen",
                        lambda mode, desktop=None: launched.append((mode, desktop)) or process)
    nested = iso.Identity("Private-1", "Desk-1", 0, False)
    response = iso._encode({"v": iso.VERSION, "status": "ok", "identity": {
        "station": "Private-1", "desktop": "Desk-1", "station_flags": 0,
        "desktop_is_input": False}})
    monkeypatch.setattr(iso, "_exchange",
                        lambda child, request, timeout: (0, response))
    assert iso._run_nested(api, nested) == nested
    assert launched == [("nested", "Private-1\\Desk-1")]
    assert api.calls[-1] == "process_in_job"


def test_desktop_launch_uses_raw_create_process_owner(monkeypatch):
    sentinel = object()
    calls = []
    monkeypatch.setattr(iso, "_create_bound_process",
                        lambda mode, desktop: calls.append((mode, desktop)) or sentinel)
    monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs:
                        pytest.fail("generic Popen used for bound child"))
    assert iso._popen("nested", desktop="Private\\Desk") is sentinel
    assert calls == [("nested", "Private\\Desk")]


def test_raw_bound_launch_sets_desktop_and_restricts_inheritance(monkeypatch):
    kernel = FakeKernel32()
    stream_handles = []
    monkeypatch.setattr(iso, "_load_kernel32", lambda: kernel)
    monkeypatch.setattr(iso, "_open_pipe_file",
                        lambda handle, flags, mode: FakeStream(handle, stream_handles))
    process = iso._create_bound_process("nested", "Private\\Desk")
    assert kernel.desktop == "Private\\Desk"
    assert kernel.creation_flags & 0x00080000  # EXTENDED_STARTUPINFO_PRESENT
    assert kernel.creation_flags & getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
    assert kernel.attribute_handles == (10, 13)
    assert kernel.handle_flags == [(10, 1, 1), (13, 1, 1),
                                   (11, 1, 0), (12, 1, 0)]
    assert kernel.attributes_deleted == 1
    process.close()
    assert set(kernel.closed + stream_handles) == {10, 11, 12, 13, 50, 51}


@pytest.mark.parametrize("failure", [
    "pipe1", "pipe2", "attributes", "handle_list", "create_process",
    "open_stdin", "open_stdout",
])
def test_raw_bound_launch_failure_closes_every_owned_handle(monkeypatch, failure):
    native_failure = failure if failure not in {"open_stdin", "open_stdout"} else None
    kernel = FakeKernel32(native_failure)
    stream_handles = []
    opens = []

    def open_pipe(handle, flags, mode):
        opens.append(handle)
        if failure == "open_stdin" and len(opens) == 1:
            raise OSError("open failed")
        if failure == "open_stdout" and len(opens) == 2:
            raise OSError("open failed")
        return FakeStream(handle, stream_handles)

    monkeypatch.setattr(iso, "_load_kernel32", lambda: kernel)
    monkeypatch.setattr(iso, "_open_pipe_file", open_pipe)
    with pytest.raises(OSError):
        iso._create_bound_process("nested", "Private\\Desk")
    if failure in {"open_stdin", "open_stdout"}:
        assert kernel.terminated == [50]
        assert any(handle == 50 for handle, _ in kernel.waited)
    created = {10, 11} if failure == "pipe2" else set()
    if failure not in {"pipe1", "pipe2"}:
        created = {10, 11, 12, 13}
    if failure not in {"pipe1", "pipe2", "attributes", "handle_list",
                       "create_process"}:
        created |= {50, 51}
    assert created <= set(kernel.closed + stream_handles)


def test_pipe_wrapper_reports_consumed_handle_without_double_close(monkeypatch):
    closed = []
    monkeypatch.setitem(sys.modules, "msvcrt", types.SimpleNamespace(
        open_osfhandle=lambda handle, flags: 77))
    monkeypatch.setattr(os, "fdopen", lambda *args, **kwargs: (_ for _ in ()).throw(OSError()))
    monkeypatch.setattr(os, "close", closed.append)
    with pytest.raises(iso._PipeOpenError) as caught:
        iso._open_pipe_file(12, os.O_RDONLY, "rb")
    assert caught.value.consumed
    assert closed == [77]


def test_malformed_child_identity_fails_without_escaping(monkeypatch):
    process = FakeProcess()
    job = FakeJob()
    parent = iso.Identity("WinSta0", "Default", iso.WSF_VISIBLE, True)
    malformed = {"station": None, "desktop": "Desk", "station_flags": 0,
                 "desktop_is_input": False}
    response = iso._encode({"v": iso.VERSION, "status": "ok",
                            "harness": malformed, "nested": malformed})
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(iso, "NativeApi", lambda: object())
    monkeypatch.setattr(iso, "_current_identity", lambda api: parent)
    monkeypatch.setattr(iso, "_create_job", lambda: job)
    monkeypatch.setattr(iso, "_popen", lambda *args, **kwargs: process)
    monkeypatch.setattr(iso, "_exchange", lambda *args: (0, response))
    assert iso.run_probe().status == "failed"
    assert job.closed


def test_parent_preserves_bounded_child_failure_diagnostic(monkeypatch):
    process = FakeProcess()
    job = FakeJob()
    parent = iso.Identity("WinSta0", "Default", iso.WSF_VISIBLE, True)
    response = iso._encode({"v": iso.VERSION, "status": "failed",
                            "reason": "desktop-select", "win32_error": 5})
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(iso, "NativeApi", lambda: object())
    monkeypatch.setattr(iso, "_current_identity", lambda api: parent)
    monkeypatch.setattr(iso, "_create_job", lambda: job)
    monkeypatch.setattr(iso, "_popen", lambda *args, **kwargs: process)
    monkeypatch.setattr(iso, "_exchange", lambda *args: (2, response))
    result = iso.run_probe()
    assert result.status == "failed"
    assert (result.reason, result.win32_error) == ("desktop-select", 5)


def test_nested_uncontained_child_gets_no_request(monkeypatch):
    api = FakeApi()
    process = FakeProcess()
    api.process_in_job = lambda child: False
    monkeypatch.setattr(iso, "_popen", lambda *args, **kwargs: process)
    monkeypatch.setattr(iso, "_exchange", lambda *_: pytest.fail("request was sent"))
    with pytest.raises(iso.ProbeFailure):
        iso._run_nested(api, iso.Identity("Private", "Desk", 0, False))
    assert process.requests == []
    assert process.waits


def test_parent_assignment_failure_sends_no_request_and_preserves_identity(monkeypatch):
    process = FakeProcess()
    job = FakeJob(assign=False)
    identity = iso.Identity("WinSta0", "Default", iso.WSF_VISIBLE, True)
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(iso, "NativeApi", lambda: object())
    monkeypatch.setattr(iso, "_current_identity", lambda api: identity)
    monkeypatch.setattr(iso, "_create_job", lambda: job)
    monkeypatch.setattr(iso, "_popen", lambda *args, **kwargs: process)
    monkeypatch.setattr(iso, "_exchange", lambda *_: pytest.fail("request was sent"))
    assert iso.run_probe().status == "unavailable"
    assert process.requests == []
    assert job.closed


def test_parent_launch_failure_closes_unassigned_job(monkeypatch):
    job = FakeJob()
    identity = iso.Identity("WinSta0", "Default", iso.WSF_VISIBLE, True)
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(iso, "NativeApi", lambda: object())
    monkeypatch.setattr(iso, "_current_identity", lambda api: identity)
    monkeypatch.setattr(iso, "_create_job", lambda: job)
    monkeypatch.setattr(iso, "_popen",
                        lambda *args, **kwargs: (_ for _ in ()).throw(OSError()))
    assert iso.run_probe().status == "unavailable"
    assert job.closed == 1


def test_parent_requires_exact_before_after_identity(monkeypatch):
    process = FakeProcess()
    job = FakeJob()
    before = iso.Identity("WinSta0", "Default", iso.WSF_VISIBLE, True)
    after = iso.Identity("Changed", "Default", 0, False)
    identities = iter((before, after))
    private = {"station": "Private", "desktop": "Desk", "station_flags": 0,
               "desktop_is_input": False}
    response = iso._encode({"v": iso.VERSION, "status": "ok",
                            "harness": private, "nested": private})
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(iso, "NativeApi", lambda: object())
    monkeypatch.setattr(iso, "_current_identity", lambda api: next(identities))
    monkeypatch.setattr(iso, "_create_job", lambda: job)
    monkeypatch.setattr(iso, "_popen", lambda *args, **kwargs: process)
    monkeypatch.setattr(iso, "_exchange", lambda *args: (0, response))
    result = iso.run_probe()
    assert result.status == "failed"
    assert result.parent_preserved is False


def test_timeout_closes_job_and_reaps_exact_child(monkeypatch):
    process = FakeProcess()
    job = FakeJob()
    identity = iso.Identity("WinSta0", "Default", iso.WSF_VISIBLE, True)
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(iso, "NativeApi", lambda: object())
    monkeypatch.setattr(iso, "_current_identity", lambda api: identity)
    monkeypatch.setattr(iso, "_create_job", lambda: job)
    monkeypatch.setattr(iso, "_popen", lambda *args, **kwargs: process)
    monkeypatch.setattr(iso, "_exchange",
                        lambda *args: (_ for _ in ()).throw(subprocess.TimeoutExpired("probe", 1)))
    assert iso.run_probe(timeout=0.01).status == "failed"
    assert job.closed
    assert process.waits


def test_probe_source_has_no_clipboard_api_entry_points():
    source = HELPER_PATH.read_text(encoding="utf-8")
    forbidden = [left + right for left, right in (
        ("Open", "Clipboard"), ("Close", "Clipboard"), ("Empty", "Clipboard"),
        ("GetClipboard", "Data"), ("SetClipboard", "Data"))]
    for name in forbidden:
        assert name not in source


@pytest.mark.skipif(
    sys.platform != "win32"
    or os.environ.get("UTTERLEAF_RUN_WINDOWS_CLIPBOARD_ISOLATION") != "1",
    reason="explicit Windows names-only isolation acceptance")
def test_native_names_only_isolation_probe():
    result = iso.run_probe()
    assert result.status == "ok", result
    assert result.parent_preserved
    assert result.harness == result.nested
