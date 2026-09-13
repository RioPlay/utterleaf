from __future__ import annotations

import ctypes
import os
from pathlib import Path
import socket
import struct
import subprocess
import sys
import threading
import time

import pytest

from utterleaf import windows_peer_identity as identity


class FakeSocket:
    def __init__(self, family=socket.AF_INET) -> None:
        self.family = family

    def getsockname(self):
        if self.family == socket.AF_INET:
            return ("127.0.0.1", 51000)
        return ("::1", 51000, 0, 0)

    def getpeername(self):
        if self.family == socket.AF_INET:
            return ("127.0.0.1", 4455)
        return ("::1", 4455, 0, 0)


class FakeNative:
    def __init__(self) -> None:
        self.rows = [(123,), (123,)]
        self.alive = [True, True]
        self.closed: list[int] = []
        self.same_identity = True
        self.same_token = True
        self.image_path = r"C:\OBS\bin\64bit\obs64.exe"
        self.opened_files: list[str] = []
        self.open_process_calls: list[int] = []

    def tcp_peer_pids(self, endpoint):
        return self.rows.pop(0)

    def open_process(self, pid):
        assert pid == 123
        self.open_process_calls.append(pid)
        return 20

    def process_alive(self, handle):
        assert handle == 20
        return self.alive.pop(0)

    def process_creation_time(self, handle):
        return 987654321

    def same_user_and_session(self, handle):
        return self.same_token

    def process_image_path(self, handle):
        return self.image_path

    def open_file(self, path):
        self.opened_files.append(path)
        expected = identity._FileIdentity(
            r"\\?\c:\obs\bin\64bit\obs64.exe", 7, b"i" * 16
        )
        if not self.same_identity:
            expected = identity._FileIdentity(expected.final_path, 8, b"j" * 16)
        return 30, expected

    def close_handle(self, handle):
        self.closed.append(handle)


def expected_lease(native: FakeNative) -> identity.ExpectedExecutableLease:
    expected = identity._FileIdentity(
        r"\\?\c:\obs\bin\64bit\obs64.exe", 7, b"i" * 16
    )
    return identity.ExpectedExecutableLease(  # type: ignore[arg-type]
        native, 10, expected, r"C:\OBS\bin\64bit\obs64.exe"
    )


def test_structure_sizes_and_table_offsets_match_windows_abi() -> None:
    assert ctypes.sizeof(identity._MIB_TCPROW_OWNER_PID) == 24
    assert ctypes.sizeof(identity._MIB_TCP6ROW_OWNER_PID) == 56
    assert ctypes.sizeof(identity._FILE_ID_INFO) == 24
    assert identity._MIB_TCPTABLE_OWNER_PID_ONE.table.offset == 4
    assert identity._MIB_TCP6TABLE_OWNER_PID_ONE.table.offset == 4


def test_verify_and_revalidate_own_process_handle_separately() -> None:
    native = FakeNative()
    expected = expected_lease(native)
    peer = expected.verify(
        FakeSocket(), cancelled=lambda: False, deadline=time.monotonic() + 1
    )
    assert peer.pid == 123
    assert peer.creation_time == 987654321
    assert repr(expected) == "ExpectedExecutableLease()"
    assert repr(peer) == "VerifiedPeerLease()"
    assert native.closed == [30]
    assert native.opened_files == [r"C:\OBS\bin\64bit\obs64.exe"]
    native.rows.append((123,))
    native.alive.extend([True, True])
    peer.revalidate(cancelled=lambda: False, deadline=time.monotonic() + 1)
    peer.close()
    peer.close()
    assert native.closed == [30, 20]
    expected.close()
    expected.close()
    assert native.closed == [30, 20, 10]


