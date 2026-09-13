import ctypes
import io
from pathlib import Path, PureWindowsPath
import threading
import subprocess
import sys
from types import SimpleNamespace

import numpy as np
import pytest

from utterleaf import capture_store as store
from utterleaf import local_filesystem as local
from utterleaf.transcript import TranscriptionCancelled


def test_long_take_uses_bounded_windows_and_removes_temporary_file(tmp_path, monkeypatch):
    monkeypatch.setattr(store.tempfile, "tempdir", str(tmp_path))
    capture = store.CaptureStore(16000)
    try:
        # Beyond all old 120/250/600-second limits, without microphone/model use.
        for i in range(601):
            assert capture.append(np.full(16000, i / 1000, dtype=np.float32))
            # Keep the synthetic producer from overwhelming actual local disk.
            if i % 40 == 0:
                with capture._condition:
                    assert capture._condition.wait_for(
                        lambda: capture.pending_bytes < store.MAX_PENDING_BYTES // 2, timeout=2)
        capture.finish().wait_ready()
        assert capture.error is None
        assert len(capture) == 601 * 16000
        lengths = []
        offset = 0
        for chunk in capture.chunks():
            lengths.append(len(chunk))
            assert np.isfinite(chunk).all()
            assert chunk[0] == pytest.approx(offset / 16000 // 1 / 1000)
            offset += len(chunk)
        assert max(lengths) == 30 * 16000
        assert sum(lengths) == 601 * 16000
        assert lengths[-1] == 16000
    finally:
        capture.close()
    assert capture._file.closed
    assert list(tmp_path.iterdir()) == []


def test_cancel_closes_pending_store_and_refuses_reentry(tmp_path, monkeypatch):
    monkeypatch.setattr(store.tempfile, "tempdir", str(tmp_path))
    capture = store.CaptureStore(48000)
    assert capture.append(np.zeros(48000, np.float32))
    capture.close()
    assert capture._ready.wait(2)
    assert not capture.append(np.zeros(1, np.float32))
    with pytest.raises(TranscriptionCancelled):
        list(capture.chunks())
    assert capture._file.closed
    assert list(tmp_path.iterdir()) == []


def test_slow_disk_queue_is_bounded_and_incomplete_is_visible(monkeypatch):
    release, writing = threading.Event(), threading.Event()
    class SlowFile(io.BytesIO):
        def write(self, data):
            writing.set()
            assert release.wait(2)
            return super().write(data)
    file = SlowFile()
    monkeypatch.setattr(store.tempfile, "TemporaryFile", lambda **kw: file)
    monkeypatch.setattr(store, "MAX_PENDING_BYTES", 32)
    capture = store.CaptureStore(16000)
    try:
        assert capture.append(np.zeros(8, np.float32))
        assert writing.wait(2)
        assert capture.append(np.zeros(8, np.float32))
        assert not capture.append(np.zeros(1, np.float32))
        assert capture.pending_bytes == 32
        assert "could not keep up" in capture.error
        release.set()
        capture.finish().wait_ready()
        assert sum(len(chunk) for chunk in capture.chunks()) == 16
    finally:
        release.set()
        capture.close()


def test_disk_full_retains_exact_written_prefix_and_never_claims_success(monkeypatch):
    class FullFile(io.BytesIO):
        def write(self, data):
            if self.tell() >= 10:
                raise OSError("disk full")
            return super().write(data[:10])
    monkeypatch.setattr(store.tempfile, "TemporaryFile", lambda **kw: FullFile())
    capture = store.CaptureStore(16000)
    try:
        assert capture.append(np.arange(8, dtype=np.float32))
        capture.finish().wait_ready()
        assert "storage failed" in capture.error
        assert len(capture) == 2
        np.testing.assert_array_equal(next(capture.chunks()), [0, 1])
        assert not capture.append(np.zeros(1, np.float32))
    finally:
        capture.close()


def test_cancellation_between_windows_does_not_read_full_audio():
    capture = store.CaptureStore(16000)
    cancelled = threading.Event()
    try:
        for _ in range(2):
            for _ in range(30):
                assert capture.append(np.zeros(16000, np.float32))
        capture.finish()
        chunks = capture.chunks(cancelled.is_set)
        assert len(next(chunks)) == 480000
        cancelled.set()
        with pytest.raises(TranscriptionCancelled):
            next(chunks)
    finally:
        capture.close()


@pytest.mark.parametrize("audio", [np.zeros(8, np.float64), np.zeros((2, 2), np.float32),
                                  np.zeros(store.MAX_BLOCK_BYTES // 4 + 1, np.float32)])
def test_invalid_blocks_are_atomically_refused(audio):
    capture = store.CaptureStore(16000)
    try:
        with pytest.raises(ValueError):
            capture.append(audio)
        assert len(capture) == 0
    finally:
        capture.close()


def test_low_space_refuses_capture_before_creating_audio_file(monkeypatch):
    monkeypatch.setattr(store.shutil, "disk_usage", lambda path: SimpleNamespace(free=0))
    monkeypatch.setattr(store.tempfile, "TemporaryFile", lambda **kw: pytest.fail("Created low-space audio"))
    with pytest.raises(store.CaptureStorageError, match="disk space"):
        store.CaptureStore(16000)


def test_disk_inspection_failure_is_reported_as_storage(monkeypatch):
    monkeypatch.setattr(store.shutil, "disk_usage",
                        lambda path: (_ for _ in ()).throw(OSError("volume unavailable")))
    monkeypatch.setattr(store.tempfile, "TemporaryFile",
                        lambda **kw: pytest.fail("Created audio after inspection failure"))
    with pytest.raises(store.CaptureStorageError, match="could not be inspected"):
        store.CaptureStore(16000)


def test_temporary_file_creation_failure_is_reported_as_storage(monkeypatch):
    monkeypatch.setattr(store.tempfile, "TemporaryFile",
                        lambda **kw: (_ for _ in ()).throw(PermissionError("denied")))
    with pytest.raises(store.CaptureStorageError, match="could not be created"):
        store.CaptureStore(16000)


def test_writer_start_failure_closes_handle_and_reports_storage(monkeypatch):
    handle = io.BytesIO()
    monkeypatch.setattr(store.tempfile, "TemporaryFile", lambda **kw: handle)
    monkeypatch.setattr(store.threading.Thread, "start",
                        lambda self: (_ for _ in ()).throw(RuntimeError("thread limit")))
    with pytest.raises(store.CaptureStorageError, match="could not start"):
        store.CaptureStore(16000)
    assert handle.closed


def test_unverified_filesystem_refuses_capture_before_creating_audio_file(monkeypatch):
    monkeypatch.setattr(store, "require_local_filesystem",
                        lambda path: (_ for _ in ()).throw(local.LocalFilesystemError()))
    monkeypatch.setattr(store.tempfile, "TemporaryFile", lambda **kw: pytest.fail("Created remote audio"))
    with pytest.raises(store.CaptureStorageError, match="verified local"):
        store.CaptureStore(16000)


def test_current_temporary_directory_is_verified_local():
    try:
        result = local.require_local_filesystem(store.tempfile.gettempdir())
    except local.LocalFilesystemError as exc:
        if local.sys.platform.startswith("linux"):
            pytest.skip(f"Actual temporary filesystem is outside the strict local policy: {exc}")
        raise
    assert result.is_dir()


def test_windows_native_check_detects_mapped_remote_drive_portably():
    roots = []
    def drive_type(root):
        roots.append(root)
        return local.DRIVE_REMOTE
    assert local._windows_drive_type(PureWindowsPath("Z:/mapped-temp"), drive_type) == local.DRIVE_REMOTE
    assert roots == ["Z:\\"]


@pytest.mark.parametrize("drive_type", [local.DRIVE_FIXED, local.DRIVE_REMOVABLE,
                                         local.DRIVE_RAMDISK])
def test_windows_local_drive_types_are_supported(monkeypatch, tmp_path, drive_type):
    monkeypatch.setattr(local.sys, "platform", "win32")
    monkeypatch.setattr(local, "_windows_drive_type", lambda path: drive_type)
    assert local.require_local_filesystem(tmp_path) == tmp_path.resolve()


def test_linux_mounted_remote_filesystem_is_rejected(monkeypatch, tmp_path):
    mountinfo = (
        "24 1 8:1 / / rw - ext4 /dev/sda1 rw\n"
        "25 24 0:42 / /mnt/team rw - nfs fileserver:/team rw\n"
    )
    mount_type = local._linux_mount_type
    monkeypatch.setattr(local.sys, "platform", "linux")
    monkeypatch.setattr(local, "_linux_mount_type",
                        lambda path: mount_type("/mnt/team/private", mountinfo))
    with pytest.raises(local.LocalFilesystemError, match="verified local"):
        local.require_local_filesystem(tmp_path)


@pytest.mark.parametrize("filesystem", ["ext4", "tmpfs", "xfs"])
def test_linux_supported_local_filesystems_are_accepted(monkeypatch, tmp_path, filesystem):
    monkeypatch.setattr(local.sys, "platform", "linux")
    monkeypatch.setattr(local, "_linux_mount_type", lambda path: filesystem)
    assert local.require_local_filesystem(tmp_path) == tmp_path.resolve()


def test_linux_unknown_or_stacked_filesystem_is_rejected(monkeypatch, tmp_path):
    monkeypatch.setattr(local.sys, "platform", "linux")
    monkeypatch.setattr(local, "_linux_mount_type", lambda path: "fuse.portal")
    with pytest.raises(local.LocalFilesystemError, match="verified local"):
        local.require_local_filesystem(tmp_path)


def test_linux_mount_lookup_uses_longest_mount_and_decodes_paths():
    mountinfo = (
        "24 1 8:1 / / rw - ext4 /dev/sda1 rw\n"
        "25 24 0:42 / /mnt/team\\040share rw - cifs //server/team rw\n"
    )
    assert local._linux_mount_type("/mnt/team share/private", mountinfo) == "cifs"


@pytest.mark.parametrize("mounts", [
    ("25 24 8:2 / /tmp rw - ext4 /dev/sdb rw\n"
     "26 24 0:42 / /tmp rw - nfs fileserver:/tmp rw\n"),
    ("26 24 0:42 / /tmp rw - nfs fileserver:/tmp rw\n"
     "25 24 8:2 / /tmp rw - ext4 /dev/sdb rw\n"),
])
def test_linux_same_path_overmount_is_refused_in_either_order(mounts):
    with pytest.raises(local.LocalFilesystemError, match="ambiguous"):
        local._linux_mount_type("/tmp/private", mounts)


def test_macos_mnt_local_flag_controls_acceptance(monkeypatch, tmp_path):
    monkeypatch.setattr(local.sys, "platform", "darwin")
    monkeypatch.setattr(local, "_darwin_mount_flags", lambda path: 0)
    with pytest.raises(local.LocalFilesystemError, match="verified local"):
        local.require_local_filesystem(tmp_path)
    monkeypatch.setattr(local, "_darwin_mount_flags", lambda path: local.MNT_LOCAL)
    assert local.require_local_filesystem(tmp_path) == tmp_path.resolve()


@pytest.mark.parametrize(("machine", "symbol"), [
    ("x86_64", "statfs$INODE64"),
    ("arm64", "statfs"),
    ("aarch64", "statfs"),
])
def test_macos_binds_architecture_appropriate_statfs_symbol_and_layout(machine, symbol):
    requested = []
    assert local._DarwinStatfs.f_flags.offset == 64
    assert ctypes.sizeof(local._DarwinStatfs) == 2168
    class Function:
        def __call__(self, encoded, pointer):
            assert encoded.endswith(b"private")
            info = ctypes.cast(pointer, ctypes.POINTER(local._DarwinStatfs)).contents
            info.f_flags = local.MNT_LOCAL
            return 0
    class Library:
        def __getattr__(self, name):
            requested.append(name)
            if name != symbol:
                raise AttributeError(name)
            return Function()
    assert local._darwin_mount_flags(Path("/private"), Library(), machine) == local.MNT_LOCAL
    assert requested == [symbol]


def test_macos_missing_or_unknown_native_abi_fails_closed():
    class MissingLibrary:
        def __getattr__(self, name):
            raise AttributeError(name)
    with pytest.raises(local.LocalFilesystemError, match="unavailable"):
        local._darwin_mount_flags(Path("/private"), MissingLibrary(), "x86_64")
    with pytest.raises(local.LocalFilesystemError, match="architecture"):
        local._darwin_mount_flags(Path("/private"), MissingLibrary(), "powerpc")


def test_space_running_out_stops_writing_and_reports_incomplete(monkeypatch):
    checks = []
    def space(path):
        checks.append(path)
        return SimpleNamespace(free=store.MIN_FREE_BYTES * 2 if len(checks) == 1 else 0)
    monkeypatch.setattr(store.shutil, "disk_usage", space)
    capture = store.CaptureStore(16000)
    try:
        capture.append(np.zeros(16000, np.float32))
        capture.finish().wait_ready()
        assert "storage failed" in capture.error
        assert len(capture) == 0
        assert list(capture.chunks()) == []
    finally:
        capture.close()


def test_process_termination_removes_owned_temporary_audio(tmp_path):
    script = """
import sys, tempfile, time
import numpy as np
from utterleaf.capture_store import CaptureStore
tempfile.tempdir = sys.argv[1]
capture = CaptureStore(16000)
capture.append(np.zeros(16000, np.float32))
capture.finish().wait_ready()
print('ready', flush=True)
time.sleep(30)
"""
    child = subprocess.Popen([sys.executable, "-c", script, str(tmp_path)],
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    try:
        with pytest.raises(subprocess.TimeoutExpired):
            child.communicate(timeout=3)
    finally:
        if child.poll() is None:
            child.kill()
        output, errors = child.communicate(timeout=3)
    assert b"ready" in output, errors
    assert child.poll() is not None
    assert list(tmp_path.iterdir()) == []
