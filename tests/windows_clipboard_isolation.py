"""Stage-one Windows clipboard isolation probe.

This helper deliberately contains no clipboard calls.  It proves only that an
owned child and its explicitly routed nested child use the same private,
noninteractive window station and desktop while the test runner stays put.
"""
from __future__ import annotations

import ctypes
import json
import os
import subprocess
import sys
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from utterleaf.windows_clipboard import _create_job


VERSION = 1
MAX_FRAME = 4096
DEFAULT_TIMEOUT = 5.0
ERROR_ALREADY_EXISTS = 183
ERROR_ACCESS_DENIED = 5
CWF_CREATE_ONLY = 0x00000001
WINSTA_READATTRIBUTES = 0x0002
WINSTA_CREATEDESKTOP = 0x0008
DESKTOP_ALL_ACCESS = 0x01FF
UOI_FLAGS = 1
UOI_NAME = 2
UOI_IO = 6
WSF_VISIBLE = 0x0001


class _USEROBJECTFLAGS(ctypes.Structure):
    _fields_ = [
        ("fInherit", ctypes.c_int),
        ("fReserved", ctypes.c_int),
        ("dwFlags", ctypes.c_ulong),
    ]


@dataclass(frozen=True)
class Identity:
    station: str
    desktop: str
    station_flags: int
    desktop_is_input: bool


@dataclass(frozen=True)
class ProbeResult:
    status: str
    harness: Identity | None = None
    nested: Identity | None = None
    parent_preserved: bool = False
    reason: str = ""
    win32_error: int | None = None


class ProbeFailure(Exception):
    def __init__(self, reason: str, win32_error: int | None = None,
                 status: str = "failed") -> None:
        super().__init__(reason)
        self.reason = reason
        self.win32_error = win32_error
        self.status = status


def _last_error() -> int | None:
    getter = getattr(ctypes, "get_last_error", None)
    value = int(getter()) if getter is not None else 0
    return value or None


