"""Real Windows ownership checks for desktop OBS pairing setup."""
from __future__ import annotations

import ctypes as C
import os
from pathlib import Path
import struct
import subprocess
import sys
import time

import pytest

from utterleaf import obs_pairing_store as pairing


pytestmark = pytest.mark.skipif(
    sys.platform != "win32", reason="Windows pairing owner lock")

_FSCTL_SET_REPARSE_POINT = 0x000900A4
_FSCTL_DELETE_REPARSE_POINT = 0x000900AC
_IO_REPARSE_TAG_MOUNT_POINT = 0xA0000003
_FILE_FLAG_OPEN_REPARSE_POINT = 0x00200000
_FILE_FLAG_BACKUP_SEMANTICS = 0x02000000
_INVALID_HANDLE = C.c_void_p(-1).value


def _owner(store: pairing.ObsPairingStore) -> Path:
    return Path(store._owner_path)  # noqa: SLF001 - exact sentinel fixture


def _child_claim(root: str) -> int:
    store = pairing.ObsPairingStore(_root=Path(root))
    try:
        store.claim_owner()
    except pairing.PairingStoreError:
        store.close()
        return 3
    store.close()
    return 0


def _child_linger(marker: str) -> int:
    Path(marker).write_bytes(b"ready")
    return 0 if sys.stdin.buffer.read(1) == b"x" else 4


def _run_claim(root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, __file__, "--claim", str(root)],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )


def _junction_api():
    kernel32 = C.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateFileW.argtypes = [C.c_wchar_p, C.c_uint32, C.c_uint32,
                                     C.c_void_p, C.c_uint32, C.c_uint32, C.c_void_p]
    kernel32.CreateFileW.restype = C.c_void_p
    kernel32.DeviceIoControl.argtypes = [C.c_void_p, C.c_uint32, C.c_void_p,
                                         C.c_uint32, C.c_void_p, C.c_uint32,
                                         C.POINTER(C.c_uint32), C.c_void_p]
    kernel32.DeviceIoControl.restype = C.c_int
    kernel32.CloseHandle.argtypes = [C.c_void_p]
    kernel32.CloseHandle.restype = C.c_int
    return kernel32


def _make_junction(target: Path, junction: Path) -> None:
    target.mkdir()
    junction.mkdir()
    kernel32 = _junction_api()
    handle = kernel32.CreateFileW(
        str(junction), 0x40000000, 0, None, 3,
        _FILE_FLAG_OPEN_REPARSE_POINT | _FILE_FLAG_BACKUP_SEMANTICS, None)
    if handle in (None, _INVALID_HANDLE):
        os.rmdir(junction)
        raise RuntimeError("could not open junction fixture")
    try:
        substitute = ("\\??\\" + str(target)).encode("utf-16-le")
        printed = str(target).encode("utf-16-le")
        names = substitute + b"\0\0" + printed + b"\0\0"
        header = struct.pack(
            "<LHHHHHH", _IO_REPARSE_TAG_MOUNT_POINT, 8 + len(names), 0,
            0, len(substitute), len(substitute) + 2, len(printed))
        buffer = C.create_string_buffer(header + names)
        returned = C.c_uint32()
        if not kernel32.DeviceIoControl(
                handle, _FSCTL_SET_REPARSE_POINT, buffer, len(header) + len(names),
                None, 0, C.byref(returned), None):
            raise RuntimeError("could not create junction fixture")
    finally:
        kernel32.CloseHandle(handle)


def _remove_junction(junction: Path) -> None:
    kernel32 = _junction_api()
    handle = kernel32.CreateFileW(
        str(junction), 0x40000000, 0, None, 3,
        _FILE_FLAG_OPEN_REPARSE_POINT | _FILE_FLAG_BACKUP_SEMANTICS, None)
    if handle in (None, _INVALID_HANDLE):
        raise RuntimeError("could not reopen junction fixture")
    try:
        header = C.create_string_buffer(
            struct.pack("<LHH", _IO_REPARSE_TAG_MOUNT_POINT, 0, 0))
        returned = C.c_uint32()
        if not kernel32.DeviceIoControl(
                handle, _FSCTL_DELETE_REPARSE_POINT, header,
                struct.calcsize("<LHH"),
                None, 0, C.byref(returned), None):
            raise RuntimeError("could not remove junction fixture")
    finally:
        kernel32.CloseHandle(handle)
    os.rmdir(junction)


