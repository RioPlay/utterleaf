"""Internal Windows OBS pairing storage; no UI, transport or capture entry point.

DPAPI protects a capability for the Windows user, not for an executable. This
does not resist compromised same-user code, administrators or copied packages.
Owned mutable buffers are cleared; Python/OpenSSL/Windows erasure is not assured.
Importing the module performs no native calls or filesystem operations.
"""
from __future__ import annotations

from contextlib import ExitStack, contextmanager
import ctypes as C
from dataclasses import dataclass
import hmac
import ntpath
import os
from pathlib import Path
import re
import secrets
import struct
import sys
import threading
from typing import Callable

ROLE_NATIVE = 1
ROLE_TRANSFER = 2
ROLE_DESKTOP = 3
MAX_PACKAGE_BYTES = 4108
_OUTER = struct.Struct("<4sBBHI")
_DOMAIN = b"Utterleaf OBS pairing package integrity v1\0"
_FILE_ALL_ACCESS = 0x001F01FF
_READ_CONTROL = 0x00020000
_DELETE = 0x00010000
_INVALID_HANDLE = C.c_void_p(-1).value
_STORE_LOCK = threading.RLock()


class PairingStoreError(RuntimeError):
    """Safe static messages; no imported data, keys or native path diagnostics."""


class PairingStoreCancelled(PairingStoreError):
    """Cancelled before commit; the prior pairing and transfer file remain."""


class PairingStoreCommitError(PairingStoreError):
    """A write committed but its final state could not be verified. Reload it."""


@dataclass(frozen=True)
class ImportResult:
    package_removed: bool
    replaced: bool


def _wipe(value: bytearray) -> None:
    value[:] = b"\0" * len(value)


def _role(role: int) -> None:
    if type(role) is not int or role not in (ROLE_NATIVE, ROLE_TRANSFER, ROLE_DESKTOP):
        raise PairingStoreError("Invalid pairing package role")


def encode_pairing_package(key: bytes | bytearray, role: int, *, _native=None) -> bytes:
    """Protect a role-specific record; the caller retains ownership of its key."""
    _role(role)
    if type(key) not in (bytes, bytearray) or len(key) != 32 or not any(key):
        raise PairingStoreError("Invalid pairing capability")
    plaintext = bytearray(b"ULKI" + bytes((1, role, 0, 0)))
    plaintext.extend(key)
    owned_key = bytearray(key)
    try:
        plaintext.extend(hmac.digest(owned_key, _DOMAIN + plaintext, "sha256"))
        protected = (_native or _Native()).protect(plaintext)
        if type(protected) is not bytes or not 1 <= len(protected) <= 4096:
            raise PairingStoreError("Could not protect pairing capability")
        return _OUTER.pack(b"ULPK", 1, role, 0, len(protected)) + protected
    finally:
        _wipe(owned_key)
        _wipe(plaintext)


def decode_pairing_package(payload: bytes, role: int, *, _native=None) -> bytearray:
    """Return an owned mutable key only after strict outer/inner validation."""
    _role(role)
    if type(payload) is not bytes or not 13 <= len(payload) <= MAX_PACKAGE_BYTES:
        raise PairingStoreError("Invalid pairing package")
    magic, version, actual_role, reserved, length = _OUTER.unpack_from(payload)
    if (magic != b"ULPK" or version != 1 or actual_role != role or reserved != 0
            or not 1 <= length <= 4096 or len(payload) != 12 + length):
        raise PairingStoreError("Invalid pairing package")
    plaintext = (_native or _Native()).unprotect(payload[12:])
    key = bytearray()
    accepted = False
    try:
        if (type(plaintext) is not bytearray or len(plaintext) != 72
                or plaintext[:8] != b"ULKI" + bytes((1, role, 0, 0))):
            raise PairingStoreError("Invalid protected pairing record")
        key.extend(plaintext[8:40])
        if not any(key):
            raise PairingStoreError("Invalid protected pairing record")
        expected = hmac.digest(key, _DOMAIN + plaintext[:40], "sha256")
        if not hmac.compare_digest(expected, plaintext[40:]):
            raise PairingStoreError("Invalid protected pairing record")
        accepted = True
        return key
    finally:
        if type(plaintext) is bytearray:
            _wipe(plaintext)
        if not accepted:
            _wipe(key)


def _cancel(cancelled: Callable[[], bool] | None) -> None:
    if cancelled is not None and cancelled():
        raise PairingStoreCancelled("Pairing import cancelled")


