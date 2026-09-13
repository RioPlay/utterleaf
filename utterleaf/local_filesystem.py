"""Fail-closed locality checks for paths that may hold private user data."""

from __future__ import annotations

import ctypes
from pathlib import Path
import platform
import posixpath
import sys


class LocalFilesystemError(OSError):
    """A path is remote, shared, or cannot be verified as local."""


DRIVE_REMOVABLE = 2
DRIVE_FIXED = 3
DRIVE_REMOTE = 4
DRIVE_RAMDISK = 6
MNT_LOCAL = 0x00001000

# Linux has no general MNT_LOCAL equivalent. Permit native local filesystem types
# and reject network, clustered, stacked, FUSE, shared-host and unknown types.
# This intentionally trades compatibility for the local-only guarantee.
LINUX_LOCAL_FILESYSTEMS = frozenset({
    "bcachefs", "btrfs", "exfat", "ext2", "ext3", "ext4",
    "f2fs", "hfsplus", "jfs", "msdos", "nilfs2", "ntfs", "ntfs3",
    "ramfs", "reiserfs", "tmpfs", "ufs", "vfat", "xfs", "zfs",
})


def require_local_filesystem(path: str | Path) -> Path:
    """Resolve an existing path and return it only when its volume is local.

    Unsupported platforms and inspection failures are refused. Callers handling
    private data should translate LocalFilesystemError into their own user-facing
    error before creating a file.
    """
    try:
        # Reject an obvious mapped/network mount before resolving it, because
        # resolution itself may contact that filesystem. Check again afterward
        # so a local-looking symlink or junction cannot bypass the decision.
        candidate = Path(path).absolute()
        if not _is_local_filesystem(candidate):
            raise LocalFilesystemError(
                "The selected path is not on a verified local filesystem.")
        resolved = candidate.resolve(strict=True)
        local = _is_local_filesystem(resolved)
    except LocalFilesystemError:
        raise
    except (OSError, ValueError) as exc:
        raise LocalFilesystemError("Could not verify a local filesystem.") from exc
    if not local:
        raise LocalFilesystemError("The selected path is not on a verified local filesystem.")
    return resolved


def _is_local_filesystem(path: Path) -> bool:
    if sys.platform == "win32":
        return _windows_drive_type(path) in {DRIVE_REMOVABLE, DRIVE_FIXED, DRIVE_RAMDISK}
    if sys.platform == "darwin":
        return bool(_darwin_mount_flags(path) & MNT_LOCAL)
    if sys.platform.startswith("linux"):
        return _linux_mount_type(path) in LINUX_LOCAL_FILESYSTEMS
    raise LocalFilesystemError("Local filesystem checks are unavailable on this platform.")


def _windows_drive_type(path: Path, function=None) -> int:
    # GetDriveTypeW recognizes drive-letter mappings as DRIVE_REMOTE. Resolved
    # UNC paths are also refused rather than relying on their spelling alone.
    value = str(path)
    if value.startswith(("\\\\", "//")):
        return DRIVE_REMOTE
    root = path.anchor
    if not root:
        return 0
    if not root.endswith(("\\", "/")):
        root += "\\"
    if function is None:
        function = ctypes.windll.kernel32.GetDriveTypeW
        function.argtypes = [ctypes.c_wchar_p]
        function.restype = ctypes.c_uint
    return int(function(root))


class _DarwinStatfs(ctypes.Structure):
    _fields_ = [
        ("f_bsize", ctypes.c_uint32),
        ("f_iosize", ctypes.c_int32),
        ("f_blocks", ctypes.c_uint64),
        ("f_bfree", ctypes.c_uint64),
        ("f_bavail", ctypes.c_uint64),
        ("f_files", ctypes.c_uint64),
        ("f_ffree", ctypes.c_uint64),
        ("f_fsid", ctypes.c_int32 * 2),
        ("f_owner", ctypes.c_uint32),
        ("f_type", ctypes.c_uint32),
        ("f_flags", ctypes.c_uint32),
        ("f_fssubtype", ctypes.c_uint32),
        ("f_fstypename", ctypes.c_char * 16),
        ("f_mntonname", ctypes.c_char * 1024),
        ("f_mntfromname", ctypes.c_char * 1024),
        ("f_flags_ext", ctypes.c_uint32),
        ("f_reserved", ctypes.c_uint32 * 7),
    ]


def _darwin_statfs_symbol(machine: str | None = None) -> str:
    machine = (machine or platform.machine()).lower()
    if machine in {"arm64", "aarch64"}:
        return "statfs"
    if machine in {"x86_64", "amd64"}:
        return "statfs$INODE64"
    raise LocalFilesystemError("The local-volume API is unavailable on this macOS architecture.")


def _darwin_mount_flags(path: Path, library=None, machine: str | None = None) -> int:
    info = _DarwinStatfs()
    library = library or ctypes.CDLL(None, use_errno=True)
    symbol = _darwin_statfs_symbol(machine)
    try:
        # Apple Silicon exposes only the 64-bit ABI as plain statfs. Intel's
        # public declaration redirects to statfs$INODE64; its plain statfs can
        # expose the incompatible legacy structure. Never fall back across ABIs.
        function = getattr(library, symbol)
    except AttributeError as exc:
        raise LocalFilesystemError("The local-volume API is unavailable on this macOS system.") from exc
    function.argtypes = [ctypes.c_char_p, ctypes.POINTER(_DarwinStatfs)]
    function.restype = ctypes.c_int
    if function(bytes(path), ctypes.byref(info)) != 0:
        errno = ctypes.get_errno()
        raise OSError(errno, "statfs could not inspect the temporary filesystem")
    return int(info.f_flags)


def _unescape_mountinfo(value: str) -> str:
    for escaped, literal in (("\\040", " "), ("\\011", "\t"),
                             ("\\012", "\n"), ("\\134", "\\")):
        value = value.replace(escaped, literal)
    return value


def _linux_mount_type(path: str | Path, mountinfo: str | None = None) -> str:
    """Return the longest owning mount's filesystem type from mountinfo."""
    if mountinfo is None:
        mountinfo = Path("/proc/self/mountinfo").read_text(encoding="utf-8")
    candidate = posixpath.normpath(str(path))
    owners = []
    for line in mountinfo.splitlines():
        fields = line.split()
        try:
            separator = fields.index("-")
            mountpoint = posixpath.normpath(_unescape_mountinfo(fields[4]))
            filesystem = fields[separator + 1]
        except (ValueError, IndexError):
            continue
        prefix = mountpoint.rstrip("/") + "/"
        if candidate == mountpoint or candidate.startswith(prefix) or mountpoint == "/":
            owners.append((mountpoint, filesystem))
    if not owners:
        raise LocalFilesystemError("Could not identify the path's mounted filesystem.")
    longest = max(len(mountpoint) for mountpoint, _ in owners)
    owners = [owner for owner in owners if len(owner[0]) == longest]
    if len(owners) != 1:
        # mountinfo does not promise that textual ordering identifies the visible
        # member of an overmount stack. Do not guess local when paths collide.
        raise LocalFilesystemError("The path has an ambiguous mounted filesystem.")
    return owners[0][1]
