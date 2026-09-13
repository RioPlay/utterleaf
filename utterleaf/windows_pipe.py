"""Bounded local Windows named-pipe client I/O.

Importing this module performs no native calls.  Pending overlapped operations
are always observed as complete before their Python storage or native handles
are released.
"""

from __future__ import annotations

from collections.abc import Callable
import ctypes
from ctypes import wintypes
import math
import re
import sys
import threading
import time


MAX_IO_BYTES = 65_536
POLL_SECONDS = 0.05

_PIPE_NAME = re.compile(r"\\\\\.\\pipe\\Utterleaf\.OBS\.[0-9a-f]{32}", re.ASCII)

_DWORD = ctypes.c_uint32
_BOOL = ctypes.c_int32
_ULONG_PTR = ctypes.c_size_t
_HANDLE = ctypes.c_void_p

_GENERIC_READ = 0x80000000
_GENERIC_WRITE = 0x40000000
_OPEN_EXISTING = 3
_FILE_FLAG_OVERLAPPED = 0x40000000
_SECURITY_SQOS_PRESENT = 0x00100000
_SECURITY_IDENTIFICATION = 0x00010000
_ERROR_FILE_NOT_FOUND = 2
_ERROR_PIPE_BUSY = 231
_ERROR_IO_PENDING = 997
_ERROR_IO_INCOMPLETE = 996
_ERROR_NOT_FOUND = 1168
_WAIT_OBJECT_0 = 0
_WAIT_TIMEOUT = 258
_INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value


class WindowsPipeError(RuntimeError):
    """A local OBS pipe operation failed."""


class WindowsPipeCancelled(WindowsPipeError):
    """A local OBS pipe operation was cancelled."""


class WindowsPipeTimeout(WindowsPipeError):
    """A local OBS pipe operation exceeded its caller deadline."""


class _NativeFailure(Exception):
    def __init__(self, code: int = 0):
        self.code = int(code)


class _OVERLAPPED(ctypes.Structure):
    _fields_ = [
        ("Internal", _ULONG_PTR),
        ("InternalHigh", _ULONG_PTR),
        ("Offset", _DWORD),
        ("OffsetHigh", _DWORD),
        ("hEvent", _HANDLE),
    ]


def _validate_controls(cancelled: object, deadline: object) -> None:
    if not callable(cancelled):
        raise TypeError("cancelled must be callable")
    if isinstance(deadline, bool) or not isinstance(deadline, (int, float)):
        raise TypeError("deadline must be a finite number")
    if not math.isfinite(float(deadline)):
        raise ValueError("deadline must be finite")


def _check_progress(cancelled: Callable[[], bool], deadline: float) -> None:
    try:
        stopped = bool(cancelled())
    except Exception:
        raise WindowsPipeError("OBS audio pipe operation failed") from None
    if stopped:
        raise WindowsPipeCancelled("OBS audio pipe operation cancelled")
    if time.monotonic() >= deadline:
        raise WindowsPipeTimeout("OBS audio pipe operation timed out")


def _validate_pipe_name(pipe_name: object) -> str:
    if type(pipe_name) is not str or _PIPE_NAME.fullmatch(pipe_name) is None:
        raise ValueError("invalid OBS audio pipe name")
    return pipe_name