def _path(value: str | os.PathLike) -> str:
    """Deliberately limited absolute DOS paths; never resolve a remote name."""
    try:
        value = os.fspath(value)
        if not isinstance(value, str):
            raise ValueError
        value = value.replace("/", "\\")
        if (not re.match(r"^[A-Za-z]:\\", value) or "\0" in value
                or len(value.encode("utf-16-le")) > 64000):
            raise ValueError
        components = value[3:].split("\\") if len(value) > 3 else []
        for part in components:
            if (not part or part in (".", "..") or part[-1] in (".", " ")
                    or any(c in part for c in ':*?"<>|')
                    or any(ord(c) < 32 for c in part)
                    or re.fullmatch(r"(?i:CON|PRN|AUX|NUL|COM[1-9¹²³]|LPT[1-9¹²³])",
                                    part.split(".", 1)[0])):
                raise ValueError
        return value[0].upper() + value[1:]
    except (TypeError, ValueError, UnicodeError):
        raise PairingStoreError("Choose an absolute local Windows path") from None


_DWORD = C.c_uint32
_BOOL = C.c_int32
_PTR = C.c_void_p


class _Blob(C.Structure):
    _fields_ = [("size", _DWORD), ("data", _PTR)]


class _SecurityAttributes(C.Structure):
    _fields_ = [("size", _DWORD), ("descriptor", _PTR), ("inherit", _BOOL)]


class _TokenUser(C.Structure):
    _fields_ = [("sid", _PTR), ("attributes", _DWORD)]


class _AttributeTag(C.Structure):
    _fields_ = [("attributes", _DWORD), ("tag", _DWORD)]


class _AclSize(C.Structure):
    _fields_ = [("count", _DWORD), ("used", _DWORD), ("free", _DWORD)]


class _AllowedAce(C.Structure):
    _fields_ = [("kind", C.c_ubyte), ("flags", C.c_ubyte),
                ("size", C.c_uint16), ("mask", _DWORD)]