def test_same_process_claim_is_idempotent_exclusive_and_reusable(tmp_path):
    first = pairing.ObsPairingStore(_root=tmp_path)
    second = pairing.ObsPairingStore(_root=tmp_path)
    try:
        first.claim_owner()
        first.claim_owner()
        with pytest.raises(pairing.PairingStoreError):
            second.claim_owner()
        first.close()
        assert _owner(first).read_bytes() == b""
        second.claim_owner()
        second.claim_owner()
    finally:
        first.close()
        second.close()
        second.close()


def test_actual_child_contends_then_succeeds_after_close(tmp_path):
    owner = pairing.ObsPairingStore(_root=tmp_path)
    owner.claim_owner()
    refused = _run_claim(tmp_path)
    assert refused.returncode == 3
    assert refused.stdout == "" and refused.stderr == ""
    owner.close()
    successor = _run_claim(tmp_path)
    assert successor.returncode == 0
    assert successor.stdout == "" and successor.stderr == ""


def test_owner_handle_is_not_inherited_by_child(tmp_path):
    owner = pairing.ObsPairingStore(_root=tmp_path)
    owner.claim_owner()
    marker = tmp_path / "child-ready"
    process = subprocess.Popen(
        [sys.executable, __file__, "--linger", str(marker)],
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=False,
    )
    try:
        deadline = time.monotonic() + 5
        while not marker.exists() and process.poll() is None and time.monotonic() < deadline:
            time.sleep(0.01)
        assert marker.read_bytes() == b"ready"
        owner.close()
        successor = pairing.ObsPairingStore(_root=tmp_path)
        try:
            successor.claim_owner()
        finally:
            successor.close()
        assert process.stdin is not None
        process.stdin.write(b"x")
        process.stdin.flush()
        assert process.wait(timeout=5) == 0
    finally:
        owner.close()
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)


def test_nonempty_owner_sentinel_is_refused_without_change(tmp_path):
    seed = pairing.ObsPairingStore(_root=tmp_path)
    seed.claim_owner()
    path = _owner(seed)
    seed.close()
    path.write_bytes(b"occupied")
    contender = pairing.ObsPairingStore(_root=tmp_path)
    try:
        with pytest.raises(pairing.PairingStoreError, match="owner lock"):
            contender.claim_owner()
        assert path.read_bytes() == b"occupied"
    finally:
        contender.close()


def test_inherited_acl_owner_sentinel_is_refused_without_repair(tmp_path):
    seed = pairing.ObsPairingStore(_root=tmp_path)
    path = _owner(seed)
    seed.close()
    path.write_bytes(b"")
    contender = pairing.ObsPairingStore(_root=tmp_path)
    try:
        with pytest.raises(pairing.PairingStoreError, match="permissions"):
            contender.claim_owner()
        assert path.read_bytes() == b""
    finally:
        contender.close()


def test_reparse_owner_sentinel_is_refused_without_following_target(tmp_path):
    seed = pairing.ObsPairingStore(_root=tmp_path)
    junction = _owner(seed)
    seed.close()
    target = tmp_path / "junction-target"
    _make_junction(target, junction)
    try:
        contender = pairing.ObsPairingStore(_root=tmp_path)
        try:
            with pytest.raises(pairing.PairingStoreError):
                contender.claim_owner()
            assert list(target.iterdir()) == []
        finally:
            contender.close()
    finally:
        _remove_junction(junction)


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--claim":
        raise SystemExit(_child_claim(sys.argv[2]))
    if len(sys.argv) == 3 and sys.argv[1] == "--linger":
        raise SystemExit(_child_linger(sys.argv[2]))
    raise SystemExit(5)
