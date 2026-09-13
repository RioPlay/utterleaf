"""Fail-closed Windows process identity checks for a connected OBS socket.

Importing this module performs no native calls.  The checks establish operating
system process attribution; they aren't cryptographic attestation of the bytes
historically mapped into a process.
"""

from __future__ import annotations

from collections.abc import Callable
import ctypes
from ctypes import wintypes
from dataclasses import dataclass
import math
import ntpath
from pathlib import Path, PureWindowsPath
import socket
import string
import sys
import threading
import time

from utterleaf.local_filesystem import LocalFilesystemError, require_local_filesystem


_DWORD = ctypes.c_uint32
_ULONG = ctypes.c_uint32
_BOOL = ctypes.c_int32

MAX_TCP_TABLE_BYTES = 16 * 1024 * 1024
MAX_TOKEN_BYTES = 64 * 1024
MAX_PATH_CHARS = 32768
TABLE_BUFFER_ATTEMPTS = 3
TABLE_POLL_SECONDS = 0.02

_NO_ERROR = 0
_ERROR_INSUFFICIENT_BUFFER = 122
_TCP_TABLE_OWNER_PID_CONNECTIONS = 4
_MIB_TCP_STATE_ESTAB = 5
_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
_SYNCHRONIZE = 0x00100000
_TOKEN_QUERY = 0x0008
_TOKEN_USER = 1
_TOKEN_SESSION_ID = 12
_WAIT_OBJECT_0 = 0
_WAIT_TIMEOUT = 258
_FILE_READ_ATTRIBUTES = 0x0080
_FILE_SHARE_READ = 0x0001
_OPEN_EXISTING = 3
_FILE_ATTRIBUTE_NORMAL = 0x0080
_FILE_ID_INFO_CLASS = 18
_INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value


class PeerIdentityError(RuntimeError):
    """The connected peer couldn't be bound to the expected executable."""


class PeerIdentityCancelled(PeerIdentityError):
    """The caller cancelled peer verification."""


class _NativeFailure(Exception):
    pass


class _FILETIME(ctypes.Structure):
    _fields_ = [("dwLowDateTime", _DWORD), ("dwHighDateTime", _DWORD)]


class _FILE_ID_128(ctypes.Structure):
    _fields_ = [("Identifier", ctypes.c_ubyte * 16)]


class _FILE_ID_INFO(ctypes.Structure):
    _fields_ = [
        ("VolumeSerialNumber", ctypes.c_ulonglong),
        ("FileId", _FILE_ID_128),
    ]


class _SID_AND_ATTRIBUTES(ctypes.Structure):
    _fields_ = [("Sid", ctypes.c_void_p), ("Attributes", _DWORD)]


class _TOKEN_USER_STRUCT(ctypes.Structure):
    _fields_ = [("User", _SID_AND_ATTRIBUTES)]


class _MIB_TCPROW_OWNER_PID(ctypes.Structure):
    _fields_ = [
        ("dwState", _DWORD),
        ("dwLocalAddr", _DWORD),
        ("dwLocalPort", _DWORD),
        ("dwRemoteAddr", _DWORD),
        ("dwRemotePort", _DWORD),
        ("dwOwningPid", _DWORD),
    ]


class _MIB_TCP6ROW_OWNER_PID(ctypes.Structure):
    _fields_ = [
        ("ucLocalAddr", ctypes.c_ubyte * 16),
        ("dwLocalScopeId", _DWORD),
        ("dwLocalPort", _DWORD),
        ("ucRemoteAddr", ctypes.c_ubyte * 16),
        ("dwRemoteScopeId", _DWORD),
        ("dwRemotePort", _DWORD),
        ("dwState", _DWORD),
        ("dwOwningPid", _DWORD),
    ]


class _MIB_TCPTABLE_OWNER_PID_ONE(ctypes.Structure):
    _fields_ = [
        ("dwNumEntries", _DWORD),
        ("table", _MIB_TCPROW_OWNER_PID * 1),
    ]