class _Native:
    """Dedicated Win32 boundary; all file handles are scoped and noninheritable."""

    def __init__(self):
        if sys.platform != "win32":
            raise PairingStoreError("OBS pairing storage requires Windows")
        try:
            self.k = C.WinDLL("kernel32", use_last_error=True, winmode=0x800)
            self.a = C.WinDLL("advapi32", use_last_error=True, winmode=0x800)
            self.c = C.WinDLL("crypt32", use_last_error=True, winmode=0x800)
            self.s = C.WinDLL("shell32", use_last_error=True, winmode=0x800)
            self.o = C.WinDLL("ole32", use_last_error=True, winmode=0x800)
            self._bind()
            self.sid = self._user_sid()
            self.sid_buffer = C.create_string_buffer(self.sid)
            self.descriptor = self._descriptor()
            self.security = _SecurityAttributes(C.sizeof(_SecurityAttributes),
                                               C.addressof(self.descriptor), 0)
        except (OSError, AttributeError):
            raise PairingStoreError("Windows pairing storage is unavailable") from None

    def _bind(self):
        def bind(dll, name, args, result):
            function = getattr(dll, name)
            function.argtypes, function.restype = args, result
        p = _PTR
        d = _DWORD
        b = _BOOL
        w = C.c_wchar_p
        pd = C.POINTER(d)
        pp = C.POINTER(p)
        bind(self.k, "GetCurrentProcess", [], p)
        bind(self.k, "CloseHandle", [p], b)
        bind(self.k, "LocalFree", [p], p)
        bind(self.k, "CreateFileW", [w, d, d, p, d, d, p], p)
        bind(self.k, "CreateDirectoryW", [w, p], b)
        bind(self.k, "GetFileType", [p], d)
        bind(self.k, "GetDriveTypeW", [w], d)
        bind(self.k, "GetFinalPathNameByHandleW", [p, w, d, d], d)
        bind(self.k, "GetFileInformationByHandleEx", [p, C.c_int, p, d], b)
        bind(self.k, "GetVolumeInformationByHandleW", [p, w, d, pd, pd, pd, w, d], b)
        bind(self.k, "GetFileSizeEx", [p, C.POINTER(C.c_int64)], b)
        bind(self.k, "GetHandleInformation", [p, pd], b)
        bind(self.k, "ReadFile", [p, p, d, pd, p], b)
        bind(self.k, "WriteFile", [p, p, d, pd, p], b)
        bind(self.k, "FlushFileBuffers", [p], b)
        bind(self.k, "MoveFileExW", [w, w, d], b)
        bind(self.k, "SetFileInformationByHandle", [p, C.c_int, p, d], b)
        bind(self.a, "OpenProcessToken", [p, d, pp], b)
        bind(self.a, "GetTokenInformation", [p, C.c_int, p, d, pd], b)
        bind(self.a, "IsValidSid", [p], b)
        bind(self.a, "EqualSid", [p, p], b)
        bind(self.a, "GetLengthSid", [p], d)
        bind(self.a, "ConvertSidToStringSidW", [p, pp], b)
        bind(self.a, "ConvertStringSecurityDescriptorToSecurityDescriptorW", [w, d, pp, pd], b)
        bind(self.a, "GetSecurityInfo", [p, C.c_int, d, pp, pp, pp, pp, pp], d)
        bind(self.a, "GetSecurityDescriptorControl", [p, C.POINTER(C.c_uint16), pd], b)
        bind(self.a, "GetAclInformation", [p, p, d, C.c_int], b)
        bind(self.a, "GetAce", [p, d, pp], b)
        blob = C.POINTER(_Blob)
        bind(self.c, "CryptProtectData", [blob, p, blob, p, p, d, blob], b)
        bind(self.c, "CryptUnprotectData", [blob, p, blob, p, p, d, blob], b)
        bind(self.s, "SHGetKnownFolderPath", [p, d, p, pp], C.c_int32)
        bind(self.o, "CoTaskMemFree", [p], None)

    def _user_sid(self) -> bytes:
        token = _PTR()
        if not self.a.OpenProcessToken(self.k.GetCurrentProcess(), 8, C.byref(token)):
            raise PairingStoreError("Could not identify the Windows user")
        try:
            size = _DWORD()
            if (self.a.GetTokenInformation(token, 1, None, 0, C.byref(size))
                    or C.get_last_error() != 122 or not 16 <= size.value <= 65536):
                raise PairingStoreError("Could not identify the Windows user")
            buffer = C.create_string_buffer(size.value)
            valid = _DWORD()
            if (not self.a.GetTokenInformation(token, 1, buffer, size, C.byref(valid))
                    or not C.sizeof(_TokenUser) <= valid.value <= size.value):
                raise PairingStoreError("Could not identify the Windows user")
            sid = C.cast(buffer, C.POINTER(_TokenUser)).contents.sid or 0
            start, end = C.addressof(buffer), C.addressof(buffer) + valid.value
            if sid < start or sid > end - 8:
                raise PairingStoreError("Could not identify the Windows user")
            header = C.string_at(sid, 8)
            length = 8 + 4 * header[1]
            if (header[0] != 1 or header[1] > 15 or length > end - sid
                    or not self.a.IsValidSid(sid) or self.a.GetLengthSid(sid) != length):
                raise PairingStoreError("Could not identify the Windows user")
            return C.string_at(sid, length)
        finally:
            self.k.CloseHandle(token)

    def _descriptor(self):
        sid_text, descriptor = _PTR(), _PTR()
        size = _DWORD()
        try:
            if not self.a.ConvertSidToStringSidW(self.sid_buffer, C.byref(sid_text)):
                raise PairingStoreError("Could not protect pairing file permissions")
            sid = C.wstring_at(sid_text)
            sddl = f"O:{sid}D:P(A;;FA;;;{sid})"
            if (not self.a.ConvertStringSecurityDescriptorToSecurityDescriptorW(
                    sddl, 1, C.byref(descriptor), C.byref(size))
                    or not 1 <= size.value <= 4096 or not descriptor.value):
                raise PairingStoreError("Could not protect pairing file permissions")
            return C.create_string_buffer(C.string_at(descriptor, size.value), size.value)
        finally:
            if descriptor.value:
                self.k.LocalFree(descriptor)
            if sid_text.value:
                self.k.LocalFree(sid_text)

    def known_folder(self) -> str:
        # FOLDERID_LocalAppData, GUID's first three fields are little endian.
        guid = C.create_string_buffer(bytes.fromhex("8527b3f1ba6fcf4f9d557b8e7f157091"), 16)
        result = _PTR()
        try:
            if self.s.SHGetKnownFolderPath(guid, 0, None, C.byref(result)) < 0 or not result.value:
                raise PairingStoreError("Could not locate local pairing storage")
            return _path(C.wstring_at(result))
        finally:
            if result.value:
                self.o.CoTaskMemFree(result)

    def _dpapi(self, data: bytearray, *, protect: bool) -> bytearray:
        buffer = (C.c_ubyte * len(data)).from_buffer(data)
        source = _Blob(len(data), C.addressof(buffer))
        output = _Blob()
        try:
            function = self.c.CryptProtectData if protect else self.c.CryptUnprotectData
            if not function(C.byref(source), None, None, None, None, 1, C.byref(output)):
                raise PairingStoreError("Windows could not unlock or protect the pairing")
            limit = 4096 if protect else 72
            if not output.data or not 1 <= output.size <= limit:
                raise PairingStoreError("Invalid Windows pairing protection result")
            result = bytearray(output.size)
            destination = (C.c_ubyte * len(result)).from_buffer(result)
            C.memmove(destination, output.data, output.size)
            return result
        finally:
            if output.data:
                C.memset(output.data, 0, output.size)
                self.k.LocalFree(output.data)

    def protect(self, plaintext: bytearray) -> bytes:
        result = self._dpapi(plaintext, protect=True)
        try:
            return bytes(result)
        finally:
            _wipe(result)

    def unprotect(self, ciphertext: bytes) -> bytearray:
        owned = bytearray(ciphertext)
        try:
            return self._dpapi(owned, protect=False)
        finally:
            _wipe(owned)

    @staticmethod
    def _wide(path: str) -> str:
        return "\\\\?\\" + path

    def _validate(self, handle: int, path: str, *, directory: bool, private: bool) -> None:
        flags = _DWORD()
        info = _AttributeTag()
        if (self.k.GetFileType(handle) != 1
                or not self.k.GetHandleInformation(handle, C.byref(flags)) or flags.value & 1
                or not self.k.GetFileInformationByHandleEx(handle, 9, C.byref(info), C.sizeof(info))
                or info.attributes & 0x400 or bool(info.attributes & 0x10) != directory):
            raise PairingStoreError("Pairing storage is not a regular local file or directory")
        final = C.create_unicode_buffer(32768)
        count = self.k.GetFinalPathNameByHandleW(handle, final, len(final), 0)
        if not 1 <= count < len(final) or not final.value.startswith("\\\\?\\"):
            raise PairingStoreError("Could not verify the pairing storage path")
        actual = _path(final.value[4:])
        if ntpath.normcase(actual) != ntpath.normcase(path):
            raise PairingStoreError("The pairing storage path was redirected")
        volume_flags = _DWORD()
        if (self.k.GetDriveTypeW(actual[:3]) not in (2, 3, 6)
                or not self.k.GetVolumeInformationByHandleW(
                    handle, None, 0, None, None, C.byref(volume_flags), None, 0)
                or not volume_flags.value & 8):
            raise PairingStoreError("Pairing storage requires a local volume with file permissions")
        if private:
            self._validate_security(handle)

    def _validate_security(self, handle: int) -> None:
        owner, acl, descriptor = _PTR(), _PTR(), _PTR()
        try:
            if (self.a.GetSecurityInfo(handle, 1, 5, C.byref(owner), None, C.byref(acl),
                                       None, C.byref(descriptor)) != 0
                    or not owner.value or not acl.value or not descriptor.value
                    or not self.a.EqualSid(owner, self.sid_buffer)):
                raise PairingStoreError("Pairing storage permissions are not private")
            control, revision, size = C.c_uint16(), _DWORD(), _AclSize()
            if (not self.a.GetSecurityDescriptorControl(descriptor, C.byref(control), C.byref(revision))
                    or not control.value & 0x1000
                    or not self.a.GetAclInformation(acl, C.byref(size), C.sizeof(size), 2)
                    or size.count != 1):
                raise PairingStoreError("Pairing storage permissions are not private")
            ace = _PTR()
            if not self.a.GetAce(acl, 0, C.byref(ace)) or not ace.value:
                raise PairingStoreError("Pairing storage permissions are not private")
            item = C.cast(ace, C.POINTER(_AllowedAce)).contents
            if (item.kind != 0 or item.flags != 0 or item.mask != _FILE_ALL_ACCESS
                    or item.size != 8 + len(self.sid)
                    or not self.a.EqualSid(ace.value + 8, self.sid_buffer)):
                raise PairingStoreError("Pairing storage permissions are not private")
        finally:
            if descriptor.value:
                self.k.LocalFree(descriptor)

    @contextmanager
    def opened(self, path: str, *, directory=False, private=True, create=False,
               write=False, delete=False, share=0, missing=False):
        path = _path(path)
        # Reject drive mappings before opening; held-handle inspection repeats it.
        if self.k.GetDriveTypeW(path[:3]) not in (2, 3, 6):
            raise PairingStoreError("Pairing storage must be on a local Windows volume")
        if directory and create:
            if (not self.k.CreateDirectoryW(self._wide(path), C.byref(self.security))
                    and C.get_last_error() != 183):
                raise PairingStoreError("Could not create private pairing storage")
        access = _READ_CONTROL | (0x80 if directory else 0x80000000)
        if write:
            access |= 0x40000000
        if delete:
            access |= _DELETE
        attributes = 0x00200000 | (0x02000000 if directory else 0)  # open reparse point
        if write:
            attributes |= 0x80000000  # write through
        handle = self.k.CreateFileW(self._wide(path), access, share,
                                    C.byref(self.security), 1 if create and not directory else 3,
                                    attributes, None)
        if handle in (None, _INVALID_HANDLE):
            error = C.get_last_error()
            if missing and error == 2:
                yield None
                return
            if error in (80, 183):
                raise PairingStoreError("A pairing file already exists at that location")
            raise PairingStoreError("Could not open the pairing file or directory")
        try:
            self._validate(handle, path, directory=directory, private=private)
            yield handle
        finally:
            self.k.CloseHandle(handle)

    @contextmanager
    def parents(self, path: str):
        """Hold every existing ancestor without delete sharing; never repair ACLs."""
        path = _path(path)
        parts = path[3:].split("\\") if len(path) > 3 else []
        with ExitStack() as held:
            current = path[:3]
            held.enter_context(self.opened(current, directory=True, private=False, share=3))
            for part in parts:
                current = ntpath.join(current, part)
                held.enter_context(self.opened(current, directory=True, private=False, share=3))
            yield

    def read(self, handle: int) -> bytes:
        size = C.c_int64()
        if not self.k.GetFileSizeEx(handle, C.byref(size)) or not 13 <= size.value <= MAX_PACKAGE_BYTES:
            raise PairingStoreError("Invalid pairing file size")
        buffer = C.create_string_buffer(size.value)
        offset = 0
        while offset < size.value:
            received = _DWORD()
            remaining = size.value - offset
            if (not self.k.ReadFile(handle, C.byref(buffer, offset), remaining, C.byref(received), None)
                    or not 1 <= received.value <= remaining):
                raise PairingStoreError("Could not read the pairing file")
            offset += received.value
        return buffer.raw

    def write(self, handle: int, payload: bytes) -> None:
        if type(payload) is not bytes or not 13 <= len(payload) <= MAX_PACKAGE_BYTES:
            raise PairingStoreError("Invalid pairing file size")
        buffer = C.create_string_buffer(payload, len(payload))
        offset = 0
        while offset < len(payload):
            written = _DWORD()
            remaining = len(payload) - offset
            if (not self.k.WriteFile(handle, C.byref(buffer, offset), remaining, C.byref(written), None)
                    or not 1 <= written.value <= remaining):
                raise PairingStoreError("Could not save the pairing file")
            offset += written.value
        if not self.k.FlushFileBuffers(handle):
            raise PairingStoreError("Could not flush the pairing file")

    def move(self, temporary: str, destination: str, *, replace: bool) -> None:
        if not self.k.MoveFileExW(self._wide(temporary), self._wide(destination), 8 | int(replace)):
            raise PairingStoreError("Could not commit the pairing file")

    def delete(self, handle: int) -> None:
        disposition = C.c_ubyte(1)
        if not self.k.SetFileInformationByHandle(handle, 4, C.byref(disposition), 1):
            raise PairingStoreError("Could not remove the pairing file")