class NativeApi:
    """Small USER32 surface with no clipboard entry points."""

    def __init__(self) -> None:
        from ctypes import wintypes

        self.user32 = ctypes.WinDLL("user32", use_last_error=True)
        self.kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        u = self.user32
        k = self.kernel32
        u.CreateWindowStationW.argtypes = [
            wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p]
        u.CreateWindowStationW.restype = ctypes.c_void_p
        u.CloseWindowStation.argtypes = [ctypes.c_void_p]
        u.CloseWindowStation.restype = wintypes.BOOL
        u.SetProcessWindowStation.argtypes = [ctypes.c_void_p]
        u.SetProcessWindowStation.restype = wintypes.BOOL
        u.GetProcessWindowStation.restype = ctypes.c_void_p
        u.CreateDesktopW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR,
                                     ctypes.c_void_p, wintypes.DWORD,
                                     wintypes.DWORD, ctypes.c_void_p]
        u.CreateDesktopW.restype = ctypes.c_void_p
        u.CloseDesktop.argtypes = [ctypes.c_void_p]
        u.CloseDesktop.restype = wintypes.BOOL
        u.SetThreadDesktop.argtypes = [ctypes.c_void_p]
        u.SetThreadDesktop.restype = wintypes.BOOL
        u.GetThreadDesktop.argtypes = [wintypes.DWORD]
        u.GetThreadDesktop.restype = ctypes.c_void_p
        u.GetUserObjectInformationW.argtypes = [
            ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p,
            wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
        u.GetUserObjectInformationW.restype = wintypes.BOOL
        k.GetCurrentThreadId.restype = wintypes.DWORD
        k.IsProcessInJob.argtypes = [ctypes.c_void_p, ctypes.c_void_p,
                                     ctypes.POINTER(wintypes.BOOL)]
        k.IsProcessInJob.restype = wintypes.BOOL

    def create_station(self, name: str) -> tuple[int, int]:
        ctypes.set_last_error(0)
        handle = int(self.user32.CreateWindowStationW(
            name, CWF_CREATE_ONLY,
            WINSTA_READATTRIBUTES | WINSTA_CREATEDESKTOP, None) or 0)
        return handle, ctypes.get_last_error()

    def close_station(self, handle: int) -> bool:
        return bool(self.user32.CloseWindowStation(ctypes.c_void_p(handle)))

    def set_station(self, handle: int) -> bool:
        return bool(self.user32.SetProcessWindowStation(ctypes.c_void_p(handle)))

    def current_station(self) -> int:
        return int(self.user32.GetProcessWindowStation() or 0)

    def create_desktop(self, name: str) -> tuple[int, int]:
        ctypes.set_last_error(0)
        handle = int(self.user32.CreateDesktopW(
            name, None, None, 0, DESKTOP_ALL_ACCESS, None) or 0)
        return handle, ctypes.get_last_error()

    def close_desktop(self, handle: int) -> bool:
        return bool(self.user32.CloseDesktop(ctypes.c_void_p(handle)))

    def set_desktop(self, handle: int) -> bool:
        return bool(self.user32.SetThreadDesktop(ctypes.c_void_p(handle)))

    def current_desktop(self) -> int:
        thread_id = self.kernel32.GetCurrentThreadId()
        return int(self.user32.GetThreadDesktop(thread_id) or 0)

    def object_name(self, handle: int) -> str:
        from ctypes import wintypes

        needed = wintypes.DWORD()
        self.user32.GetUserObjectInformationW(
            ctypes.c_void_p(handle), UOI_NAME, None, 0, ctypes.byref(needed))
        if not needed.value or needed.value > 1024:
            raise ProbeFailure("identity-name-size", _last_error())
        buffer = ctypes.create_unicode_buffer(
            (needed.value + ctypes.sizeof(ctypes.c_wchar) - 1)
            // ctypes.sizeof(ctypes.c_wchar))
        if not self.user32.GetUserObjectInformationW(
                ctypes.c_void_p(handle), UOI_NAME, buffer,
                ctypes.sizeof(buffer), ctypes.byref(needed)):
            raise ProbeFailure("identity-name-query", _last_error())
        value = buffer.value
        if not value or len(value) > 255:
            raise ProbeFailure("identity-name-invalid")
        return value

    def station_flags(self, handle: int) -> int:
        flags = _USEROBJECTFLAGS()
        needed = ctypes.c_ulong()
        if not self.user32.GetUserObjectInformationW(
                ctypes.c_void_p(handle), UOI_FLAGS, ctypes.byref(flags),
                ctypes.sizeof(flags), ctypes.byref(needed)):
            raise ProbeFailure("identity-station-flags", _last_error())
        return int(flags.dwFlags)

    def desktop_is_input(self, handle: int) -> bool:
        value = ctypes.c_int()
        needed = ctypes.c_ulong()
        if not self.user32.GetUserObjectInformationW(
                ctypes.c_void_p(handle), UOI_IO, ctypes.byref(value),
                ctypes.sizeof(value), ctypes.byref(needed)):
            raise ProbeFailure("identity-desktop-input", _last_error())
        return bool(value.value)

    def process_in_job(self, process: subprocess.Popen[bytes]) -> bool:
        from ctypes import wintypes

        value = wintypes.BOOL()
        if not self.kernel32.IsProcessInJob(
                ctypes.c_void_p(int(process._handle)), None,
                ctypes.byref(value)):
            raise ProbeFailure("nested-job-query", _last_error())
        return bool(value.value)


class _STARTUPINFOW(ctypes.Structure):
    _fields_ = [
        ("cb", ctypes.c_ulong), ("lpReserved", ctypes.c_wchar_p),
        ("lpDesktop", ctypes.c_wchar_p), ("lpTitle", ctypes.c_wchar_p),
        ("dwX", ctypes.c_ulong), ("dwY", ctypes.c_ulong),
        ("dwXSize", ctypes.c_ulong), ("dwYSize", ctypes.c_ulong),
        ("dwXCountChars", ctypes.c_ulong), ("dwYCountChars", ctypes.c_ulong),
        ("dwFillAttribute", ctypes.c_ulong), ("dwFlags", ctypes.c_ulong),
        ("wShowWindow", ctypes.c_ushort), ("cbReserved2", ctypes.c_ushort),
        ("lpReserved2", ctypes.c_void_p), ("hStdInput", ctypes.c_void_p),
        ("hStdOutput", ctypes.c_void_p), ("hStdError", ctypes.c_void_p),
    ]


class _PROCESS_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("hProcess", ctypes.c_void_p), ("hThread", ctypes.c_void_p),
        ("dwProcessId", ctypes.c_ulong), ("dwThreadId", ctypes.c_ulong),
    ]


class _STARTUPINFOEXW(ctypes.Structure):
    _fields_ = [("StartupInfo", _STARTUPINFOW), ("lpAttributeList", ctypes.c_void_p)]


class BoundProcess:
    """Exact process and pipe ownership for an lpDesktop-bound child."""

    def __init__(self, kernel32, handle: int, stdin, stdout) -> None:
        self._kernel32 = kernel32
        self._handle = handle
        self.stdin = stdin
        self.stdout = stdout
        self.returncode: int | None = None

    def poll(self):
        if self.returncode is not None:
            return self.returncode
        if self._kernel32.WaitForSingleObject(ctypes.c_void_p(self._handle), 0) == 0:
            self.returncode = self._exit_code()
        return self.returncode

    def _exit_code(self) -> int:
        from ctypes import wintypes

        code = wintypes.DWORD()
        if not self._kernel32.GetExitCodeProcess(
                ctypes.c_void_p(self._handle), ctypes.byref(code)):
            raise OSError("child exit-code query failed")
        return int(code.value)

    def wait(self, timeout=None):
        milliseconds = 0xFFFFFFFF if timeout is None else max(0, int(timeout * 1000))
        result = self._kernel32.WaitForSingleObject(
            ctypes.c_void_p(self._handle), milliseconds)
        if result == 0x102:
            raise subprocess.TimeoutExpired(_command("nested"), timeout)
        if result != 0:
            raise OSError("child wait failed")
        self.returncode = self._exit_code()
        return self.returncode

    def terminate(self):
        if self.poll() is None:
            self._kernel32.TerminateProcess(ctypes.c_void_p(self._handle), 2)

    kill = terminate

    def communicate(self, request: bytes, timeout: float):
        self.stdin.write(request)
        self.stdin.close()
        self.wait(timeout)
        output = self.stdout.read(MAX_FRAME + 1)
        self.stdout.close()
        return output, b""

    def close(self) -> None:
        for stream in (self.stdin, self.stdout):
            try:
                if not stream.closed:
                    stream.close()
            except OSError:
                pass
        if self._handle:
            self._kernel32.CloseHandle(ctypes.c_void_p(self._handle))
            self._handle = 0


class _PipeOpenError(OSError):
    def __init__(self, consumed: bool) -> None:
        super().__init__("pipe stream creation failed")
        self.consumed = consumed


def _load_kernel32():
    return ctypes.WinDLL("kernel32", use_last_error=True)


def _open_pipe_file(handle: int, flags: int, mode: str):
    import msvcrt

    try:
        descriptor = msvcrt.open_osfhandle(handle, flags)
    except OSError as exc:
        raise _PipeOpenError(False) from exc
    try:
        return os.fdopen(descriptor, mode, buffering=0)
    except Exception as exc:
        os.close(descriptor)
        raise _PipeOpenError(True) from exc


def _create_bound_process(mode: str, desktop: str) -> BoundProcess:
    """Create a hidden child on exactly ``desktop`` with owned binary pipes."""
    from ctypes import wintypes

    kernel32 = _load_kernel32()
    kernel32.CreatePipe.argtypes = [ctypes.POINTER(ctypes.c_void_p),
                                    ctypes.POINTER(ctypes.c_void_p),
                                    ctypes.c_void_p, wintypes.DWORD]
    kernel32.CreatePipe.restype = wintypes.BOOL
    kernel32.SetHandleInformation.argtypes = [ctypes.c_void_p, wintypes.DWORD,
                                              wintypes.DWORD]
    kernel32.SetHandleInformation.restype = wintypes.BOOL
    kernel32.CreateProcessW.argtypes = [
        wintypes.LPCWSTR, wintypes.LPWSTR, ctypes.c_void_p, ctypes.c_void_p,
        wintypes.BOOL, wintypes.DWORD, ctypes.c_void_p, wintypes.LPCWSTR,
        ctypes.POINTER(_STARTUPINFOW), ctypes.POINTER(_PROCESS_INFORMATION)]
    kernel32.CreateProcessW.restype = wintypes.BOOL
    kernel32.WaitForSingleObject.argtypes = [ctypes.c_void_p, wintypes.DWORD]
    kernel32.WaitForSingleObject.restype = wintypes.DWORD
    kernel32.GetExitCodeProcess.argtypes = [ctypes.c_void_p,
                                            ctypes.POINTER(wintypes.DWORD)]
    kernel32.GetExitCodeProcess.restype = wintypes.BOOL
    kernel32.TerminateProcess.argtypes = [ctypes.c_void_p, wintypes.UINT]
    kernel32.TerminateProcess.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    kernel32.CloseHandle.restype = wintypes.BOOL
    kernel32.InitializeProcThreadAttributeList.argtypes = [
        ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD,
        ctypes.POINTER(ctypes.c_size_t)]
    kernel32.InitializeProcThreadAttributeList.restype = wintypes.BOOL
    kernel32.UpdateProcThreadAttribute.argtypes = [
        ctypes.c_void_p, wintypes.DWORD, ctypes.c_size_t, ctypes.c_void_p,
        ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p]
    kernel32.UpdateProcThreadAttribute.restype = wintypes.BOOL
    kernel32.DeleteProcThreadAttributeList.argtypes = [ctypes.c_void_p]

    child_in = ctypes.c_void_p()
    parent_in = ctypes.c_void_p()
    parent_out = ctypes.c_void_p()
    child_out = ctypes.c_void_p()
    owned: set[int] = set()
    streams = []
    attributes = None
    attributes_initialized = False
    process_handle = 0
    handed_off = False
    try:
        if not kernel32.CreatePipe(ctypes.byref(child_in), ctypes.byref(parent_in), None, 0):
            raise OSError("stdin pipe creation failed")
        owned.update((int(child_in.value), int(parent_in.value)))
        if not kernel32.CreatePipe(ctypes.byref(parent_out), ctypes.byref(child_out), None, 0):
            raise OSError("stdout pipe creation failed")
        owned.update((int(parent_out.value), int(child_out.value)))
        # Only the two child pipe ends are inheritable. Window-station and desktop
        # handles were created with NULL security attributes and are noninherited.
        for handle, inheritable in ((child_in.value, True), (child_out.value, True),
                                    (parent_in.value, False), (parent_out.value, False)):
            if not kernel32.SetHandleInformation(
                    ctypes.c_void_p(handle), 1, 1 if inheritable else 0):
                raise OSError("pipe inheritance setup failed")

        attribute_size = ctypes.c_size_t()
        kernel32.InitializeProcThreadAttributeList(None, 1, 0,
                                                   ctypes.byref(attribute_size))
        if not attribute_size.value or attribute_size.value > 64 * 1024:
            raise OSError("invalid process attribute-list size")
        attributes = ctypes.create_string_buffer(attribute_size.value)
        if not kernel32.InitializeProcThreadAttributeList(
                attributes, 1, 0, ctypes.byref(attribute_size)):
            raise OSError("process attribute-list setup failed")
        attributes_initialized = True
        inherited = (ctypes.c_void_p * 2)(child_in.value, child_out.value)
        if not kernel32.UpdateProcThreadAttribute(
                attributes, 0, 0x00020002,
                ctypes.cast(inherited, ctypes.c_void_p), ctypes.sizeof(inherited),
                None, None):
            raise OSError("restricted handle-list setup failed")

        startup = _STARTUPINFOEXW()
        startup.StartupInfo.cb = ctypes.sizeof(startup)
        startup.StartupInfo.lpDesktop = desktop
        startup.StartupInfo.dwFlags = 0x00000101  # USESTDHANDLES | USESHOWWINDOW
        startup.StartupInfo.wShowWindow = 0
        startup.StartupInfo.hStdInput = child_in.value
        startup.StartupInfo.hStdOutput = child_out.value
        startup.StartupInfo.hStdError = child_out.value
        startup.lpAttributeList = ctypes.cast(attributes, ctypes.c_void_p)
        info = _PROCESS_INFORMATION()
        command = ctypes.create_unicode_buffer(subprocess.list2cmdline(_command(mode)))
        if not kernel32.CreateProcessW(
                None, command, None, None, True,
                getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000) | 0x00080000,
                None, None, ctypes.cast(ctypes.byref(startup),
                                       ctypes.POINTER(_STARTUPINFOW)),
                ctypes.byref(info)):
            raise OSError("bound child creation failed")
        process_handle = int(info.hProcess)
        owned.add(process_handle)
        owned.add(int(info.hThread))
        for handle in (int(info.hThread), int(child_in.value), int(child_out.value)):
            if kernel32.CloseHandle(ctypes.c_void_p(handle)):
                owned.discard(handle)
        try:
            stdin = _open_pipe_file(int(parent_in.value), os.O_WRONLY, "wb")
        except _PipeOpenError as exc:
            if exc.consumed:
                owned.discard(int(parent_in.value))
            raise
        streams.append(stdin)
        owned.discard(int(parent_in.value))
        try:
            stdout = _open_pipe_file(int(parent_out.value), os.O_RDONLY, "rb")
        except _PipeOpenError as exc:
            if exc.consumed:
                owned.discard(int(parent_out.value))
            raise
        streams.append(stdout)
        owned.discard(int(parent_out.value))
        owned.discard(process_handle)
        handed_off = True
        return BoundProcess(kernel32, process_handle, stdin, stdout)
    finally:
        if attributes_initialized:
            kernel32.DeleteProcThreadAttributeList(attributes)
        if process_handle and not handed_off:
            kernel32.TerminateProcess(ctypes.c_void_p(process_handle), 2)
            kernel32.WaitForSingleObject(ctypes.c_void_p(process_handle), 500)
        if not handed_off:
            for stream in streams:
                try:
                    stream.close()
                except OSError:
                    pass
        for handle in owned:
            kernel32.CloseHandle(ctypes.c_void_p(handle))


