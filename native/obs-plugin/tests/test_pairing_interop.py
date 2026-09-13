"""Real Windows native-store -> Python-store -> native authorization checks.

Uses only disposable directories, capabilities and a waiting child process.
No OBS application, consumer storage, network connection or audio is involved.
"""
# SPDX-License-Identifier: GPL-2.0-or-later
from __future__ import annotations

import ctypes as C
import hmac
import os
from pathlib import Path
import subprocess
import struct
import sys
import tempfile
import unittest

from utterleaf.obs_authorization import create_prepare_proof
from utterleaf import obs_pairing_store as pairing


_FSCTL_SET_REPARSE_POINT = 0x000900A4
_FSCTL_DELETE_REPARSE_POINT = 0x000900AC
_IO_REPARSE_TAG_MOUNT_POINT = 0xA0000003
_FILE_FLAG_OPEN_REPARSE_POINT = 0x00200000
_FILE_FLAG_BACKUP_SEMANTICS = 0x02000000
_INVALID_HANDLE = C.c_void_p(-1).value


def _owned_path(root: Path, child: Path) -> Path:
    """Check lexical containment without resolving a junction."""
    root_abs = Path(os.path.abspath(os.fspath(root)))
    child_abs = Path(os.path.abspath(os.fspath(child)))
    if os.path.commonpath((str(root_abs), str(child_abs))).casefold() != str(root_abs).casefold():
        raise AssertionError("junction fixture escaped its disposable root")
    return child_abs


def _make_junction(root: Path, target: Path, junction: Path) -> None:
    """Create one disposable mount-point reparse directory with Win32 APIs."""
    _owned_path(root, target)
    _owned_path(root, junction)
    target.mkdir()
    junction.mkdir()
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
    handle = kernel32.CreateFileW(
        str(junction), 0x40000000, 0, None, 3,
        _FILE_FLAG_OPEN_REPARSE_POINT | _FILE_FLAG_BACKUP_SEMANTICS, None)
    if handle in (None, _INVALID_HANDLE):
        os.rmdir(junction)
        raise RuntimeError(f"could not open junction fixture ({C.get_last_error()})")
    try:
        substitute = "\\??\\" + str(target).replace("/", "\\")
        printed = str(target).replace("/", "\\")
        substitute_bytes = substitute.encode("utf-16-le")
        printed_bytes = printed.encode("utf-16-le")
        # The mount-point buffer separates the names with a UTF-16 NUL;
        # offsets and lengths are byte counts and exclude the terminators.
        path_buffer = substitute_bytes + b"\0\0" + printed_bytes + b"\0\0"
        data = struct.pack("<LHHHHHH", _IO_REPARSE_TAG_MOUNT_POINT,
                           8 + len(path_buffer), 0, 0, len(substitute_bytes),
                           len(substitute_bytes) + 2, len(printed_bytes))
        buffer = C.create_string_buffer(data + path_buffer)
        returned = C.c_uint32()
        if not kernel32.DeviceIoControl(handle, _FSCTL_SET_REPARSE_POINT,
                                        buffer, len(data) + len(path_buffer),
                                        None, 0, C.byref(returned), None):
            error = C.get_last_error()
            raise RuntimeError(f"could not create junction fixture ({error})")
    except Exception:
        delete = C.create_string_buffer(struct.pack("<LHH", _IO_REPARSE_TAG_MOUNT_POINT, 0, 0))
        returned = C.c_uint32()
        kernel32.DeviceIoControl(handle, _FSCTL_DELETE_REPARSE_POINT,
                                 delete, struct.calcsize("<LHH"), None, 0,
                                 C.byref(returned), None)
        raise
    finally:
        kernel32.CloseHandle(handle)


def _remove_junction(root: Path, junction: Path) -> None:
    """Delete only the reparse point and directory; never traverse its target."""
    _owned_path(root, junction)
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
    handle = kernel32.CreateFileW(
        str(junction), 0x40000000, 0, None, 3,
        _FILE_FLAG_OPEN_REPARSE_POINT | _FILE_FLAG_BACKUP_SEMANTICS, None)
    if handle in (None, _INVALID_HANDLE):
        raise RuntimeError(f"could not reopen junction for cleanup ({C.get_last_error()})")
    try:
        delete = C.create_string_buffer(struct.pack("<LHH", _IO_REPARSE_TAG_MOUNT_POINT, 0, 0))
        returned = C.c_uint32()
        if not kernel32.DeviceIoControl(handle, _FSCTL_DELETE_REPARSE_POINT,
                                        delete, struct.calcsize("<LHH"), None, 0,
                                        C.byref(returned), None):
            raise RuntimeError(f"could not remove junction reparse point ({C.get_last_error()})")
    finally:
        kernel32.CloseHandle(handle)
    os.rmdir(junction)