class ObsPairingStore:
    """One desktop store owner. Explicitly close it to release directory handles.

    `_root` substitutes an existing disposable LocalAppData root for tests only;
    production callers leave it unset. Operations serialize in this process.
    The integration owner must serialize cross-process access and capture state.
    Construction creates only private directories, never a capability or capture.
    """

    def __init__(self, *, _root: Path | None = None, _native=None):
        self._held = ExitStack()
        self._closed = True
        self._native = _native or _Native()
        self._root = _path(_root if _root is not None else self._native.known_folder())
        self.directory = ntpath.join(self._root, "Utterleaf", "desktop")
        self.path = ntpath.join(self.directory, "obs-pairing-v1.dat")
        try:
            self._held.enter_context(self._native.parents(self._root))
            for folder in (ntpath.join(self._root, "Utterleaf"), self.directory):
                self._held.enter_context(self._native.opened(
                    folder, directory=True, create=True, private=True, share=3))
            self._closed = False
        except BaseException:
            self._held.close()
            raise

    def __enter__(self):
        self._ensure_open()
        return self

    def __exit__(self, *_args):
        self.close()

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass

    def _ensure_open(self):
        if self._closed:
            raise PairingStoreError("The pairing store is closed")

    def close(self) -> None:
        with _STORE_LOCK:
            if not self._closed:
                self._closed = True
                self._held.close()

    def load(self) -> bytearray | None:
        with _STORE_LOCK:
            self._ensure_open()
            with self._native.opened(self.path, missing=True) as handle:
                if handle is None:
                    return None
                return decode_pairing_package(self._native.read(handle), ROLE_DESKTOP, _native=self._native)

    def _save(self, key: bytearray, *, replace: bool, cancelled=None) -> None:
        payload = encode_pairing_package(key, ROLE_DESKTOP, _native=self._native)
        temporary = ntpath.join(self.directory, ".pairing-" + secrets.token_hex(16) + ".tmp")
        committed = False
        created = False
        try:
            _cancel(cancelled)
            with self._native.opened(temporary, create=True, write=True, delete=True) as handle:
                created = True
                self._native.write(handle, payload)
            _cancel(cancelled)
            self._native.move(temporary, self.path, replace=replace)
            committed = True
            try:
                saved = self.load()
                try:
                    if saved is None or not hmac.compare_digest(saved, key):
                        raise PairingStoreError("Saved pairing did not match the imported capability")
                finally:
                    if saved is not None:
                        _wipe(saved)
            except Exception:
                raise PairingStoreCommitError(
                    "The pairing was written but could not be verified; reload its status") from None
        finally:
            if created and not committed:
                try:
                    with self._native.opened(temporary, delete=True, missing=True) as handle:
                        if handle is not None:
                            self._native.delete(handle)
                except PairingStoreError:
                    pass  # An encrypted temporary file may remain; never promote it.

    def import_package(self, path: str | Path, *, replace: bool = False,
                       cancelled: Callable[[], bool] | None = None) -> ImportResult:
        """Import explicitly. Cancellation is observed until the atomic commit.

        Deletion of the transfer file is best-effort after commit verification.
        Retaining/copying a package keeps it usable until OBS revokes the key.
        """
        if type(replace) is not bool or (cancelled is not None and not callable(cancelled)):
            raise PairingStoreError("Invalid pairing import options")
        path = _path(path)
        with _STORE_LOCK:
            self._ensure_open()
            _cancel(cancelled)
            old = self.load()
            existed = old is not None
            if old is not None:
                _wipe(old)
            if existed and not replace:
                raise PairingStoreError("Pairing already exists; choose replacement explicitly")
            if not existed and replace:
                raise PairingStoreError("There is no pairing to replace")
            with ExitStack() as held:
                held.enter_context(self._native.parents(ntpath.dirname(path)))
                # Try DELETE while opening; retry read-only without closing a valid
                # accepted handle. Both attempts hold the file against modification.
                try:
                    handle = held.enter_context(self._native.opened(path, delete=True))
                    can_remove = True
                except PairingStoreError:
                    handle = held.enter_context(self._native.opened(path))
                    can_remove = False
                key = decode_pairing_package(self._native.read(handle), ROLE_TRANSFER, _native=self._native)
                try:
                    _cancel(cancelled)
                    self._save(key, replace=replace, cancelled=cancelled)
                    removed = False
                    if can_remove:
                        try:
                            self._native.delete(handle)
                            removed = True
                        except PairingStoreError:
                            pass
                    return ImportResult(removed, existed)
                finally:
                    _wipe(key)

    def forget(self) -> bool:
        """Delete only this desktop copy; it cannot revoke packages held elsewhere."""
        with _STORE_LOCK:
            self._ensure_open()
            with self._native.opened(self.path, delete=True, missing=True) as handle:
                if handle is None:
                    return False
                self._native.delete(handle)
            with self._native.opened(self.path, missing=True) as remaining:
                if remaining is not None:
                    raise PairingStoreError("The pairing file remains; forgetting was not durable")
            return True