@pytest.mark.parametrize(
    "rows",
    [
        [(123, 456)],
        [(123,), (456,)],
        [(0,)],
        [(4,)],
    ],
    ids=["ambiguous", "pid-changed", "idle-pid", "system-pid"],
)
def test_verify_rejects_ambiguous_changed_or_reserved_pid_and_closes(rows) -> None:
    native = FakeNative()
    native.rows = list(rows)
    process_was_opened = rows[0] == (123,)
    expected = expected_lease(native)
    with pytest.raises(identity.PeerIdentityError):
        expected.verify(
            FakeSocket(), cancelled=lambda: False, deadline=time.monotonic() + 0.1
        )
    if process_was_opened:
        assert 20 in native.closed
    else:
        assert native.open_process_calls == []
    expected.close()


@pytest.mark.parametrize("attribute", ["same_identity", "same_token"])
def test_verify_rejects_wrong_file_or_token_and_closes_process(attribute) -> None:
    native = FakeNative()
    setattr(native, attribute, False)
    expected = expected_lease(native)
    with pytest.raises(identity.PeerIdentityError) as caught:
        expected.verify(
            FakeSocket(), cancelled=lambda: False, deadline=time.monotonic() + 1
        )
    assert str(caught.value) == "OBS peer identity verification failed"
    assert 20 in native.closed
    expected.close()


@pytest.mark.parametrize(
    "reported",
    [
        r"\\server\share\obs64.exe",
        r"\\?\C:\OBS\bin\64bit\obs64.exe",
        r"\\.\C:\OBS\bin\64bit\obs64.exe",
        r"C:\Other\obs64.exe",
        r"C:\OBS\bin\64bit\..\obs64.exe",
    ],
    ids=["unc", "extended-device", "device", "different-local", "parent-component"],
)
def test_reported_image_is_rejected_lexically_before_any_candidate_open(reported) -> None:
    native = FakeNative()
    native.image_path = reported
    expected = expected_lease(native)
    with pytest.raises(identity.PeerIdentityError):
        expected.verify(
            FakeSocket(), cancelled=lambda: False, deadline=time.monotonic() + 1
        )
    assert native.opened_files == []
    assert 20 in native.closed
    expected.close()


def test_verify_rejects_process_exit_at_either_liveness_check() -> None:
    for alive in ([False], [True, False]):
        native = FakeNative()
        native.alive = list(alive)
        expected = expected_lease(native)
        with pytest.raises(identity.PeerIdentityError):
            expected.verify(
                FakeSocket(), cancelled=lambda: False, deadline=time.monotonic() + 1
            )
        assert 20 in native.closed
        expected.close()


def test_missing_row_obeys_shared_deadline() -> None:
    native = FakeNative()
    native.rows = [()] * 20
    expected = expected_lease(native)
    started = time.monotonic()
    with pytest.raises(identity.PeerIdentityError):
        expected.verify(
            FakeSocket(), cancelled=lambda: False, deadline=time.monotonic() + 0.025
        )
    assert time.monotonic() - started < 0.2
    expected.close()


def test_cancellation_is_distinct_and_callback_failure_is_sanitized() -> None:
    expected = expected_lease(FakeNative())
    with pytest.raises(identity.PeerIdentityCancelled):
        expected.verify(FakeSocket(), cancelled=lambda: True, deadline=time.monotonic() + 1)

    def failed_check() -> bool:
        raise RuntimeError("private callback value")

    with pytest.raises(identity.PeerIdentityError) as caught:
        expected.verify(FakeSocket(), cancelled=failed_check, deadline=time.monotonic() + 1)
    assert str(caught.value) == "OBS peer identity verification failed"
    assert caught.value.__cause__ is None
    expected.close()


def test_late_cancellation_cannot_return_a_verified_or_revalidated_lease() -> None:
    native = FakeNative()
    expected = expected_lease(native)
    checks = 0

    def cancel_after_final_check() -> bool:
        nonlocal checks
        checks += 1
        return checks >= 4

    with pytest.raises(identity.PeerIdentityCancelled):
        expected.verify(
            FakeSocket(),
            cancelled=cancel_after_final_check,
            deadline=time.monotonic() + 1,
        )
    assert 20 in native.closed

    native = FakeNative()
    peer = identity.VerifiedPeerLease(
        native, 20, 123, 5, identity._socket_tuple(FakeSocket())  # type: ignore[arg-type]
    )
    checks = 0

    def cancel_revalidation_at_end() -> bool:
        nonlocal checks
        checks += 1
        return checks >= 3

    with pytest.raises(identity.PeerIdentityCancelled):
        peer.revalidate(
            cancelled=cancel_revalidation_at_end, deadline=time.monotonic() + 1
        )
    peer.close()
    expected.close()