class _Options(C.Structure):
    _fields_ = [("pid", C.c_uint32), ("session", C.c_ubyte * 16), ("mask", C.c_ubyte)]


class PairingInteropTests(unittest.TestCase):
    pairing_dll: Path
    authorization_dll: Path

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(prefix="pairing-interop-", dir=Path.cwd())
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        self.dll = C.WinDLL(str(self.pairing_dll))
        signatures = {
            "open_test_root": ([C.c_wchar_p, C.POINTER(C.c_void_p)], C.c_int),
            "destroy": ([C.c_void_p], None),
            "load": ([C.c_void_p, C.c_void_p], C.c_int),
            "create": ([C.c_void_p, C.c_void_p, C.c_void_p], C.c_int),
            "replace": ([C.c_void_p, C.c_void_p, C.c_void_p], C.c_int),
            "export": ([C.c_void_p, C.c_wchar_p, C.c_void_p], C.c_int),
            "forget": ([C.c_void_p], C.c_int),
        }
        for name, (args, result) in signatures.items():
            function = getattr(self.dll, "ul_pairing_store_" + name)
            function.argtypes, function.restype = args, result
        self.store = C.c_void_p()
        self.assertEqual(self.dll.ul_pairing_store_open_test_root(str(self.root), C.byref(self.store)), 0)
        self.assertTrue(self.store.value)
        self.addCleanup(self.dll.ul_pairing_store_destroy, self.store)
        self.key = (C.c_ubyte * 32)()
        self.addCleanup(C.memset, self.key, 0, 32)
        self.assertEqual(self.dll.ul_pairing_store_create(self.store, None, self.key), 0)
        self.assertTrue(any(self.key))

    def load_desktop(self, desktop):
        key = desktop.load()
        self.assertIsInstance(key, bytearray)
        self.addCleanup(pairing._wipe, key)
        return key

    def export(self, name="transfer.utterleaf-obs-pairing"):
        transfer = self.root / name
        self.assertEqual(self.dll.ul_pairing_store_export(self.store, str(transfer), None), 0)
        return transfer

    def test_native_export_import_reload_and_authorization(self):
        transfer = self.export()
        native_api = pairing._Native()
        # Native role-1 and role-2 records both decrypt in Python with matching
        # keys; Windows checks the ACL on each actual native-created file.
        native_path = self.root / "Utterleaf" / "obs-plugin" / "pairing-v1.dat"
        with native_api.opened(str(native_path)) as handle:
            native_key = pairing.decode_pairing_package(native_api.read(handle), pairing.ROLE_NATIVE)
        try:
            self.assertTrue(hmac.compare_digest(native_key, self.key))
        finally:
            pairing._wipe(native_key)
        with pairing.ObsPairingStore(_root=self.root) as desktop:
            self.assertIsNone(desktop.load())
            result = desktop.import_package(transfer)
            self.assertTrue(result.package_removed)
            self.assertFalse(result.replaced)
            self.assertFalse(transfer.exists())
        with pairing.ObsPairingStore(_root=self.root) as desktop:
            key = self.load_desktop(desktop)
            self.assertTrue(hmac.compare_digest(key, self.key))
            self.authorize(key)

    def authorize(self, key):
        native = C.WinDLL(str(self.authorization_dll))
        native.ul_authorizer_create.argtypes = [C.c_void_p]
        native.ul_authorizer_create.restype = C.c_void_p
        native.ul_authorizer_issue.argtypes = [C.c_void_p, C.c_uint32, C.c_void_p, C.c_ubyte, C.c_void_p]
        native.ul_authorizer_issue.restype = C.c_bool
        native.ul_authorizer_prepare.argtypes = [C.c_void_p, C.c_void_p, C.c_size_t,
                                                C.c_void_p, C.c_size_t, C.POINTER(_Options)]
        native.ul_authorizer_prepare.restype = C.c_void_p
        native.ul_authorizer_destroy.argtypes = [C.c_void_p]
        native.ul_authorizer_destroy.restype = None
        owner = native.ul_authorizer_create(self.key)
        self.assertTrue(owner)
        child = None
        try:
            child = subprocess.Popen([sys._base_executable, "-c",
                                      "import sys; sys.stdin.buffer.read(1)"],
                                     stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                                     stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW)
            session_bytes = bytes(range(16))
            session = (C.c_ubyte * 16).from_buffer_copy(session_bytes)
            challenge = (C.c_ubyte * 60)()
            self.assertTrue(native.ul_authorizer_issue(owner, child.pid, session, 9, challenge))
            proof = create_prepare_proof(key, bytes(challenge), client_pid=child.pid,
                                         session_id=session_bytes, additional_mix_mask=9)
            wire_proof = (C.c_ubyte * 32).from_buffer_copy(proof)
            options = _Options()
            admission = native.ul_authorizer_prepare(owner, challenge, 60, wire_proof, 32, C.byref(options))
            self.assertTrue(admission)
            self.assertEqual(options.pid, child.pid)
            self.assertEqual(bytes(options.session), session_bytes)
            self.assertEqual(options.mask, 9)
            self.assertFalse(native.ul_authorizer_prepare(owner, challenge, 60, wire_proof, 32, C.byref(options)))
        finally:
            # No admission worker/pipe handshake was started; this checks proof
            # interoperability and real process admission, not live PCM delivery.
            native.ul_authorizer_destroy(owner)
            if child is not None:
                if child.stdin:
                    child.stdin.close()
                try:
                    child.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait(timeout=5)

    def test_replacement_and_forgetting_are_separate(self):
        transfer = self.export()
        with pairing.ObsPairingStore(_root=self.root) as desktop:
            desktop.import_package(transfer)
            old = self.load_desktop(desktop)
            new = (C.c_ubyte * 32)()
            self.addCleanup(C.memset, new, 0, 32)
            self.assertEqual(self.dll.ul_pairing_store_replace(self.store, None, new), 0)
            self.assertFalse(hmac.compare_digest(old, new))
            transfer = self.export("replacement.utterleaf-obs-pairing")
            with self.assertRaises(pairing.PairingStoreError):
                desktop.import_package(transfer)
            self.assertTrue(transfer.exists())
            result = desktop.import_package(transfer, replace=True)
            self.assertTrue(result.replaced)
            self.assertTrue(hmac.compare_digest(self.load_desktop(desktop), new))
            self.assertEqual(self.dll.ul_pairing_store_forget(self.store), 0)
            self.assertTrue(hmac.compare_digest(self.load_desktop(desktop), new))
            self.assertTrue(desktop.forget())
            self.assertIsNone(desktop.load())
            self.assertEqual(self.dll.ul_pairing_store_load(self.store, new), 1)
            self.assertFalse(any(new))

    def test_export_never_overwrites_and_corruption_preserves_import(self):
        transfer = self.export()
        before = transfer.read_bytes()
        self.assertNotEqual(self.dll.ul_pairing_store_export(self.store, str(transfer), None), 0)
        self.assertEqual(transfer.read_bytes(), before)
        # Keep the private ACL while corrupting only the encrypted record.
        corrupt = bytearray(before)
        corrupt[-1] ^= 1
        transfer.write_bytes(corrupt)
        with pairing.ObsPairingStore(_root=self.root) as desktop:
            with self.assertRaises(pairing.PairingStoreError):
                desktop.import_package(transfer)
            self.assertIsNone(desktop.load())
            self.assertTrue(transfer.exists())

    def test_unsafe_existing_directory_is_not_repaired(self):
        other_root = self.root / "wrong-acl"
        other_root.mkdir()
        (other_root / "Utterleaf").mkdir()
        with self.assertRaises(pairing.PairingStoreError):
            pairing.ObsPairingStore(_root=other_root)
        other = C.c_void_p()
        result = self.dll.ul_pairing_store_open_test_root(str(other_root), C.byref(other))
        if other.value:
            self.dll.ul_pairing_store_destroy(other)
        self.assertNotEqual(result, 0)
        self.assertFalse((other_root / "Utterleaf" / "desktop").exists())
        self.assertFalse((other_root / "Utterleaf" / "obs-plugin").exists())

    def test_real_junction_root_is_refused_without_following_target(self):
        target = self.root / "junction-target"
        junction = self.root / "junction-root"
        _make_junction(self.root, target, junction)
        try:
            with self.assertRaises(pairing.PairingStoreError):
                pairing.ObsPairingStore(_root=junction)
            native_store = C.c_void_p()
            result = self.dll.ul_pairing_store_open_test_root(
                str(junction), C.byref(native_store))
            if native_store.value:
                self.dll.ul_pairing_store_destroy(native_store)
            self.assertNotEqual(result, 0)
            self.assertFalse((target / "Utterleaf").exists())
        finally:
            _remove_junction(self.root, junction)


if __name__ == "__main__":
    if sys.platform != "win32" or len(sys.argv) != 3:
        raise SystemExit("Pass the pairing-store DLL and authorization DLL on Windows")
    PairingInteropTests.pairing_dll = Path(sys.argv.pop(1)).resolve(strict=True)
    PairingInteropTests.authorization_dll = Path(sys.argv.pop(1)).resolve(strict=True)
    unittest.main(verbosity=2)