class _Native:
    def __init__(self) -> None:
        if sys.platform != "win32":
            raise WindowsPipeError("Windows OBS audio pipes are unavailable")
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self._create_file = kernel32.CreateFileW
        self._create_file.argtypes = [
            wintypes.LPCWSTR, _DWORD, _DWORD, ctypes.c_void_p, _DWORD, _DWORD,
            _HANDLE,
        ]
        self._create_file.restype = _HANDLE
        self._create_event = kernel32.CreateEventW
        self._create_event.argtypes = [ctypes.c_void_p, _BOOL, _BOOL, wintypes.LPCWSTR]
        self._create_event.restype = _HANDLE
        self._read_file = kernel32.ReadFile
        self._read_file.argtypes = [_HANDLE, ctypes.c_void_p, _DWORD, ctypes.POINTER(_DWORD), ctypes.POINTER(_OVERLAPPED)]
        self._read_file.restype = _BOOL
        self._write_file = kernel32.WriteFile
        self._write_file.argtypes = [_HANDLE, ctypes.c_void_p, _DWORD, ctypes.POINTER(_DWORD), ctypes.POINTER(_OVERLAPPED)]
        self._write_file.restype = _BOOL
        self._wait = kernel32.WaitForSingleObject
        self._wait.argtypes = [_HANDLE, _DWORD]
        self._wait.restype = _DWORD
        self._cancel = kernel32.CancelIoEx
        self._cancel.argtypes = [_HANDLE, ctypes.POINTER(_OVERLAPPED)]
        self._cancel.restype = _BOOL
        self._result = kernel32.GetOverlappedResult
        self._result.argtypes = [_HANDLE, ctypes.POINTER(_OVERLAPPED), ctypes.POINTER(_DWORD), _BOOL]
        self._result.restype = _BOOL
        self._server_pid = kernel32.GetNamedPipeServerProcessId
        self._server_pid.argtypes = [_HANDLE, ctypes.POINTER(_DWORD)]
        self._server_pid.restype = _BOOL
        self._close = kernel32.CloseHandle
        self._close.argtypes = [_HANDLE]
        self._close.restype = _BOOL

    @staticmethod
    def last_error() -> int:
        return int(ctypes.get_last_error())

    def open_pipe(self, name: str) -> int:
        flags = _FILE_FLAG_OVERLAPPED | _SECURITY_SQOS_PRESENT | _SECURITY_IDENTIFICATION
        handle = self._create_file(
            name, _GENERIC_READ | _GENERIC_WRITE, 0, None, _OPEN_EXISTING,
            flags, None,
        )
        value = int(handle) if handle else 0
        if not value or value == _INVALID_HANDLE_VALUE:
            raise _NativeFailure(self.last_error())
        return value

    def create_event(self) -> int:
        handle = self._create_event(None, True, False, None)
        if not handle:
            raise _NativeFailure(self.last_error())
        return int(handle)

    def begin_read(self, handle: int, buffer: object, size: int, overlapped: _OVERLAPPED) -> bool:
        if self._read_file(handle, buffer, size, None, ctypes.byref(overlapped)):
            return True
        code = self.last_error()
        if code != _ERROR_IO_PENDING:
            raise _NativeFailure(code)
        return False

    def begin_write(self, handle: int, buffer: object, size: int, overlapped: _OVERLAPPED) -> bool:
        if self._write_file(handle, buffer, size, None, ctypes.byref(overlapped)):
            return True
        code = self.last_error()
        if code != _ERROR_IO_PENDING:
            raise _NativeFailure(code)
        return False

    def wait(self, event: int, milliseconds: int) -> int:
        return int(self._wait(event, milliseconds))

    def cancel(self, handle: int, overlapped: _OVERLAPPED) -> int:
        if self._cancel(handle, ctypes.byref(overlapped)):
            return 0
        return self.last_error()

    def result(self, handle: int, overlapped: _OVERLAPPED, *, wait: bool) -> int:
        transferred = _DWORD()
        if not self._result(handle, ctypes.byref(overlapped), ctypes.byref(transferred), wait):
            raise _NativeFailure(self.last_error())
        return int(transferred.value)

    def server_pid(self, handle: int) -> int:
        pid = _DWORD()
        if not self._server_pid(handle, ctypes.byref(pid)):
            raise _NativeFailure(self.last_error())
        return int(pid.value)

    def close(self, handle: int) -> None:
        self._close(handle)