@pytest.mark.parametrize(
    "stage", ["same_user_and_session", "process_image_path", "open_file"]
)
def test_cancellation_between_native_stages_stops_and_closes_handles(stage) -> None:
    native = FakeNative()
    expected = expected_lease(native)
    switched = threading.Event()
    original = getattr(native, stage)

    def switch_after_call(*args):
        result = original(*args)
        switched.set()
        return result

    setattr(native, stage, switch_after_call)
    with pytest.raises(identity.PeerIdentityCancelled):
        expected.verify(
            FakeSocket(),
            cancelled=switched.is_set,
            deadline=time.monotonic() + 1,
        )
    assert 20 in native.closed
    if stage == "open_file":
        assert 30 in native.closed
    else:
        assert native.opened_files == []
    expected.close()
    assert 10 in native.closed


@pytest.mark.parametrize(
    "family,local,peer",
    [
        (socket.AF_INET, ("0.0.0.0", 50000), ("127.0.0.1", 4455)),
        (socket.AF_INET, ("127.0.0.1", 50000), ("127.0.0.2", 4455)),
        (socket.AF_INET6, ("::1", 50000, 1, 0), ("::1", 4455, 0, 0)),
        (socket.AF_INET6, ("::1", 50000, 0, 1), ("::1", 4455, 0, 0)),
    ],
)
def test_socket_tuple_rejects_nonloopback_flow_or_scope(family, local, peer) -> None:
    class Socket:
        def __init__(self):
            self.family = family

        def getsockname(self):
            return local

        def getpeername(self):
            return peer

    with pytest.raises(identity.PeerIdentityError):
        identity._socket_tuple(Socket())  # type: ignore[arg-type]


def _tcp_buffer(family: int, *, count: int = 1, client_side: bool = False) -> bytes:
    if family == socket.AF_INET:
        row = identity._MIB_TCPROW_OWNER_PID()
        row.dwState = identity._MIB_TCP_STATE_ESTAB
        local_host = "127.0.0.1"
        remote_host = "127.0.0.1"
        row.dwLocalAddr = struct.unpack("=I", socket.inet_pton(family, local_host))[0]
        row.dwRemoteAddr = struct.unpack("=I", socket.inet_pton(family, remote_host))[0]
    else:
        row = identity._MIB_TCP6ROW_OWNER_PID()
        row.dwState = identity._MIB_TCP_STATE_ESTAB
        row.ucLocalAddr[:] = socket.inet_pton(family, "::1")
        row.ucRemoteAddr[:] = socket.inet_pton(family, "::1")
    local_port, remote_port = (51000, 4455) if client_side else (4455, 51000)
    row.dwLocalPort = socket.htons(local_port)
    row.dwRemotePort = socket.htons(remote_port)
    row.dwOwningPid = 321
    table = (
        identity._MIB_TCPTABLE_OWNER_PID_ONE
        if family == socket.AF_INET
        else identity._MIB_TCP6TABLE_OWNER_PID_ONE
    )
    return struct.pack("<I", count) + bytes(row) if table.table.offset == 4 else b""


class FakeTcpApi:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload
        self.calls = 0

    def GetExtendedTcpTable(self, buffer, size, ordered, family, table_class, reserved):
        self.calls += 1
        if buffer is None or size._obj.value < len(self.payload):
            size._obj.value = len(self.payload)
            return identity._ERROR_INSUFFICIENT_BUFFER
        ctypes.memmove(buffer, self.payload, len(self.payload))
        size._obj.value = len(self.payload)
        return identity._NO_ERROR