class _MIB_TCP6TABLE_OWNER_PID_ONE(ctypes.Structure):
    _fields_ = [
        ("dwNumEntries", _DWORD),
        ("table", _MIB_TCP6ROW_OWNER_PID * 1),
    ]


@dataclass(frozen=True, repr=False)
class _FileIdentity:
    final_path: str
    volume_serial: int
    file_id: bytes


@dataclass(frozen=True, repr=False)
class _SocketTuple:
    family: int
    local_address: bytes
    local_port: int
    local_scope: int
    peer_address: bytes
    peer_port: int
    peer_scope: int


def _safe_cancelled(cancelled: Callable[[], bool]) -> bool:
    try:
        return bool(cancelled())
    except Exception:
        raise PeerIdentityError("OBS peer identity verification failed") from None


def _check_progress(cancelled: Callable[[], bool], deadline: float) -> None:
    if _safe_cancelled(cancelled):
        raise PeerIdentityCancelled("OBS peer identity verification cancelled")
    if time.monotonic() >= deadline:
        raise PeerIdentityError("OBS peer identity verification failed")


def _validate_controls(cancelled: object, deadline: object) -> None:
    if not callable(cancelled):
        raise PeerIdentityError("OBS peer identity verification failed")
    if type(deadline) not in (int, float) or isinstance(deadline, bool):
        raise PeerIdentityError("OBS peer identity verification failed")
    if not math.isfinite(float(deadline)):
        raise PeerIdentityError("OBS peer identity verification failed")


def _socket_tuple(sock: socket.socket) -> _SocketTuple:
    try:
        family = sock.family
        local = sock.getsockname()
        peer = sock.getpeername()
        if family == socket.AF_INET:
            if len(local) != 2 or len(peer) != 2:
                raise ValueError
            local_host, local_port = local
            peer_host, peer_port = peer
            local_scope = peer_scope = 0
            loopback = socket.inet_pton(socket.AF_INET, "127.0.0.1")
        elif family == socket.AF_INET6:
            if len(local) != 4 or len(peer) != 4:
                raise ValueError
            local_host, local_port, local_flow, local_scope = local
            peer_host, peer_port, peer_flow, peer_scope = peer
            if local_flow != 0 or peer_flow != 0 or local_scope != 0 or peer_scope != 0:
                raise ValueError
            loopback = socket.inet_pton(socket.AF_INET6, "::1")
        else:
            raise ValueError
        local_address = socket.inet_pton(family, local_host)
        peer_address = socket.inet_pton(family, peer_host)
        if local_address != loopback or peer_address != loopback:
            raise ValueError
        if (
            type(local_port) is not int
            or type(peer_port) is not int
            or not 1 <= local_port <= 65535
            or not 1 <= peer_port <= 65535
        ):
            raise ValueError
        return _SocketTuple(
            family,
            local_address,
            local_port,
            local_scope,
            peer_address,
            peer_port,
            peer_scope,
        )
    except Exception:
        raise PeerIdentityError("OBS peer identity verification failed") from None


def _canonical_path(path: str) -> str:
    return ntpath.normcase(ntpath.normpath(path.replace("/", "\\")))


def _canonical_dos_image_path(path: str, *, trusted_final: bool) -> str:
    if type(path) is not str or not path or "\0" in path:
        raise _NativeFailure
    value = path.replace("/", "\\")
    if trusted_final and value.startswith("\\\\?\\"):
        value = value[4:]
    if value.startswith("\\") or value.startswith("\\Device\\"):
        raise _NativeFailure
    drive, tail = ntpath.splitdrive(value)
    if (
        len(drive) != 2
        or drive[1] != ":"
        or drive[0] not in string.ascii_letters
        or not tail.startswith("\\")
        or ":" in tail
        or ".." in PureWindowsPath(value).parts
    ):
        raise _NativeFailure
    return _canonical_path(value)