class WindowsPipe:
    """An owned, serialized local named-pipe handle."""

    def __init__(self, native: _Native, handle: int, cancelled: Callable[[], bool]):
        self._native = native
        self._handle = handle
        self._cancelled = cancelled
        self._closing = threading.Event()
        self._lock = threading.Lock()

    def __enter__(self) -> WindowsPipe:
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()

    def __repr__(self) -> str:
        return f"{type(self).__name__}(closed={self._handle is None})"

    def _require_handle_locked(self) -> int:
        if self._handle is None:
            raise WindowsPipeError("OBS audio pipe is closed")
        return self._handle

    def _close_locked(self) -> None:
        handle, self._handle = self._handle, None
        if handle is not None:
            self._native.close(handle)

    def close(self) -> None:
        self._closing.set()
        with self._lock:
            self._close_locked()

    def server_pid(self) -> int:
        with self._lock:
            handle = self._require_handle_locked()
            try:
                pid = self._native.server_pid(handle)
                if pid <= 4:
                    raise _NativeFailure()
                return pid
            except BaseException as exc:
                self._closing.set()
                self._close_locked()
                if not isinstance(exc, Exception):
                    raise
                raise WindowsPipeError("OBS audio pipe server verification failed") from None

    def _cancel_requested(self) -> bool:
        if self._closing.is_set():
            return True
        try:
            return bool(self._cancelled())
        except Exception:
            raise WindowsPipeError("OBS audio pipe operation failed") from None

    def _cancel_and_drain(self, handle: int, overlapped: _OVERLAPPED) -> None:
        cancel_failure: BaseException | None = None
        try:
            cancel_error = self._native.cancel(handle, overlapped)
            if cancel_error not in (0, _ERROR_NOT_FOUND):
                cancel_failure = _NativeFailure(cancel_error)
        except BaseException as exc:
            cancel_failure = exc

        result_failure: BaseException | None = None
        while True:
            retry = False
            try:
                self._native.result(handle, overlapped, wait=True)
                break
            except _NativeFailure as exc:
                if exc.code == _ERROR_IO_INCOMPLETE:
                    retry = True
                else:
                    break  # A normal WinAPI operation error is terminal.
            except BaseException as exc:
                # Preserve Python failures, but don't release native operation
                # storage until WinAPI subsequently reports a terminal result.
                if result_failure is None:
                    result_failure = exc
                retry = True
            if retry:
                try:
                    time.sleep(POLL_SECONDS)
                except BaseException as exc:
                    if result_failure is None:
                        result_failure = exc
        if cancel_failure is not None:
            raise cancel_failure
        if result_failure is not None:
            raise result_failure

    def _perform(self, handle: int, buffer: object, size: int, deadline: float, *, write: bool) -> int:
        overlapped = _OVERLAPPED()
        event = self._native.create_event()
        pending = False
        try:
            overlapped.hEvent = event
            pending = True
            try:
                immediate = (
                    self._native.begin_write(handle, buffer, size, overlapped)
                    if write else self._native.begin_read(handle, buffer, size, overlapped)
                )
            except _NativeFailure:
                pending = False
                raise
            if immediate:
                result = self._native.result(handle, overlapped, wait=False)
                pending = False
                return result
            while True:
                if self._cancel_requested():
                    try:
                        self._cancel_and_drain(handle, overlapped)
                    finally:
                        pending = False
                    raise WindowsPipeCancelled("OBS audio pipe operation cancelled")
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    try:
                        self._cancel_and_drain(handle, overlapped)
                    finally:
                        pending = False
                    raise WindowsPipeTimeout("OBS audio pipe operation timed out")
                status = self._native.wait(event, max(1, min(50, math.ceil(remaining * 1000))))
                if status == _WAIT_TIMEOUT:
                    continue
                if status != _WAIT_OBJECT_0:
                    try:
                        self._cancel_and_drain(handle, overlapped)
                    finally:
                        pending = False
                    raise _NativeFailure()
                result = self._native.result(handle, overlapped, wait=False)
                pending = False
                return result
        except BaseException:
            if pending:
                try:
                    self._cancel_and_drain(handle, overlapped)
                except Exception:
                    pass
            raise
        finally:
            self._native.close(event)

    def read(self, max_bytes: int, *, deadline: float) -> bytes:
        if isinstance(max_bytes, bool) or not isinstance(max_bytes, int):
            raise TypeError("max_bytes must be an integer")
        if not 1 <= max_bytes <= MAX_IO_BYTES:
            raise ValueError("max_bytes is outside the supported range")
        _validate_controls(self._cancelled, deadline)
        with self._lock:
            handle = self._require_handle_locked()
            try:
                _check_progress(self._cancel_requested, float(deadline))
                buffer = (ctypes.c_ubyte * max_bytes)()
                count = self._perform(handle, buffer, max_bytes, float(deadline), write=False)
                if not 1 <= count <= max_bytes:
                    raise _NativeFailure()
                _check_progress(self._cancel_requested, float(deadline))
                return bytes(buffer[:count])
            except BaseException as exc:
                self._closing.set()
                self._close_locked()
                if not isinstance(exc, Exception):
                    raise
                if isinstance(exc, (WindowsPipeCancelled, WindowsPipeTimeout, WindowsPipeError)):
                    raise
                raise WindowsPipeError("OBS audio pipe read failed") from None

    def write_all(self, data: bytes, *, deadline: float) -> None:
        if type(data) is not bytes:
            raise TypeError("data must be bytes")
        if not 1 <= len(data) <= MAX_IO_BYTES:
            raise ValueError("data length is outside the supported range")
        _validate_controls(self._cancelled, deadline)
        with self._lock:
            handle = self._require_handle_locked()
            try:
                offset = 0
                while offset < len(data):
                    _check_progress(self._cancel_requested, float(deadline))
                    remaining = data[offset:]
                    buffer = ctypes.create_string_buffer(remaining, len(remaining))
                    count = self._perform(handle, buffer, len(remaining), float(deadline), write=True)
                    if not 1 <= count <= len(remaining):
                        raise _NativeFailure()
                    offset += count
                _check_progress(self._cancel_requested, float(deadline))
            except BaseException as exc:
                self._closing.set()
                self._close_locked()
                if not isinstance(exc, Exception):
                    raise
                if isinstance(exc, (WindowsPipeCancelled, WindowsPipeTimeout, WindowsPipeError)):
                    raise
                raise WindowsPipeError("OBS audio pipe write failed") from None


def connect(pipe_name: str, *, cancelled: Callable[[], bool], deadline: float) -> WindowsPipe:
    """Open one exact local Utterleaf OBS pipe before ``deadline``."""
    name = _validate_pipe_name(pipe_name)
    _validate_controls(cancelled, deadline)
    deadline_value = float(deadline)
    _check_progress(cancelled, deadline_value)
    native = _Native()
    while True:
        _check_progress(cancelled, deadline_value)
        try:
            handle = native.open_pipe(name)
            try:
                _check_progress(cancelled, deadline_value)
                pipe = WindowsPipe(native, handle, cancelled)
            except BaseException:
                native.close(handle)
                raise
            return pipe
        except _NativeFailure as exc:
            if exc.code not in (_ERROR_FILE_NOT_FOUND, _ERROR_PIPE_BUSY):
                raise WindowsPipeError("OBS audio pipe connection failed") from None
        remaining = deadline_value - time.monotonic()
        if remaining <= 0:
            raise WindowsPipeTimeout("OBS audio pipe connection timed out")
        time.sleep(min(POLL_SECONDS, remaining))