class GrowingTcpApi(FakeTcpApi):
    def GetExtendedTcpTable(self, buffer, size, ordered, family, table_class, reserved):
        self.calls += 1
        if buffer is None:
            size._obj.value = 4
            return identity._ERROR_INSUFFICIENT_BUFFER
        if size._obj.value < len(self.payload):
            size._obj.value = len(self.payload)
            return identity._ERROR_INSUFFICIENT_BUFFER
        ctypes.memmove(buffer, self.payload, len(self.payload))
        size._obj.value = len(self.payload)
        return identity._NO_ERROR


@pytest.mark.parametrize("family", [socket.AF_INET, socket.AF_INET6])
def test_tcp_table_parses_reversed_tuple_and_grows_buffer(family) -> None:
    native = identity._Native.__new__(identity._Native)
    api = GrowingTcpApi(_tcp_buffer(family))
    native.iphlpapi = api
    endpoint = identity._socket_tuple(FakeSocket(family))
    assert native.tcp_peer_pids(endpoint) == (321,)
    assert api.calls == 3
    api.payload = _tcp_buffer(family, client_side=True)
    assert native.tcp_peer_pids(endpoint) == ()


def test_tcp_table_rejects_count_beyond_returned_buffer() -> None:
    native = identity._Native.__new__(identity._Native)
    native.iphlpapi = FakeTcpApi(_tcp_buffer(socket.AF_INET, count=2))
    with pytest.raises(identity._NativeFailure):
        native.tcp_peer_pids(identity._socket_tuple(FakeSocket()))


def test_tcp_table_rejects_success_size_smaller_than_rows() -> None:
    class ShortSuccess(FakeTcpApi):
        def GetExtendedTcpTable(
            self, buffer, size, ordered, family, table_class, reserved
        ):
            result = super().GetExtendedTcpTable(
                buffer, size, ordered, family, table_class, reserved
            )
            if buffer is not None and result == identity._NO_ERROR:
                size._obj.value = 4
            return result

    native = identity._Native.__new__(identity._Native)
    native.iphlpapi = ShortSuccess(_tcp_buffer(socket.AF_INET))
    with pytest.raises(identity._NativeFailure):
        native.tcp_peer_pids(identity._socket_tuple(FakeSocket()))


def test_tcp_table_rejects_oversized_request_before_allocation(monkeypatch) -> None:
    class OversizedRequest:
        calls = 0

        def GetExtendedTcpTable(
            self, buffer, size, ordered, family, table_class, reserved
        ):
            self.calls += 1
            assert buffer is None
            size._obj.value = identity.MAX_TCP_TABLE_BYTES + 1
            return identity._ERROR_INSUFFICIENT_BUFFER

    api = OversizedRequest()
    native = identity._Native.__new__(identity._Native)
    native.iphlpapi = api
    monkeypatch.setattr(
        identity.ctypes,
        "create_string_buffer",
        lambda size: pytest.fail("oversized TCP table allocation wasn't expected"),
    )
    with pytest.raises(identity._NativeFailure):
        native.tcp_peer_pids(identity._socket_tuple(FakeSocket()))
    assert api.calls == 1


def test_tcp_table_stops_after_three_insufficient_buffer_retries() -> None:
    class NeverEnough:
        calls = 0
        buffer_calls = 0

        def GetExtendedTcpTable(
            self, buffer, size, ordered, family, table_class, reserved
        ):
            self.calls += 1
            if buffer is None:
                size._obj.value = 4
            else:
                self.buffer_calls += 1
                size._obj.value += 1
            return identity._ERROR_INSUFFICIENT_BUFFER

    api = NeverEnough()
    native = identity._Native.__new__(identity._Native)
    native.iphlpapi = api
    with pytest.raises(identity._NativeFailure):
        native.tcp_peer_pids(identity._socket_tuple(FakeSocket()))
    assert api.calls == 1 + identity.TABLE_BUFFER_ATTEMPTS
    assert api.buffer_calls == identity.TABLE_BUFFER_ATTEMPTS == 3