class _Native:
    def __init__(self) -> None:
        if sys.platform != "win32":
            raise _NativeFailure
        try:
            self.kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            self.advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
            self.iphlpapi = ctypes.WinDLL("iphlpapi", use_last_error=True)
            self._bind()
        except Exception:
            raise _NativeFailure from None

    def _bind(self) -> None:
        handle = ctypes.c_void_p
        self.kernel32.CreateFileW.argtypes = [
            ctypes.c_wchar_p,
            _DWORD,
            _DWORD,
            ctypes.c_void_p,
            _DWORD,
            _DWORD,
            handle,
        ]
        self.kernel32.CreateFileW.restype = handle
        self.kernel32.GetFinalPathNameByHandleW.argtypes = [
            handle,
            ctypes.c_wchar_p,
            _DWORD,
            _DWORD,
        ]
        self.kernel32.GetFinalPathNameByHandleW.restype = _DWORD
        self.kernel32.GetFileInformationByHandleEx.argtypes = [
            handle,
            ctypes.c_int,
            ctypes.c_void_p,
            _DWORD,
        ]
        self.kernel32.GetFileInformationByHandleEx.restype = _BOOL
        self.kernel32.OpenProcess.argtypes = [_DWORD, _BOOL, _DWORD]
        self.kernel32.OpenProcess.restype = handle
        self.kernel32.WaitForSingleObject.argtypes = [handle, _DWORD]
        self.kernel32.WaitForSingleObject.restype = _DWORD
        self.kernel32.GetProcessTimes.argtypes = [
            handle,
            ctypes.POINTER(_FILETIME),
            ctypes.POINTER(_FILETIME),
            ctypes.POINTER(_FILETIME),
            ctypes.POINTER(_FILETIME),
        ]
        self.kernel32.GetProcessTimes.restype = _BOOL
        self.kernel32.QueryFullProcessImageNameW.argtypes = [
            handle,
            _DWORD,
            ctypes.c_wchar_p,
            ctypes.POINTER(_DWORD),
        ]
        self.kernel32.QueryFullProcessImageNameW.restype = _BOOL
        self.kernel32.GetCurrentProcess.argtypes = []
        self.kernel32.GetCurrentProcess.restype = handle
        self.kernel32.DuplicateHandle.argtypes = [
            handle, handle, handle, ctypes.POINTER(handle), _DWORD, _BOOL, _DWORD
        ]
        self.kernel32.DuplicateHandle.restype = _BOOL
        self.kernel32.CloseHandle.argtypes = [handle]
        self.kernel32.CloseHandle.restype = _BOOL
        self.advapi32.OpenProcessToken.argtypes = [
            handle,
            _DWORD,
            ctypes.POINTER(handle),
        ]
        self.advapi32.OpenProcessToken.restype = _BOOL
        self.advapi32.GetTokenInformation.argtypes = [
            handle,
            ctypes.c_int,
            ctypes.c_void_p,
            _DWORD,
            ctypes.POINTER(_DWORD),
        ]
        self.advapi32.GetTokenInformation.restype = _BOOL
        self.advapi32.EqualSid.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        self.advapi32.EqualSid.restype = _BOOL
        self.iphlpapi.GetExtendedTcpTable.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(_DWORD),
            _BOOL,
            _ULONG,
            ctypes.c_int,
            _ULONG,
        ]
        self.iphlpapi.GetExtendedTcpTable.restype = _DWORD

    def close_handle(self, handle: int) -> None:
        try:
            self.kernel32.CloseHandle(ctypes.c_void_p(handle))
        except Exception:
            pass

    def open_file(self, path: str) -> tuple[int, _FileIdentity]:
        handle = self.kernel32.CreateFileW(
            path,
            _FILE_READ_ATTRIBUTES,
            _FILE_SHARE_READ,
            None,
            _OPEN_EXISTING,
            _FILE_ATTRIBUTE_NORMAL,
            None,
        )
        value = int(handle or 0)
        if not value or value == _INVALID_HANDLE_VALUE:
            raise _NativeFailure
        try:
            needed = int(self.kernel32.GetFinalPathNameByHandleW(handle, None, 0, 0))
            if not 1 < needed <= MAX_PATH_CHARS:
                raise _NativeFailure
            buffer = ctypes.create_unicode_buffer(needed)
            length = int(
                self.kernel32.GetFinalPathNameByHandleW(handle, buffer, needed, 0)
            )
            if length <= 0 or length >= needed:
                raise _NativeFailure
            info = _FILE_ID_INFO()
            if not self.kernel32.GetFileInformationByHandleEx(
                handle, _FILE_ID_INFO_CLASS, ctypes.byref(info), ctypes.sizeof(info)
            ):
                raise _NativeFailure
            identity = _FileIdentity(
                _canonical_path(buffer.value),
                int(info.VolumeSerialNumber),
                bytes(info.FileId.Identifier),
            )
            if len(identity.file_id) != 16:
                raise _NativeFailure
            return value, identity
        except BaseException:
            self.close_handle(value)
            raise

    def open_process(self, pid: int) -> int:
        handle = self.kernel32.OpenProcess(
            _PROCESS_QUERY_LIMITED_INFORMATION | _SYNCHRONIZE, False, pid
        )
        value = int(handle or 0)
        if not value:
            raise _NativeFailure
        return value

    def process_alive(self, handle: int) -> bool:
        result = int(self.kernel32.WaitForSingleObject(ctypes.c_void_p(handle), 0))
        if result == _WAIT_TIMEOUT:
            return True
        if result == _WAIT_OBJECT_0:
            return False
        raise _NativeFailure

    def duplicate_process(self, handle: int) -> int:
        current = self.kernel32.GetCurrentProcess()
        duplicate = ctypes.c_void_p()
        if not self.kernel32.DuplicateHandle(
            current, ctypes.c_void_p(handle), current, ctypes.byref(duplicate),
            0, False, 2,  # DUPLICATE_SAME_ACCESS; never inherit or close the source.
        ):
            raise _NativeFailure
        if not duplicate.value or duplicate.value == _INVALID_HANDLE_VALUE:
            raise _NativeFailure
        return int(duplicate.value)

    def process_creation_time(self, handle: int) -> int:
        creation, exited, kernel, user = (_FILETIME() for _ in range(4))
        if not self.kernel32.GetProcessTimes(
            ctypes.c_void_p(handle),
            ctypes.byref(creation),
            ctypes.byref(exited),
            ctypes.byref(kernel),
            ctypes.byref(user),
        ):
            raise _NativeFailure
        result = (int(creation.dwHighDateTime) << 32) | int(creation.dwLowDateTime)
        if result <= 0:
            raise _NativeFailure
        return result

    def process_image_path(self, handle: int) -> str:
        buffer = ctypes.create_unicode_buffer(MAX_PATH_CHARS)
        size = _DWORD(MAX_PATH_CHARS)
        if not self.kernel32.QueryFullProcessImageNameW(
            ctypes.c_void_p(handle), 0, buffer, ctypes.byref(size)
        ):
            raise _NativeFailure
        if not 0 < size.value < MAX_PATH_CHARS:
            raise _NativeFailure
        return buffer.value

    def _open_token(self, process_handle: int) -> int:
        token = ctypes.c_void_p()
        if not self.advapi32.OpenProcessToken(
            ctypes.c_void_p(process_handle), _TOKEN_QUERY, ctypes.byref(token)
        ):
            raise _NativeFailure
        value = int(token.value or 0)
        if not value:
            raise _NativeFailure
        return value

    def _token_buffer(self, token: int, information_class: int):
        needed = _DWORD()
        first = self.advapi32.GetTokenInformation(
            ctypes.c_void_p(token), information_class, None, 0, ctypes.byref(needed)
        )
        if first or ctypes.get_last_error() != _ERROR_INSUFFICIENT_BUFFER:
            raise _NativeFailure
        if not 1 <= needed.value <= MAX_TOKEN_BYTES:
            raise _NativeFailure
        buffer = ctypes.create_string_buffer(needed.value)
        returned = _DWORD()
        if not self.advapi32.GetTokenInformation(
            ctypes.c_void_p(token),
            information_class,
            buffer,
            needed.value,
            ctypes.byref(returned),
        ):
            raise _NativeFailure
        if not 1 <= returned.value <= needed.value:
            raise _NativeFailure
        return buffer, int(returned.value)

    @staticmethod
    def _token_user_sid(buffer, valid_length: int) -> int:
        structure_size = ctypes.sizeof(_TOKEN_USER_STRUCT)
        if valid_length < structure_size:
            raise _NativeFailure
        base = ctypes.addressof(buffer)
        end = base + valid_length
        sid = int(
            ctypes.cast(buffer, ctypes.POINTER(_TOKEN_USER_STRUCT)).contents.User.Sid
            or 0
        )
        if sid < base or sid > end - 8:
            raise _NativeFailure
        header = ctypes.string_at(sid, 8)
        subauthority_count = header[1]
        # A valid Windows SID has at most 15 32-bit subauthorities.
        sid_length = 8 + subauthority_count * 4
        if header[0] != 1 or subauthority_count > 15 or sid_length > end - sid:
            raise _NativeFailure
        return sid

    def same_user_and_session(self, process_handle: int) -> bool:
        peer_token = current_token = 0
        try:
            peer_token = self._open_token(process_handle)
            current_process = int(self.kernel32.GetCurrentProcess() or 0)
            if not current_process:
                raise _NativeFailure
            current_token = self._open_token(current_process)
            peer_user, peer_user_length = self._token_buffer(peer_token, _TOKEN_USER)
            current_user, current_user_length = self._token_buffer(
                current_token, _TOKEN_USER
            )
            peer_sid = self._token_user_sid(peer_user, peer_user_length)
            current_sid = self._token_user_sid(current_user, current_user_length)
            same_user = bool(self.advapi32.EqualSid(peer_sid, current_sid))
            peer_session, peer_session_length = self._token_buffer(
                peer_token, _TOKEN_SESSION_ID
            )
            current_session, current_session_length = self._token_buffer(
                current_token, _TOKEN_SESSION_ID
            )
            if peer_session_length < ctypes.sizeof(_DWORD) or (
                current_session_length < ctypes.sizeof(_DWORD)
            ):
                raise _NativeFailure
            peer_value = _DWORD.from_buffer(peer_session).value
            current_value = _DWORD.from_buffer(current_session).value
            return same_user and peer_value == current_value
        finally:
            if current_token:
                self.close_handle(current_token)
            if peer_token:
                self.close_handle(peer_token)

    def tcp_peer_pids(self, endpoint: _SocketTuple) -> tuple[int, ...]:
        if endpoint.family == socket.AF_INET:
            row_type = _MIB_TCPROW_OWNER_PID
            table_type = _MIB_TCPTABLE_OWNER_PID_ONE
        elif endpoint.family == socket.AF_INET6:
            row_type = _MIB_TCP6ROW_OWNER_PID
            table_type = _MIB_TCP6TABLE_OWNER_PID_ONE
        else:
            raise _NativeFailure
        size = _DWORD()
        result = int(
            self.iphlpapi.GetExtendedTcpTable(
                None,
                ctypes.byref(size),
                False,
                endpoint.family,
                _TCP_TABLE_OWNER_PID_CONNECTIONS,
                0,
            )
        )
        if result not in {_NO_ERROR, _ERROR_INSUFFICIENT_BUFFER}:
            raise _NativeFailure
        for _ in range(TABLE_BUFFER_ATTEMPTS):
            offset = table_type.table.offset
            if not offset <= size.value <= MAX_TCP_TABLE_BYTES:
                raise _NativeFailure
            capacity = int(size.value)
            buffer = ctypes.create_string_buffer(capacity)
            supplied = _DWORD(capacity)
            result = int(
                self.iphlpapi.GetExtendedTcpTable(
                    buffer,
                    ctypes.byref(supplied),
                    False,
                    endpoint.family,
                    _TCP_TABLE_OWNER_PID_CONNECTIONS,
                    0,
                )
            )
            if result == _ERROR_INSUFFICIENT_BUFFER:
                size = supplied
                continue
            if result != _NO_ERROR:
                raise _NativeFailure
            returned_size = int(supplied.value)
            if not offset <= returned_size <= capacity:
                raise _NativeFailure
            count = _DWORD.from_buffer(buffer).value
            row_size = ctypes.sizeof(row_type)
            if count > (returned_size - offset) // row_size:
                raise _NativeFailure
            matches: list[int] = []
            for index in range(count):
                row = row_type.from_buffer_copy(buffer, offset + index * row_size)
                if self._row_matches(row, endpoint):
                    matches.append(int(row.dwOwningPid))
                    if len(matches) > 1:
                        break
            return tuple(matches)
        raise _NativeFailure

    @staticmethod
    def _port(value: int) -> int:
        if value & 0xFFFF0000:
            raise _NativeFailure
        return socket.ntohs(value)

    def _row_matches(self, row, endpoint: _SocketTuple) -> bool:
        try:
            if int(row.dwState) != _MIB_TCP_STATE_ESTAB:
                return False
            if self._port(int(row.dwLocalPort)) != endpoint.peer_port:
                return False
            if self._port(int(row.dwRemotePort)) != endpoint.local_port:
                return False
            if endpoint.family == socket.AF_INET:
                local = ctypes.string_at(
                    ctypes.addressof(row) + type(row).dwLocalAddr.offset, 4
                )
                remote = ctypes.string_at(
                    ctypes.addressof(row) + type(row).dwRemoteAddr.offset, 4
                )
                return local == endpoint.peer_address and remote == endpoint.local_address
            return (
                bytes(row.ucLocalAddr) == endpoint.peer_address
                and bytes(row.ucRemoteAddr) == endpoint.local_address
                and socket.ntohl(int(row.dwLocalScopeId)) == endpoint.peer_scope
                and socket.ntohl(int(row.dwRemoteScopeId)) == endpoint.local_scope
            )
        except (OSError, OverflowError):
            raise _NativeFailure from None


