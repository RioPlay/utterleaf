"""Bounded, private Windows clipboard operations.

Clipboard text crosses only inherited pipes to a one-shot child.  The child owns
the hidden window and every native clipboard handle.  On Windows, payload is not
sent until that child joins a kill-on-close job owned only by the parent.  A rare
failed native termination/reap remains an uncertain result, never a retry claim.
"""
from __future__ import annotations

import base64
import ctypes
import json
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


PROTOCOL_VERSION = 1
MAX_TEXT_BYTES = 1024 * 1024
MAX_FRAME_BYTES = ((MAX_TEXT_BYTES + 2) // 3) * 4 + 512
OPERATION_TIMEOUT_SECONDS = 1.0
STOP_TIMEOUT_SECONDS = 0.2
POLL_SECONDS = 0.01
OPEN_RETRY_SECONDS = 0.25

_STATUSES = frozenset({"ok", "unavailable", "changed", "cancelled", "uncertain"})


class _IO_COUNTERS(ctypes.Structure):
    _fields_ = [(name, ctypes.c_ulonglong) for name in (
        "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
        "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]


class _BASIC_JOB_LIMITS(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_longlong),
        ("PerJobUserTimeLimit", ctypes.c_longlong),
        ("LimitFlags", ctypes.c_ulong),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", ctypes.c_ulong),
        ("Affinity", ctypes.c_size_t),
        ("PriorityClass", ctypes.c_ulong),
        ("SchedulingClass", ctypes.c_ulong),
    ]


class _EXTENDED_JOB_LIMITS(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", _BASIC_JOB_LIMITS),
        ("IoInfo", _IO_COUNTERS),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


class _WindowsJob:
    """One unnamed, non-inherited kill-on-close job handle."""

    def __init__(self, kernel32, handle: int) -> None:
        self._kernel32 = kernel32
        self._handle = handle

    def assign(self, process) -> bool:
        try:
            process_handle = int(process._handle)
            return bool(self._kernel32.AssignProcessToJobObject(
                ctypes.c_void_p(self._handle), ctypes.c_void_p(process_handle)))
        except Exception:
            return False

    def close(self) -> bool:
        if not self._handle:
            return True
        try:
            closed = bool(self._kernel32.CloseHandle(ctypes.c_void_p(self._handle)))
        except Exception:
            closed = False
        if closed:
            self._handle = 0
        return closed

    def __del__(self) -> None:
        self.close()


def _create_job() -> _WindowsJob | None:
    """Create and configure containment before any payload-capable child exists."""
    if sys.platform != "win32":
        return None
    kernel32 = None
    handle = 0
    try:
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        kernel32.CreateJobObjectW.restype = ctypes.c_void_p
        kernel32.SetInformationJobObject.argtypes = [
            ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
        kernel32.SetInformationJobObject.restype = wintypes.BOOL
        kernel32.AssignProcessToJobObject.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
        kernel32.CloseHandle.restype = wintypes.BOOL
        # NULL security attributes make this unnamed handle non-inheritable.
        handle = int(kernel32.CreateJobObjectW(None, None) or 0)
        if not handle:
            return None
        limits = _EXTENDED_JOB_LIMITS()
        limits.BasicLimitInformation.LimitFlags = 0x00002000  # KILL_ON_JOB_CLOSE
        if not kernel32.SetInformationJobObject(
                ctypes.c_void_p(handle), 9, ctypes.byref(limits), ctypes.sizeof(limits)):
            return None
        job = _WindowsJob(kernel32, handle)
        handle = 0  # ownership handed to the returned wrapper
        return job
    except Exception:
        return None
    finally:
        if handle and kernel32 is not None:
            try:
                kernel32.CloseHandle(ctypes.c_void_p(handle))
            except Exception:
                pass


@dataclass(frozen=True)
class Result:
    status: str
    text: str | None = None
    sequence: int | None = None


def _cancelled(cancel: Callable[[], bool] | None) -> bool:
    try:
        return bool(cancel is not None and cancel())
    except Exception:
        return True


def _child_command() -> list[str]:
    if getattr(sys, "frozen", False):
        executable = sys.executable
        if sys.platform == "win32":
            # PyInstaller's windowed bootloader deliberately exposes no Python
            # standard streams.  The distribution ships this console companion;
            # CREATE_NO_WINDOW below keeps it invisible while preserving pipes.
            executable = str(Path(executable).with_name("utterleaf-cli.exe"))
        return [executable, "--clipboard-worker"]
    return [sys.executable, "-m", "utterleaf", "--clipboard-worker"]


def snapshot(*, cancel: Callable[[], bool] | None = None) -> Result:
    """Return a bounded plain-text snapshot and its Windows sequence receipt."""
    return _invoke({"v": PROTOCOL_VERSION, "op": "snapshot"}, "snapshot", cancel)


def write(text: str, *, expected_sequence: int | None = None,
          cancel: Callable[[], bool] | None = None) -> Result:
    """Eagerly replace CF_UNICODETEXT, conditionally when a receipt is supplied."""
    if not isinstance(text, str) or "\0" in text:
        return Result("unavailable")
    try:
        encoded = text.encode("utf-8")
    except UnicodeEncodeError:
        return Result("unavailable")
    if len(encoded) > MAX_TEXT_BYTES:
        return Result("unavailable")
    if expected_sequence is not None and (
            isinstance(expected_sequence, bool) or not isinstance(expected_sequence, int)
            or expected_sequence <= 0 or expected_sequence > 0xFFFFFFFF):
        return Result("unavailable")
    request: dict[str, object] = {
        "v": PROTOCOL_VERSION,
        "op": "write",
        "text_b64": base64.b64encode(encoded).decode("ascii"),
    }
    if expected_sequence is not None:
        request["expected_sequence"] = expected_sequence
    return _invoke(request, "write", cancel)


def _invoke(request: dict[str, object], operation: str,
            cancel: Callable[[], bool] | None) -> Result:
    if _cancelled(cancel):
        return Result("cancelled")
    frame = json.dumps(request, separators=(",", ":")).encode("utf-8") + b"\n"
    if len(frame) > MAX_FRAME_BYTES:
        return Result("unavailable")
    job = _create_job() if sys.platform == "win32" else None
    if sys.platform == "win32" and job is None:
        return Result("unavailable")
    if _cancelled(cancel):
        if job is not None:
            job.close()
        return Result("cancelled")
    kwargs: dict[str, object] = {
        "stdin": subprocess.PIPE,
        "stdout": subprocess.PIPE,
        "stderr": subprocess.DEVNULL,
        "shell": False,
        "close_fds": True,
    }
    if sys.platform == "win32":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        process = subprocess.Popen(_child_command(), **kwargs)
    except Exception:
        if job is not None:
            job.close()
        return Result("unavailable")

    # The child can parse imports and then wait for stdin, but cannot receive an
    # operation until assignment succeeds.  Assignment failure therefore has no
    # clipboard side effect and is safe to report as unavailable.
    if job is not None and not job.assign(process):
        job.close()
        _stop_process(process)
        _close_pipes(process)
        return Result("unavailable")
    if _cancelled(cancel):
        if job is not None:
            job.close()
        _stop_process(process)
        _close_pipes(process)
        return Result("cancelled")

    done = threading.Event()
    state: dict[str, object] = {}

    def exchange() -> None:
        try:
            if process.stdin is None or process.stdout is None:
                raise OSError
            if process.stdin.write(frame) != len(frame):
                raise OSError
            process.stdin.close()
            state["output"] = process.stdout.read(MAX_FRAME_BYTES + 1)
        except Exception as exc:
            state["error"] = exc
        finally:
            # The I/O thread alone closes streams it may have blocked in.  The
            # control thread first terminates/reaps the child, which releases the
            # pipe ends, then joins this owner without contending on buffer locks.
            _close_pipes(process)
            done.set()

    try:
        io_thread = threading.Thread(target=exchange, daemon=True,
                                     name="utterleaf-clipboard-worker-io")
        io_thread.start()
    except Exception:
        if job is not None:
            job.close()
        _stop_process(process)
        _close_pipes(process)  # no I/O thread started, so parent still owns them
        return Result("unavailable")

    deadline = time.monotonic() + OPERATION_TIMEOUT_SECONDS
    cancelled_after_launch = False
    while not done.wait(POLL_SECONDS):
        if _cancelled(cancel):
            cancelled_after_launch = True
            break
        if time.monotonic() >= deadline:
            break

    timed_out = not done.is_set()
    reaped = True
    if timed_out or cancelled_after_launch:
        if job is not None:
            job.close()
        reaped = _stop_process(process)
    else:
        try:
            process.wait(timeout=STOP_TIMEOUT_SECONDS)
        except (OSError, subprocess.TimeoutExpired):
            timed_out = True
            if job is not None:
                job.close()
            reaped = _stop_process(process)
    io_thread.join(STOP_TIMEOUT_SECONDS)

    job_closed = True if job is None else job.close()

    if cancelled_after_launch:
        return Result("unavailable" if operation == "snapshot" else "uncertain")
    if timed_out or not reaped or not job_closed or io_thread.is_alive():
        return Result("unavailable" if operation == "snapshot" else "uncertain")
    output = state.get("output")
    if state.get("error") is not None or not isinstance(output, bytes):
        return Result("unavailable" if operation == "snapshot" else "uncertain")
    if len(output) > MAX_FRAME_BYTES or process.returncode != 0:
        return Result("unavailable" if operation == "snapshot" else "uncertain")
    parsed = _parse_response(output, operation)
    if parsed is None:
        return Result("unavailable" if operation == "snapshot" else "uncertain")
    if _cancelled(cancel):
        if operation == "snapshot":
            return Result("unavailable")
        if parsed.status not in {"changed", "unavailable", "cancelled"}:
            return Result("uncertain")
    return parsed


def _stop_process(process) -> bool:
    try:
        live = process.poll() is None
    except Exception:
        live = True
    if live:
        try:
            process.terminate()
        except Exception:
            pass
    try:
        process.wait(timeout=STOP_TIMEOUT_SECONDS)
        return True
    except Exception:
        pass
    try:
        live = process.poll() is None
    except Exception:
        live = True
    if live:
        try:
            process.kill()
        except Exception:
            pass
    try:
        process.wait(timeout=STOP_TIMEOUT_SECONDS)
        return True
    except Exception:
        return False


def _close_pipes(process) -> None:
    for stream in (process.stdin, process.stdout):
        try:
            if stream is not None:
                stream.close()
        except (OSError, ValueError):
            pass


def _parse_response(raw: bytes, operation: str) -> Result | None:
    if not raw.endswith(b"\n") or raw.count(b"\n") != 1:
        return None
    try:
        value = json.loads(raw, object_pairs_hook=_unique_object)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError, RecursionError):
        return None
    if (not isinstance(value, dict) or type(value.get("v")) is not int
            or value.get("v") != PROTOCOL_VERSION):
        return None
    status = value.get("status")
    if not isinstance(status, str) or status not in _STATUSES:
        return None
    if operation == "snapshot" and status not in {"ok", "unavailable"}:
        return None
    sequence = value.get("sequence")
    if sequence is not None and (
            isinstance(sequence, bool) or not isinstance(sequence, int)
            or sequence <= 0 or sequence > 0xFFFFFFFF):
        return None
    allowed = {"v", "status", "sequence"}
    text = None
    if operation == "snapshot" and status == "ok":
        allowed.add("text_b64")
        encoded = value.get("text_b64")
        if not isinstance(encoded, str) or sequence is None:
            return None
        try:
            payload = base64.b64decode(encoded, validate=True)
            if len(payload) > MAX_TEXT_BYTES:
                return None
            text = payload.decode("utf-8")
        except (ValueError, UnicodeDecodeError):
            return None
    elif "text_b64" in value:
        return None
    if set(value) - allowed:
        return None
    if operation == "write" and status == "ok" and sequence is None:
        return None
    return Result(status, text=text, sequence=sequence)


class _Win32:
    CF_UNICODETEXT = 13
    GMEM_MOVEABLE = 0x0002

    def __init__(self) -> None:
        from ctypes import wintypes

        self.user32 = ctypes.WinDLL("user32", use_last_error=True)
        self.kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self.user32.CreateWindowExW.argtypes = [
            wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
            ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
            wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID,
        ]
        self.user32.CreateWindowExW.restype = ctypes.c_void_p
        self.user32.OpenClipboard.argtypes = [ctypes.c_void_p]
        self.user32.OpenClipboard.restype = wintypes.BOOL
        self.user32.CloseClipboard.restype = wintypes.BOOL
        self.user32.EmptyClipboard.restype = wintypes.BOOL
        self.user32.IsClipboardFormatAvailable.argtypes = [wintypes.UINT]
        self.user32.IsClipboardFormatAvailable.restype = wintypes.BOOL
        self.user32.GetClipboardData.argtypes = [wintypes.UINT]
        self.user32.GetClipboardData.restype = ctypes.c_void_p
        self.user32.SetClipboardData.argtypes = [wintypes.UINT, ctypes.c_void_p]
        self.user32.SetClipboardData.restype = ctypes.c_void_p
        self.user32.GetClipboardSequenceNumber.restype = wintypes.DWORD
        self.user32.DestroyWindow.argtypes = [wintypes.HWND]
        self.user32.DestroyWindow.restype = wintypes.BOOL
        self.kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
        self.kernel32.GlobalAlloc.restype = ctypes.c_void_p
        self.kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
        self.kernel32.GlobalLock.restype = ctypes.c_void_p
        self.kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
        self.kernel32.GlobalUnlock.restype = wintypes.BOOL
        self.kernel32.GlobalSize.argtypes = [ctypes.c_void_p]
        self.kernel32.GlobalSize.restype = ctypes.c_size_t
        self.kernel32.GlobalFree.argtypes = [ctypes.c_void_p]
        self.kernel32.GlobalFree.restype = ctypes.c_void_p

    def create_window(self) -> int:
        return int(self.user32.CreateWindowExW(
            0, "STATIC", "UtterleafClipboardWorker", 0,
            0, 0, 0, 0, None, None, None, None) or 0)

    def destroy_window(self, window: int) -> bool:
        return bool(self.user32.DestroyWindow(ctypes.c_void_p(window)))

    def open_clipboard(self, window: int) -> bool:
        deadline = time.monotonic() + OPEN_RETRY_SECONDS
        while True:
            if self.user32.OpenClipboard(ctypes.c_void_p(window)):
                return True
            if time.monotonic() >= deadline:
                return False
            time.sleep(POLL_SECONDS)

    def close_clipboard(self) -> bool:
        return bool(self.user32.CloseClipboard())

    def sequence(self) -> int:
        return int(self.user32.GetClipboardSequenceNumber())

    def read_text(self) -> str | None:
        if not self.user32.IsClipboardFormatAvailable(self.CF_UNICODETEXT):
            return None
        handle = self.user32.GetClipboardData(self.CF_UNICODETEXT)
        if not handle:
            return None
        size = int(self.kernel32.GlobalSize(ctypes.c_void_p(handle)))
        if size < 2 or size > MAX_TEXT_BYTES * 2 + 2:
            return None
        pointer = self.kernel32.GlobalLock(ctypes.c_void_p(handle))
        if not pointer:
            return None
        try:
            raw = ctypes.string_at(pointer, size)
        finally:
            self.kernel32.GlobalUnlock(ctypes.c_void_p(handle))
        end = next((i for i in range(0, len(raw) - 1, 2)
                    if raw[i:i + 2] == b"\0\0"), None)
        if end is None:
            return None
        try:
            text = raw[:end].decode("utf-16-le")
        except UnicodeDecodeError:
            return None
        return text if len(text.encode("utf-8")) <= MAX_TEXT_BYTES else None

    def allocate_text(self, text: str) -> int:
        raw = text.encode("utf-16-le") + b"\0\0"
        handle = int(self.kernel32.GlobalAlloc(self.GMEM_MOVEABLE, len(raw)) or 0)
        if not handle:
            return 0
        pointer = self.kernel32.GlobalLock(ctypes.c_void_p(handle))
        if not pointer:
            self.kernel32.GlobalFree(ctypes.c_void_p(handle))
            return 0
        ctypes.memmove(pointer, raw, len(raw))
        self.kernel32.GlobalUnlock(ctypes.c_void_p(handle))
        return handle

    def free(self, handle: int) -> None:
        self.kernel32.GlobalFree(ctypes.c_void_p(handle))

    def empty(self) -> bool:
        return bool(self.user32.EmptyClipboard())

    def set_text(self, handle: int) -> bool:
        return bool(self.user32.SetClipboardData(
            self.CF_UNICODETEXT, ctypes.c_void_p(handle)))


def _win_api():
    return _Win32()


def _native_snapshot(api) -> Result:
    try:
        window = api.create_window()
    except Exception:
        return Result("unavailable")
    if not window:
        return Result("unavailable")
    opened = False
    close_ok = True
    destroy_ok = True
    result = Result("unavailable")
    try:
        opened = api.open_clipboard(window)
        if opened:
            text = api.read_text()
            sequence = api.sequence()
            if text is not None and sequence:
                result = Result("ok", text=text, sequence=sequence)
    except Exception:
        result = Result("unavailable")
    finally:
        if opened:
            try:
                close_ok = bool(api.close_clipboard())
            except Exception:
                close_ok = False
        try:
            destroy_ok = bool(api.destroy_window(window))
        except Exception:
            destroy_ok = False
    if result.status == "ok" and (not close_ok or not destroy_ok):
        return Result("unavailable")
    return result


def _native_write(api, text: str, expected_sequence: int | None) -> Result:
    try:
        window = api.create_window()
    except Exception:
        return Result("unavailable")
    if not window:
        return Result("unavailable")
    opened = False
    handle = 0
    mutated = False
    result = Result("unavailable")
    close_ok = True
    destroy_ok = True
    try:
        opened = api.open_clipboard(window)
        if opened:
            current = api.sequence()
            if expected_sequence is not None and current != expected_sequence:
                result = Result("changed", sequence=current or None)
            else:
                handle = api.allocate_text(text)
                if handle:
                    # Once EmptyClipboard is called, a false return no longer
                    # proves that no prior-owner interaction or clearing occurred.
                    mutated = True
                    if not api.empty():
                        result = Result("uncertain")
                    elif api.set_text(handle):
                        handle = 0  # ownership transferred to the system
                        sequence = api.sequence()
                        result = (Result("ok", sequence=sequence) if sequence
                                  else Result("uncertain"))
                    else:
                        result = Result("uncertain")
    except Exception:
        result = Result("uncertain" if mutated else "unavailable")
    finally:
        if handle:
            try:
                api.free(handle)
            except Exception:
                pass
        if opened:
            try:
                close_ok = bool(api.close_clipboard())
            except Exception:
                close_ok = False
        try:
            destroy_ok = bool(api.destroy_window(window))
        except Exception:
            destroy_ok = False
    if result.status == "ok" and (not close_ok or not destroy_ok):
        return Result("uncertain")
    return result


def _decode_request(raw: bytes) -> tuple[str, str | None, int | None] | None:
    if not raw.endswith(b"\n") or len(raw) > MAX_FRAME_BYTES:
        return None
    try:
        value = json.loads(raw, object_pairs_hook=_unique_object)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError, RecursionError):
        return None
    if (not isinstance(value, dict) or type(value.get("v")) is not int
            or value.get("v") != PROTOCOL_VERSION):
        return None
    operation = value.get("op")
    if operation == "snapshot" and set(value) == {"v", "op"}:
        return operation, None, None
    if operation != "write" or not set(value) <= {
            "v", "op", "text_b64", "expected_sequence"}:
        return None
    encoded = value.get("text_b64")
    sequence = value.get("expected_sequence")
    if not isinstance(encoded, str):
        return None
    if sequence is not None and (
            isinstance(sequence, bool) or not isinstance(sequence, int)
            or sequence <= 0 or sequence > 0xFFFFFFFF):
        return None
    try:
        payload = base64.b64decode(encoded, validate=True)
        if len(payload) > MAX_TEXT_BYTES:
            return None
        text = payload.decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return None
    if "\0" in text:
        return None
    return operation, text, sequence


def _unique_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate protocol key")
        value[key] = item
    return value


def _encode_result(result: Result) -> bytes:
    value: dict[str, object] = {"v": PROTOCOL_VERSION, "status": result.status}
    if result.sequence is not None:
        value["sequence"] = result.sequence
    if result.text is not None:
        payload = result.text.encode("utf-8")
        if len(payload) > MAX_TEXT_BYTES:
            result = Result("unavailable")
            value = {"v": PROTOCOL_VERSION, "status": result.status}
        else:
            value["text_b64"] = base64.b64encode(payload).decode("ascii")
    encoded = json.dumps(value, separators=(",", ":")).encode("utf-8") + b"\n"
    return encoded if len(encoded) <= MAX_FRAME_BYTES else b'{"v":1,"status":"unavailable"}\n'


def run_worker() -> int:
    """Run one private request from inherited pipes; never print diagnostics."""
    if sys.stdin is None or sys.stdout is None:
        return 2
    source = getattr(sys.stdin, "buffer", sys.stdin)
    sink = getattr(sys.stdout, "buffer", sys.stdout)
    try:
        if source.isatty():
            return 2
        raw = source.readline(MAX_FRAME_BYTES + 1)
        if len(raw) > MAX_FRAME_BYTES or source.read(1):
            request = None
        else:
            request = _decode_request(raw)
        if request is None or sys.platform != "win32":
            sink.write(_encode_result(Result("unavailable")))
            sink.flush()
            return 2
        operation, text, sequence = request
        api = _win_api()
        result = (_native_snapshot(api) if operation == "snapshot" else
                  _native_write(api, text or "", sequence))
        sink.write(_encode_result(result))
        sink.flush()
        return 0
    except Exception:
        try:
            sink.write(_encode_result(Result("unavailable")))
            sink.flush()
        except Exception:
            pass
        return 2