def _token_user_buffer(sid: bytes):
    structure_size = ctypes.sizeof(identity._TOKEN_USER_STRUCT)
    buffer = ctypes.create_string_buffer(structure_size + len(sid))
    token_user = identity._TOKEN_USER_STRUCT.from_buffer(buffer)
    token_user.User.Sid = ctypes.addressof(buffer) + structure_size
    ctypes.memmove(token_user.User.Sid, sid, len(sid))
    return buffer


def test_token_user_sid_is_bounded_by_exact_returned_length() -> None:
    native = identity._Native.__new__(identity._Native)
    sid = b"\x01\x01" + b"\x00\x00\x00\x00\x00\x05" + struct.pack("<I", 21)
    buffer = _token_user_buffer(sid)
    valid = ctypes.sizeof(identity._TOKEN_USER_STRUCT) + len(sid)
    assert native._token_user_sid(buffer, valid) == (
        ctypes.addressof(buffer) + ctypes.sizeof(identity._TOKEN_USER_STRUCT)
    )
    with pytest.raises(identity._NativeFailure):
        native._token_user_sid(buffer, valid - 1)


def test_token_user_sid_rejects_pointer_outside_buffer_and_oversized_sid() -> None:
    native = identity._Native.__new__(identity._Native)
    buffer = _token_user_buffer(b"\x01\x0f" + b"\x00" * 6)
    with pytest.raises(identity._NativeFailure):
        native._token_user_sid(buffer, len(buffer))
    token_user = identity._TOKEN_USER_STRUCT.from_buffer(buffer)
    token_user.User.Sid = ctypes.addressof(buffer) + len(buffer) + 8
    with pytest.raises(identity._NativeFailure):
        native._token_user_sid(buffer, len(buffer))


def test_revalidate_serializes_close_around_handle_use() -> None:
    native = FakeNative()
    entered = threading.Event()
    release = threading.Event()

    def blocked_alive(handle):
        entered.set()
        release.wait(1)
        return True

    native.process_alive = blocked_alive
    native.rows = [(123,)]
    peer = identity.VerifiedPeerLease(
        native, 20, 123, 5, identity._socket_tuple(FakeSocket())  # type: ignore[arg-type]
    )
    check = threading.Thread(
        target=lambda: peer.revalidate(
            cancelled=lambda: False, deadline=time.monotonic() + 1
        )
    )
    check.start()
    assert entered.wait(1)
    closed = threading.Event()
    closer = threading.Thread(target=lambda: (peer.close(), closed.set()))
    closer.start()
    assert not closed.wait(0.02)
    release.set()
    check.join(1)
    closer.join(1)
    assert not check.is_alive() and not closer.is_alive()
    assert native.closed == [20]


def test_non_windows_refuses_before_path_or_native_io(monkeypatch) -> None:
    monkeypatch.setattr(identity.sys, "platform", "linux")
    monkeypatch.setattr(
        identity,
        "require_local_filesystem",
        lambda path: pytest.fail("path inspection wasn't expected"),
    )
    monkeypatch.setattr(identity, "_load_native", lambda: pytest.fail("native load wasn't expected"))
    with pytest.raises(identity.PeerIdentityError):
        identity.open_expected_executable("/tmp/obs64.exe")


@pytest.mark.skipif(sys.platform != "win32", reason="Windows native identity API")
def test_expected_path_rejects_relative_unc_and_device_before_native_load(monkeypatch) -> None:
    monkeypatch.setattr(identity, "_load_native", lambda: pytest.fail("native load wasn't expected"))
    for path in ("obs64.exe", r"\\server\share\obs64.exe", r"\\?\C:\obs64.exe"):
        with pytest.raises(identity.PeerIdentityError):
            identity.open_expected_executable(path)