def _load_native() -> _Native:
    return _Native()


def _peer_pid(
    native: _Native,
    endpoint: _SocketTuple,
    cancelled: Callable[[], bool],
    deadline: float,
    expected_pid: int | None = None,
) -> int:
    while True:
        _check_progress(cancelled, deadline)
        matches = native.tcp_peer_pids(endpoint)
        _check_progress(cancelled, deadline)
        if len(matches) > 1 or any(pid in {0, 4} or pid < 0 for pid in matches):
            raise PeerIdentityError("OBS peer identity verification failed")
        if matches:
            pid = matches[0]
            if expected_pid is not None and pid != expected_pid:
                raise PeerIdentityError("OBS peer identity verification failed")
            return pid
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise PeerIdentityError("OBS peer identity verification failed")
        time.sleep(min(TABLE_POLL_SECONDS, remaining))


class ExpectedExecutableLease:
    """Owned handle pinning the configured executable during authentication."""

    def __init__(
        self,
        native: _Native,
        handle: int,
        identity: _FileIdentity,
        resolved_path: str,
    ) -> None:
        self._native = native
        self._handle = handle
        self._identity = identity
        self._resolved_path = resolved_path
        self._lock = threading.Lock()
        self._closed = False

    def __repr__(self) -> str:
        return "ExpectedExecutableLease()"

    def __enter__(self) -> ExpectedExecutableLease:
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()

    def verify(
        self,
        sock: socket.socket,
        *,
        cancelled: Callable[[], bool],
        deadline: float,
    ) -> VerifiedPeerLease:
        _validate_controls(cancelled, deadline)
        with self._lock:
            if self._closed:
                raise PeerIdentityError("OBS peer identity verification failed")
            try:
                _check_progress(cancelled, float(deadline))
                endpoint = _socket_tuple(sock)
                pid = _peer_pid(
                    self._native, endpoint, cancelled, float(deadline)
                )
                process_handle = self._native.open_process(pid)
                try:
                    _check_progress(cancelled, float(deadline))
                    if not self._native.process_alive(process_handle):
                        raise _NativeFailure
                    _check_progress(cancelled, float(deadline))
                    creation_time = self._native.process_creation_time(process_handle)
                    _check_progress(cancelled, float(deadline))
                    if not self._native.same_user_and_session(process_handle):
                        raise _NativeFailure
                    _check_progress(cancelled, float(deadline))
                    reported_image = _canonical_dos_image_path(
                        self._native.process_image_path(process_handle),
                        trusted_final=False,
                    )
                    _check_progress(cancelled, float(deadline))
                    expected_image = _canonical_dos_image_path(
                        self._identity.final_path,
                        trusted_final=True,
                    )
                    if reported_image != expected_image:
                        raise _NativeFailure
                    candidate_handle, candidate = self._native.open_file(
                        self._resolved_path
                    )
                    try:
                        _check_progress(cancelled, float(deadline))
                        if candidate != self._identity:
                            raise _NativeFailure
                    finally:
                        self._native.close_handle(candidate_handle)
                    _check_progress(cancelled, float(deadline))
                    _peer_pid(
                        self._native,
                        endpoint,
                        cancelled,
                        float(deadline),
                        expected_pid=pid,
                    )
                    if not self._native.process_alive(process_handle):
                        raise _NativeFailure
                    _check_progress(cancelled, float(deadline))
                    return VerifiedPeerLease(
                        self._native,
                        process_handle,
                        pid,
                        creation_time,
                        endpoint,
                    )
                except BaseException:
                    self._native.close_handle(process_handle)
                    raise
            except PeerIdentityError:
                raise
            except BaseException as exc:
                if not isinstance(exc, Exception):
                    raise
                raise PeerIdentityError("OBS peer identity verification failed") from None

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            handle, self._handle = self._handle, 0
        self._native.close_handle(handle)