def _current_identity(api: NativeApi) -> Identity:
    station = api.current_station()
    desktop = api.current_desktop()
    if not station or not desktop:
        raise ProbeFailure("identity-handle", _last_error())
    return Identity(api.object_name(station), api.object_name(desktop),
                    api.station_flags(station), api.desktop_is_input(desktop))


def _is_private(identity: Identity, expected_station: str | None = None,
                expected_desktop: str | None = None) -> bool:
    return bool(
        identity.station.casefold() != "winsta0"
        and not (identity.station_flags & WSF_VISIBLE)
        and not identity.desktop_is_input
        and (expected_station is None or identity.station == expected_station)
        and (expected_desktop is None or identity.desktop == expected_desktop)
    )


def _encode(payload: dict[str, Any]) -> bytes:
    data = json.dumps(payload, ensure_ascii=True, separators=(",", ":")).encode("ascii")
    if len(data) + 1 > MAX_FRAME:
        raise ValueError("protocol frame too large")
    return data + b"\n"


def _decode(data: bytes) -> dict[str, Any] | None:
    if not data or len(data) > MAX_FRAME or not data.endswith(b"\n"):
        return None
    try:
        value = json.loads(data.decode("ascii"))
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError):
        return None
    return value if isinstance(value, dict) else None


