"""Harmless native Windows pipe/TCP child used by focused tests only."""

from __future__ import annotations

from dataclasses import dataclass
import subprocess
import sys
import threading


@dataclass(frozen=True)
class NativePipeServer:
    process: subprocess.Popen
    pipe_name: str
    server_pid: int
    tcp_port: int | None


_CHILD = r'''
import ctypes, hashlib, hmac, os, socket, struct, sys, threading, time
from ctypes import wintypes

watchdog = threading.Timer(8, lambda: os._exit(90))
watchdog.daemon = True
watchdog.start()

name, mode, payload_hex = sys.argv[1:]
payload = bytes.fromhex(payload_hex)
session_id = bytes.fromhex(name.rsplit(".", 1)[1])

k = ctypes.WinDLL("kernel32", use_last_error=True)
INVALID = ctypes.c_void_p(-1).value
DWORD = ctypes.c_uint32
HANDLE = ctypes.c_void_p
k.CreateNamedPipeW.argtypes = [wintypes.LPCWSTR, DWORD, DWORD, DWORD, DWORD, DWORD, DWORD, ctypes.c_void_p]
k.CreateNamedPipeW.restype = HANDLE
k.ConnectNamedPipe.argtypes = [HANDLE, ctypes.c_void_p]
k.ConnectNamedPipe.restype = ctypes.c_int32
k.WriteFile.argtypes = [HANDLE, ctypes.c_void_p, DWORD, ctypes.POINTER(DWORD), ctypes.c_void_p]
k.WriteFile.restype = ctypes.c_int32
k.ReadFile.argtypes = [HANDLE, ctypes.c_void_p, DWORD, ctypes.POINTER(DWORD), ctypes.c_void_p]
k.ReadFile.restype = ctypes.c_int32
k.CloseHandle.argtypes = [HANDLE]
k.CloseHandle.restype = ctypes.c_int32

h = k.CreateNamedPipeW(name, 3, 0, 1, 65536, 65536, 0, None)
if int(h) == INVALID:
    raise SystemExit(10)

listener = None
port = 0
if mode == "audio":
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    port = listener.getsockname()[1]

print(f"READY {os.getpid()} {port}", flush=True)

control_done = threading.Event()
def hold_control():
    connection = None
    try:
        connection, _address = listener.accept()
        connection.settimeout(7)
        while connection.recv(1024):
            pass
    except (OSError, TimeoutError):
        pass
    finally:
        if connection is not None:
            connection.close()
        listener.close()
        control_done.set()

if listener is not None:
    threading.Thread(target=hold_control, daemon=True).start()

if not k.ConnectNamedPipe(h, None) and ctypes.get_last_error() != 535:
    raise SystemExit(11)

def write_all(data):
    offset = 0
    while offset < len(data):
        count = DWORD()
        chunk = data[offset:]
        if not k.WriteFile(h, chunk, len(chunk), ctypes.byref(count), None) or not count.value:
            raise SystemExit(12)
        offset += count.value

def read_exact(length):
    result = bytearray()
    while len(result) < length:
        buffer = ctypes.create_string_buffer(length - len(result))
        count = DWORD()
        if not k.ReadFile(h, buffer, len(buffer), ctypes.byref(count), None) or not count.value:
            raise SystemExit(13)
        result.extend(buffer.raw[:count.value])
    return bytes(result)

if mode == "exchange":
    write_all(payload[:3])
    time.sleep(.08)
    write_all(payload[3:])
    read_exact(1)
elif mode == "stall":
    time.sleep(3)
elif mode == "audio":
    hello = read_exact(56)
    header, secret = hello[:24], hello[24:]
    magic, version, kind, reserved, returned_session = struct.unpack("<4sBBH16s", header)
    if (magic, version, kind, reserved, returned_session) != (b"ULAH", 1, 1, 0, session_id):
        raise SystemExit(14)
    digest = hmac.digest(secret, b"Utterleaf OBS audio server ack v1\0" + header, "sha256")
    write_all(struct.pack("<4sBBH16s32s", b"ULAH", 1, 2, 0, session_id, digest))
    write_all(payload)
    buffer = ctypes.create_string_buffer(1)
    count = DWORD()
    k.ReadFile(h, buffer, 1, ctypes.byref(count), None)
elif mode == "observe":
    buffer = ctypes.create_string_buffer(56)
    count = DWORD()
    succeeded = k.ReadFile(h, buffer, 56, ctypes.byref(count), None)
    if not succeeded and ctypes.get_last_error() not in (109, 232):
        raise SystemExit(16)
    print(f"BYTES {count.value}", flush=True)
else:
    raise SystemExit(15)

k.CloseHandle(h)
'''


def start_native_pipe_server(
    mode: str,
    payload: bytes = b"",
    *,
    session_id: bytes | None = None,
) -> NativePipeServer:
    """Start a self-expiring native fixture and wait for bounded readiness."""
    if mode not in {"exchange", "stall", "audio", "observe"}:
        raise ValueError("unsupported fixture mode")
    if type(payload) is not bytes or len(payload) > 8_192:
        raise ValueError("invalid fixture payload")
    import secrets
    if session_id is None:
        session_id = secrets.token_bytes(16)
    if type(session_id) is not bytes or len(session_id) != 16:
        raise ValueError("invalid fixture session")
    pipe_name = rf"\\.\pipe\Utterleaf.OBS.{session_id.hex()}"
    executable = getattr(sys, "_base_executable", sys.executable)
    process = subprocess.Popen(
        [executable, "-c", _CHILD, pipe_name, mode, payload.hex()],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    ready: list[str] = []
    reader = threading.Thread(target=lambda: ready.append(process.stdout.readline()), daemon=True)
    reader.start()
    reader.join(3)
    if reader.is_alive() or not ready or not ready[0].startswith("READY "):
        process.wait(timeout=10)
        raise RuntimeError("native pipe fixture failed to start")
    fields = ready[0].split()
    if len(fields) != 3:
        process.wait(timeout=10)
        raise RuntimeError("native pipe fixture returned invalid readiness")
    port = int(fields[2])
    return NativePipeServer(
        process=process,
        pipe_name=pipe_name,
        server_pid=int(fields[1]),
        tcp_port=port or None,
    )