class VerifiedPeerLease:
    """Owned stable process handle for the socket's verified server process."""

    def __init__(
        self,
        native: _Native,
        handle: int,
        pid: int,
        creation_time: int,
        endpoint: _SocketTuple,
    ) -> None:
        self._native = native
        self._handle = handle
        self._pid = pid
        self._creation_time = creation_time
        self._endpoint = endpoint
        self._lock = threading.Lock()
        self._closed = False

    def __repr__(self) -> str:
        return "VerifiedPeerLease()"

    def __enter__(self) -> VerifiedPeerLease:
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()

    @property
    def creation_time(self) -> int:
        return self._creation_time

    @property
    def pid(self) -> int:
        return self._pid

    def revalidate(
        self, *, cancelled: Callable[[], bool], deadline: float
    ) -> None:
        _validate_controls(cancelled, deadline)
        with self._lock:
            if self._closed:
                raise PeerIdentityError("OBS peer identity verification failed")
            try:
                _check_progress(cancelled, float(deadline))
                if not self._native.process_alive(self._handle):
                    raise _NativeFailure
                _check_progress(cancelled, float(deadline))
                _peer_pid(
                    self._native,
                    self._endpoint,
                    cancelled,
                    float(deadline),
                    expected_pid=self._pid,
                )
                _check_progress(cancelled, float(deadline))
                if not self._native.process_alive(self._handle):
                    raise _NativeFailure
                _check_progress(cancelled, float(deadline))
            except PeerIdentityError:
                raise
            except BaseException as exc:
                if not isinstance(exc, Exception):
                    raise
                raise PeerIdentityError("OBS peer identity verification failed") from None

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            handle, self._handle = self._handle, 0
        self._native.close_handle(handle)

    def retain_process(
        self, *, cancelled: Callable[[], bool], deadline: float
    ) -> VerifiedProcessLease:
        """Pin the verified process independently while its TCP peer is valid.

        The caller owns the returned handle. It remains usable after control/TCP
        closes, but never survives exit of the original process object.
        """
        _validate_controls(cancelled, deadline)
        duplicate = 0
        with self._lock:
            try:
                if self._closed:
                    raise _NativeFailure
                _check_progress(cancelled, float(deadline))
                if not self._native.process_alive(self._handle):
                    raise _NativeFailure
                _check_progress(cancelled, float(deadline))
                _peer_pid(self._native, self._endpoint, cancelled, float(deadline),
                          expected_pid=self._pid)
                _check_progress(cancelled, float(deadline))
                duplicate = self._native.duplicate_process(self._handle)
                _check_progress(cancelled, float(deadline))
                if not self._native.process_alive(duplicate):
                    raise _NativeFailure
                _check_progress(cancelled, float(deadline))
                return VerifiedProcessLease(
                    self._native, duplicate, self._pid, self._creation_time
                )
            except BaseException as exc:
                if duplicate:
                    self._native.close_handle(duplicate)
                if isinstance(exc, PeerIdentityError) or not isinstance(exc, Exception):
                    raise
                raise PeerIdentityError("OBS peer identity verification failed") from None