def _parse_identity(value: Any) -> Identity | None:
    if not isinstance(value, dict) or set(value) != {
            "station", "desktop", "station_flags", "desktop_is_input"}:
        return None
    station = value.get("station")
    desktop = value.get("desktop")
    flags = value.get("station_flags")
    is_input = value.get("desktop_is_input")
    if (not isinstance(station, str) or not station or len(station) > 255
            or not isinstance(desktop, str) or not desktop or len(desktop) > 255
            or not isinstance(flags, int) or isinstance(flags, bool) or flags < 0
            or type(is_input) is not bool):
        return None
    return Identity(station, desktop, flags, is_input)


def _command(mode: str) -> list[str]:
    return [sys.executable, str(Path(__file__).resolve()), mode]


def _startupinfo():
    info = subprocess.STARTUPINFO()
    info.dwFlags |= getattr(subprocess, "STARTF_USESHOWWINDOW", 1)
    info.wShowWindow = 0
    return info


def _popen(mode: str, *, desktop: str | None = None) -> subprocess.Popen[bytes]:
    if desktop is not None:
        return _create_bound_process(mode, desktop)
    return subprocess.Popen(
        _command(mode), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL, close_fds=True,
        startupinfo=_startupinfo(),
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def _stop_owned(process: subprocess.Popen[bytes], job=None) -> bool:
    reaped = False
    try:
        if job is not None:
            job.close()
        try:
            process.wait(timeout=0.5)
        except subprocess.TimeoutExpired:
            process.terminate()
            try:
                process.wait(timeout=0.5)
            except subprocess.TimeoutExpired:
                process.kill()
                try:
                    process.wait(timeout=0.5)
                except (subprocess.TimeoutExpired, OSError):
                    pass
        reaped = process.poll() is not None
    except OSError:
        reaped = False
    finally:
        close = getattr(process, "close", None)
        if close is not None:
            try:
                close()
            except OSError:
                pass
        else:
            for stream in (getattr(process, "stdin", None),
                           getattr(process, "stdout", None)):
                try:
                    if stream is not None:
                        stream.close()
                except OSError:
                    pass
    return reaped


def _exchange(process: subprocess.Popen[bytes], request: dict[str, Any],
              timeout: float) -> tuple[int, bytes]:
    output, _ = process.communicate(_encode(request), timeout=timeout)
    if len(output) > MAX_FRAME:
        raise ValueError("response frame too large")
    return int(process.returncode or 0), output


def run_probe(*, timeout: float = DEFAULT_TIMEOUT) -> ProbeResult:
    """Run the opt-in native identity probe; never call a clipboard API."""
    if sys.platform != "win32":
        return ProbeResult("unavailable", reason="platform")
    try:
        api = NativeApi()
        before = _current_identity(api)
        job = _create_job()
        if job is None:
            return ProbeResult("unavailable", reason="job-create")
    except ProbeFailure as exc:
        return ProbeResult("unavailable", reason=f"parent-before-{exc.reason}",
                           win32_error=exc.win32_error)
    except Exception:
        return ProbeResult("unavailable", reason="parent-setup")
    try:
        process = _popen("harness")
    except Exception:
        job.close()
        return ProbeResult("unavailable", reason="harness-launch",
                           win32_error=_last_error())

    status = "failed"
    harness = None
    nested = None
    reason = ""
    win32_error = None
    try:
        if not job.assign(process):
            status = "unavailable"
            reason = "harness-job-assign"
        else:
            code, raw = _exchange(process, {"v": VERSION, "op": "names"}, timeout)
            payload = _decode(raw)
            if payload is None:
                reason = "harness-response"
            elif payload.get("status") != "ok":
                if payload.get("status") == "unavailable":
                    status = "unavailable"
                value = payload.get("reason")
                error = payload.get("win32_error")
                reason = value if isinstance(value, str) and len(value) <= 80 else "harness-failed"
                win32_error = (error if isinstance(error, int) and not isinstance(error, bool)
                               and 0 < error <= 0xFFFFFFFF else None)
            elif code != 0:
                reason = "harness-exit"
            else:
                harness = _parse_identity(payload.get("harness"))
                nested = _parse_identity(payload.get("nested"))
                if harness is None or nested is None:
                    reason = "identity-response"
                elif (_is_private(harness)
                        and _is_private(nested, harness.station, harness.desktop)):
                    status = "ok"
                else:
                    reason = "identity-private"
    except subprocess.TimeoutExpired:
        status = "failed"
        reason = "harness-timeout"
    except (KeyError, TypeError, ValueError, OSError):
        status = "failed"
        reason = "parent-exchange"
    finally:
        cleanup_ok = _stop_owned(process, job)
    try:
        preserved = before == _current_identity(api)
    except ProbeFailure as exc:
        preserved = False
        reason = f"parent-after-{exc.reason}"
        win32_error = exc.win32_error
    except OSError:
        preserved = False
        reason = "parent-after"
    if not cleanup_ok or not preserved:
        status = "failed"
        if not cleanup_ok:
            reason = "harness-cleanup"
    return ProbeResult(status, harness, nested, preserved, reason, win32_error)


def _nested_receipt(api: NativeApi, request: dict[str, Any]) -> dict[str, Any]:
    if request != {"v": VERSION, "op": "identify",
                   "station": request.get("station"),
                   "desktop": request.get("desktop")}:
        return {"v": VERSION, "status": "failed"}
    station = request.get("station")
    desktop = request.get("desktop")
    if not isinstance(station, str) or not isinstance(desktop, str):
        return {"v": VERSION, "status": "failed"}
    try:
        identity = _current_identity(api)
        if not _is_private(identity, station, desktop):
            raise ProbeFailure("nested-identity-private")
        return {"v": VERSION, "status": "ok", "identity": asdict(identity)}
    except ProbeFailure as exc:
        return {"v": VERSION, "status": "failed", "reason": exc.reason,
                "win32_error": exc.win32_error}


def _run_nested(api: NativeApi, identity: Identity,
                timeout: float = DEFAULT_TIMEOUT) -> Identity:
    process = _popen("nested", desktop=f"{identity.station}\\{identity.desktop}")
    nested = None
    failure = None
    try:
        if not api.process_in_job(process):
            raise ProbeFailure("nested-job-membership")
        code, raw = _exchange(process, {
            "v": VERSION, "op": "identify", "station": identity.station,
            "desktop": identity.desktop}, timeout)
        payload = _decode(raw)
        if payload is None:
            raise ProbeFailure("nested-response")
        if payload.get("status") != "ok":
            error = payload.get("win32_error")
            raise ProbeFailure(str(payload.get("reason") or "nested-failed"),
                               error if isinstance(error, int) else None)
        if code != 0:
            raise ProbeFailure("nested-exit")
        nested = _parse_identity(payload.get("identity"))
        if nested is None:
            raise ProbeFailure("nested-identity-response")
        if not _is_private(nested, identity.station, identity.desktop):
            raise ProbeFailure("nested-identity-mismatch")
    except Exception as exc:
        failure = exc
    finally:
        cleanup_ok = _stop_owned(process)
    if failure is not None:
        raise failure
    if not cleanup_ok or nested is None:
        raise ProbeFailure("nested-cleanup")
    return nested


def _harness_receipt(api: NativeApi) -> dict[str, Any]:
    requested_station_name = f"UtterleafIsolation-{uuid.uuid4().hex}"
    station, station_error = api.create_station(requested_station_name)
    selected_station = False
    desktop = 0
    selected_desktop = False
    try:
        # GetLastError is defined only for a NULL return. CWF_CREATE_ONLY makes
        # any successful handle proof that this is a newly created station.
        if not station:
            reason = ("station-create-existing" if station_error == ERROR_ALREADY_EXISTS
                      else "station-create")
            status = "unavailable" if station_error == ERROR_ACCESS_DENIED else "failed"
            raise ProbeFailure(reason, station_error or None, status)
        if not api.set_station(station):
            raise ProbeFailure("station-select", _last_error())
        selected_station = True
        station_name = api.object_name(api.current_station())
        if station_name != requested_station_name:
            raise ProbeFailure("station-name-mismatch")
        desktop_name = f"UtterleafIsolation-{uuid.uuid4().hex}"
        desktop, desktop_error = api.create_desktop(desktop_name)
        # This UUID-named desktop is the first object created in the new station.
        # As above, LastError is meaningful only when the function returns NULL.
        if not desktop:
            reason = ("desktop-create-existing" if desktop_error == ERROR_ALREADY_EXISTS
                      else "desktop-create")
            raise ProbeFailure(reason, desktop_error or None)
        if not api.set_desktop(desktop):
            raise ProbeFailure("desktop-select", _last_error())
        selected_desktop = True
        identity = _current_identity(api)
        if not _is_private(identity, station_name, desktop_name):
            raise ProbeFailure("harness-identity-private")
        nested = _run_nested(api, identity)
        return {"v": VERSION, "status": "ok", "harness": asdict(identity),
                "nested": asdict(nested)}
    except ProbeFailure as exc:
        return {"v": VERSION, "status": exc.status, "reason": exc.reason,
                "win32_error": exc.win32_error}
    except Exception:
        return {"v": VERSION, "status": "failed", "reason": "harness-exception",
                "win32_error": _last_error()}
    finally:
        # Selected user objects are process/thread lifetime resources and cannot
        # be closed here. Unselected handles remain ours and must be closed.
        if desktop and not selected_desktop:
            api.close_desktop(desktop)
        if station and not selected_station:
            api.close_station(station)


def _read_request() -> dict[str, Any] | None:
    stream = getattr(sys.stdin, "buffer", None)
    if stream is None or sys.stdin.isatty():
        return None
    frame = stream.readline(MAX_FRAME + 1)
    if len(frame) > MAX_FRAME or stream.read(1):
        return None
    return _decode(frame)


def _write_response(payload: dict[str, Any]) -> int:
    stream = getattr(sys.stdout, "buffer", None)
    if stream is None or sys.stdout.isatty():
        return 2
    try:
        stream.write(_encode(payload))
        stream.flush()
        return 0 if payload.get("status") == "ok" else 2
    except (BrokenPipeError, OSError, ValueError):
        return 2


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if sys.platform != "win32" or args not in (["harness"], ["nested"]):
        return 2
    request = _read_request()
    if request is None:
        return 2
    try:
        api = NativeApi()
        if args == ["harness"]:
            if request != {"v": VERSION, "op": "names"}:
                return 2
            return _write_response(_harness_receipt(api))
        return _write_response(_nested_receipt(api, request))
    except Exception:
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