def _start_python_server(family: int):
    if family == socket.AF_INET6:
        probe = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
        try:
            probe.bind(("::1", 0))
        except OSError as exc:
            unsupported = {
                getattr(os, "EAFNOSUPPORT", 97),
                getattr(os, "EADDRNOTAVAIL", 99),
                10047,
                10049,
            }
            if exc.errno in unsupported or getattr(exc, "winerror", None) in unsupported:
                pytest.skip("IPv6 loopback bind is unavailable")
            raise
        finally:
            probe.close()
    base_python = getattr(sys, "_base_executable", sys.executable)
    code = (
        "import os,socket,threading\n"
        "t=threading.Timer(8,lambda:os._exit(2));t.daemon=True;t.start()\n"
        f"s=socket.socket({family},socket.SOCK_STREAM)\n"
        "s.settimeout(8)\n"
        f"s.bind(({repr('127.0.0.1' if family == socket.AF_INET else '::1')},0))\n"
        "s.listen(1)\n"
        "print(s.getsockname()[1],os.getpid(),flush=True)\n"
        "c,a=s.accept()\n"
        "c.settimeout(8)\n"
        "try:c.recv(1)\n"
        "except (OSError,TimeoutError):pass\n"
        "c.close();s.close()\n"
    )
    child = subprocess.Popen(
        [base_python, "-c", code],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    assert child.stdout is not None
    ready = threading.Event()
    output: list[str] = []

    def read_ready() -> None:
        output.append(child.stdout.readline().strip())
        ready.set()

    reader = threading.Thread(target=read_ready, daemon=True)
    reader.start()
    if not ready.wait(3):
        child.wait(timeout=10)
        reader.join(1)
        pytest.fail("loopback identity child didn't become ready")
    line = output[0]
    if not line:
        child.wait(timeout=10)
        pytest.fail("loopback identity child exited before readiness")
    try:
        port_text, pid_text = line.split()
    except ValueError:
        child.wait(timeout=10)
        pytest.fail("loopback identity child returned invalid readiness data")
    return child, base_python, int(port_text), int(pid_text)


def _finish_child(child, client) -> None:
    try:
        client.sendall(b"x")
    except OSError:
        pass
    client.close()
    child.wait(timeout=10)
    assert child.returncode == 0


@pytest.mark.skipif(sys.platform != "win32", reason="Windows native identity API")
@pytest.mark.parametrize("family", [socket.AF_INET, socket.AF_INET6], ids=["ipv4", "ipv6"])
def test_native_python_server_identity_and_wrong_executable(family) -> None:
    child, base_python, port, child_pid = _start_python_server(family)
    client = socket.socket(family, socket.SOCK_STREAM)
    host = "127.0.0.1" if family == socket.AF_INET else "::1"
    try:
        client.connect((host, port))
        with identity.open_expected_executable(base_python) as expected:
            peer = expected.verify(
                client, cancelled=lambda: False, deadline=time.monotonic() + 2
            )
            try:
                assert peer.pid == child_pid
                assert peer.pid != os.getpid()
                assert peer.creation_time > 0
                peer.revalidate(cancelled=lambda: False, deadline=time.monotonic() + 2)
            finally:
                peer.close()
    finally:
        _finish_child(child, client)


    child, _, port, _ = _start_python_server(family)
    client = socket.socket(family, socket.SOCK_STREAM)
    try:
        client.connect((host, port))
        wrong = Path(os.environ["SystemRoot"]) / "System32" / "cmd.exe"
        with identity.open_expected_executable(wrong) as expected:
            with pytest.raises(identity.PeerIdentityError):
                expected.verify(
                    client, cancelled=lambda: False, deadline=time.monotonic() + 2
                )
    finally:
        _finish_child(child, client)


class RetainNative(FakeNative):
    def __init__(self):
        super().__init__()
        self.rows = [(123,)]
        self.live = True
        self.duplicated = []

    def process_alive(self, handle):
        assert handle in (20, 40)
        return self.live

    def duplicate_process(self, handle):
        self.duplicated.append(handle)
        return 40


def retain_source(native):
    return identity.VerifiedPeerLease(native, 20, 123, 987654321,
                                      identity._socket_tuple(FakeSocket()))


def test_independent_process_lease_survives_tcp_lease_close():
    native = RetainNative()
    peer = retain_source(native)
    retained = peer.retain_process(cancelled=lambda: False, deadline=time.monotonic() + 1)
    assert native.duplicated == [20]
    assert retained.pid == 123 and retained.creation_time == peer.creation_time
    peer.close()
    assert native.closed == [20]
    # No rows remain: consulting TCP again would fail this check.
    retained.verify_pid(123, cancelled=lambda: False, deadline=time.monotonic() + 1)
    assert repr(retained) == "VerifiedProcessLease()"
    retained.close()
    retained.close()
    assert native.closed == [20, 40]
    with pytest.raises(identity.PeerIdentityError):
        retained.verify_pid(123, cancelled=lambda: False, deadline=time.monotonic() + 1)


@pytest.mark.parametrize("failure", ["pid", "exit", "token", "closed"])
def test_independent_process_lease_rejects_identity_loss(failure):
    native = RetainNative()
    with retain_source(native) as peer:
        retained = peer.retain_process(cancelled=lambda: False, deadline=time.monotonic() + 1)
    if failure == "exit":
        native.live = False
    if failure == "token":
        native.same_token = False
    if failure == "closed":
        retained.close()
    try:
        with pytest.raises(identity.PeerIdentityError):
            retained.verify_pid(124 if failure == "pid" else 123,
                                cancelled=lambda: False, deadline=time.monotonic() + 1)
    finally:
        retained.close()
    assert native.closed == [20, 40]


def test_retain_rejects_stale_tcp_before_duplicating():
    native = RetainNative()
    native.rows = [(456,)]
    with retain_source(native) as peer:
        with pytest.raises(identity.PeerIdentityError):
            peer.retain_process(cancelled=lambda: False, deadline=time.monotonic() + 1)
    assert native.duplicated == [] and native.closed == [20]


def test_retain_cancellation_after_duplicate_closes_only_new_handle():
    native = RetainNative()
    with retain_source(native) as peer:
        with pytest.raises(identity.PeerIdentityCancelled):
            peer.retain_process(cancelled=lambda: bool(native.duplicated),
                                deadline=time.monotonic() + 1)
        assert native.closed == [40]
    assert native.closed == [40, 20]


def test_duplicate_native_call_preserves_source_rights_without_inheritance():
    calls = []

    class Kernel:
        def GetCurrentProcess(self):
            return -1

        def DuplicateHandle(self, source_process, source, target_process, out,
                            access, inherit, flags):
            calls.append((source_process, source.value, target_process, access, inherit, flags))
            out._obj.value = 40
            return True

    native = identity._Native.__new__(identity._Native)
    native.kernel32 = Kernel()
    assert native.duplicate_process(20) == 40
    assert calls == [(-1, 20, -1, 0, False, 2)]


@pytest.mark.skipif(sys.platform != "win32", reason="Windows native identity API")
def test_native_process_duplicate_remains_valid_without_tcp_connection():
    retained = None
    with socket.socket() as listener, socket.socket() as client:
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        client.connect(listener.getsockname())
        server, _ = listener.accept()
        with server, identity.open_expected_executable(sys._base_executable) as expected:
            with expected.verify(client, cancelled=lambda: False,
                                 deadline=time.monotonic() + 2) as peer:
                retained = peer.retain_process(cancelled=lambda: False,
                                               deadline=time.monotonic() + 2)
    try:
        retained.verify_pid(os.getpid(), cancelled=lambda: False, deadline=time.monotonic() + 2)
    finally:
        retained.close()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows native identity API")
def test_native_process_duplicate_rejects_original_child_exit():
    child, base_python, port, pid = _start_python_server(socket.AF_INET)
    client = socket.socket()
    retained = None
    try:
        client.connect(("127.0.0.1", port))
        with identity.open_expected_executable(base_python) as expected:
            with expected.verify(client, cancelled=lambda: False,
                                 deadline=time.monotonic() + 2) as peer:
                retained = peer.retain_process(cancelled=lambda: False,
                                               deadline=time.monotonic() + 2)
    finally:
        _finish_child(child, client)
    try:
        with pytest.raises(identity.PeerIdentityError):
            retained.verify_pid(pid, cancelled=lambda: False, deadline=time.monotonic() + 2)
    finally:
        retained.close()