class VerifiedProcessLease:
    """An independently owned handle for the originally verified process.

    Created by VerifiedPeerLease.retain_process, never by a PID received in JSON.
    No TCP dependency remains; the same process/user/session must stay alive.
    """

    def __init__(self, native: _Native, handle: int, pid: int, creation_time: int):
        self._native, self._handle = native, handle
        self._pid, self._creation_time = pid, creation_time
        self._lock = threading.Lock()

    def __repr__(self) -> str:
        return "VerifiedProcessLease()"

    def __enter__(self) -> VerifiedProcessLease:
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()

    @property
    def pid(self) -> int:
        return self._pid

    @property
    def creation_time(self) -> int:
        return self._creation_time

    def verify_pid(self, pid: int, *, cancelled: Callable[[], bool], deadline: float) -> None:
        _validate_controls(cancelled, deadline)
        with self._lock:
            try:
                _check_progress(cancelled, float(deadline))
                if type(pid) is not int or pid <= 4 or pid != self._pid or not self._handle:
                    raise _NativeFailure
                if not self._native.process_alive(self._handle):
                    raise _NativeFailure
                _check_progress(cancelled, float(deadline))
                if not self._native.same_user_and_session(self._handle):
                    raise _NativeFailure
                _check_progress(cancelled, float(deadline))
                if not self._native.process_alive(self._handle):
                    raise _NativeFailure
                _check_progress(cancelled, float(deadline))
            except PeerIdentityError:
                raise
            except Exception:
                raise PeerIdentityError("OBS audio peer identity verification failed") from None

    def close(self) -> None:
        with self._lock:
            handle, self._handle = self._handle, 0
        if handle:
            self._native.close_handle(handle)


def open_expected_executable(path: str | Path) -> ExpectedExecutableLease:
    """Open an explicitly selected local executable and retain its identity."""
    try:
        if sys.platform != "win32":
            raise _NativeFailure
        if type(path) is not str and not isinstance(path, Path):
            raise ValueError
        candidate = Path(path)
        if not candidate.is_absolute() or candidate.suffix.casefold() != ".exe":
            raise ValueError
        resolved = require_local_filesystem(candidate)
        native = _load_native()
        handle, identity = native.open_file(str(resolved))
        return ExpectedExecutableLease(native, handle, identity, str(resolved))
    except (PeerIdentityError, PeerIdentityCancelled):
        raise
    except (LocalFilesystemError, OSError, ValueError, _NativeFailure):
        raise PeerIdentityError("Expected OBS executable could not be verified") from None


__all__ = [
    "ExpectedExecutableLease",
    "PeerIdentityCancelled",
    "PeerIdentityError",
    "VerifiedPeerLease",
    "VerifiedProcessLease",
    "open_expected_executable",
]
