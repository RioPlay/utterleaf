"""Private OBS pairing package codec and disposable Windows store fixtures."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

from utterleaf import obs_pairing_store as pairing


KEY = b"k" * 32
OTHER_KEY = b"z" * 32


class FakeNative:
    def protect(self, plaintext: bytearray) -> bytes:
        assert type(plaintext) is bytearray
        return b"P" + bytes(plaintext)

    def unprotect(self, ciphertext: bytes) -> bytearray:
        if not ciphertext.startswith(b"P"):
            return bytearray(b"bad")
        return bytearray(ciphertext[1:])


class FailingProtect(FakeNative):
    def protect(self, plaintext):
        raise pairing.PairingStoreError("protect")


class WrongProtectLength(FakeNative):
    def protect(self, plaintext):
        return b""


class FailingUnprotect(FakeNative):
    def unprotect(self, ciphertext):
        raise pairing.PairingStoreError("unprotect")


class WrongUnprotectLength(FakeNative):
    def unprotect(self, ciphertext):
        return bytearray(b"wrong")


def package(key=KEY, role=pairing.ROLE_TRANSFER):
    return pairing.encode_pairing_package(key, role, _native=FakeNative())


def test_codec_round_trip_and_input_aliases_are_supported():
    key = bytearray(KEY)
    encoded = pairing.encode_pairing_package(key, pairing.ROLE_TRANSFER, _native=FakeNative())
    decoded = pairing.decode_pairing_package(encoded, pairing.ROLE_TRANSFER, _native=FakeNative())
    assert decoded == KEY
    assert isinstance(decoded, bytearray)
    assert key == KEY


@pytest.mark.parametrize("role", [0, 4, True, "1"])
def test_codec_rejects_invalid_roles(role):
    with pytest.raises(pairing.PairingStoreError, match="role"):
        pairing.encode_pairing_package(KEY, role, _native=FakeNative())


@pytest.mark.parametrize("key", [b"", b"k" * 31, b"k" * 33, b"\0" * 32, None, "key"])
def test_codec_rejects_invalid_keys(key):
    with pytest.raises(pairing.PairingStoreError, match="capability"):
        pairing.encode_pairing_package(key, pairing.ROLE_TRANSFER, _native=FakeNative())


@pytest.mark.parametrize("payload", [b"", b"ULPK", package()[:-1], package() + b"x"])
def test_codec_rejects_bad_outer_lengths(payload):
    with pytest.raises(pairing.PairingStoreError):
        pairing.decode_pairing_package(payload, pairing.ROLE_TRANSFER, _native=FakeNative())


@pytest.mark.parametrize("offset", [0, 4, 5, 6, 7, 8, 12, -1])
def test_codec_rejects_corruption_and_never_returns_key(offset):
    changed = bytearray(package())
    changed[offset] ^= 1
    with pytest.raises(pairing.PairingStoreError):
        pairing.decode_pairing_package(bytes(changed), pairing.ROLE_TRANSFER, _native=FakeNative())


def test_codec_rejects_wrong_role_and_bad_plaintext():
    with pytest.raises(pairing.PairingStoreError):
        pairing.decode_pairing_package(package(role=pairing.ROLE_DESKTOP), pairing.ROLE_TRANSFER,
                                        _native=FakeNative())

    class BadNative(FakeNative):
        def unprotect(self, ciphertext):
            return bytearray(b"bad")

    with pytest.raises(pairing.PairingStoreError):
        pairing.decode_pairing_package(package(), pairing.ROLE_TRANSFER, _native=BadNative())


@pytest.mark.parametrize("backend", [FailingProtect(), WrongProtectLength()])
def test_codec_rejects_protection_failures(backend):
    with pytest.raises(pairing.PairingStoreError):
        pairing.encode_pairing_package(KEY, pairing.ROLE_TRANSFER, _native=backend)


@pytest.mark.parametrize("backend", [FailingUnprotect(), WrongUnprotectLength()])
def test_codec_rejects_unprotection_failures(backend):
    with pytest.raises(pairing.PairingStoreError):
        pairing.decode_pairing_package(package(), pairing.ROLE_TRANSFER, _native=backend)


@pytest.mark.parametrize("value", ["relative.dat", "C:\\..\\x", "C:\\tmp\\..\\x",
                                    "C:\\CON", "C:\\name.", "C:\\name ",
                                    "\\\\server\\share\\x", "\\\\?\\C:\\x",
                                    "C:\\stream:bad"])
def test_rejects_unsafe_windows_paths(value):
    with pytest.raises(pairing.PairingStoreError):
        pairing._path(value)


windows_only = pytest.mark.skipif(sys.platform != "win32", reason="Windows DPAPI/ACL store")


def _native_transfer(tmp_path, key=KEY):
    native = pairing._Native()
    path = tmp_path / "transfer.dat"
    payload = pairing.encode_pairing_package(key, pairing.ROLE_TRANSFER, _native=native)
    with native.parents(str(path.parent)):
        with native.opened(str(path), create=True, write=True, delete=True) as handle:
            native.write(handle, payload)
    return native, path


@windows_only
def test_store_import_reload_missing_and_forget(tmp_path):
    native, transfer = _native_transfer(tmp_path)
    store = pairing.ObsPairingStore(_root=tmp_path, _native=native)
    assert store.load() is None
    result = store.import_package(transfer)
    assert result.replaced is False and result.package_removed is True
    assert store.load() == KEY
    store.close()

    reopened = pairing.ObsPairingStore(_root=tmp_path, _native=native)
    assert reopened.load() == KEY
    assert reopened.forget() is True
    assert reopened.load() is None
    assert reopened.forget() is False
    reopened.close()


@windows_only
def test_store_rejects_corrupt_existing_state(tmp_path):
    native, transfer = _native_transfer(tmp_path)
    store = pairing.ObsPairingStore(_root=tmp_path, _native=native)
    store.import_package(transfer)
    store.close()
    path = store.path
    with native.opened(path, write=True, share=3) as handle:
        native.write(handle, b"ULPK\x01\x03\0\0\x01\0\0\0x")
    reopened = pairing.ObsPairingStore(_root=tmp_path, _native=native)
    with pytest.raises(pairing.PairingStoreError):
        reopened.load()
    reopened.close()


@windows_only
def test_store_requires_explicit_replace_and_replaces_atomically(tmp_path):
    native, transfer = _native_transfer(tmp_path)
    store = pairing.ObsPairingStore(_root=tmp_path, _native=native)
    store.import_package(transfer)
    second = tmp_path / "second.dat"
    payload = pairing.encode_pairing_package(OTHER_KEY, pairing.ROLE_TRANSFER, _native=native)
    with native.parents(str(second.parent)):
        with native.opened(str(second), create=True, write=True, delete=True) as handle:
            native.write(handle, payload)
    with pytest.raises(pairing.PairingStoreError, match="already exists"):
        store.import_package(second)
    result = store.import_package(second, replace=True)
    assert result.replaced is True and store.load() == OTHER_KEY
    store.close()


@windows_only
def test_store_cancellation_before_commit_preserves_old_state_and_package(tmp_path):
    native, transfer = _native_transfer(tmp_path)
    store = pairing.ObsPairingStore(_root=tmp_path, _native=native)
    store.import_package(transfer)
    second = tmp_path / "second.dat"
    payload = pairing.encode_pairing_package(OTHER_KEY, pairing.ROLE_TRANSFER, _native=native)
    with native.parents(str(second.parent)):
        with native.opened(str(second), create=True, write=True, delete=True) as handle:
            native.write(handle, payload)
    with pytest.raises(pairing.PairingStoreCancelled):
        store.import_package(second, replace=True, cancelled=lambda: True)
    assert store.load() == KEY and second.exists()
    store.close()


@windows_only
def test_store_cancellation_after_commit_is_success(tmp_path, monkeypatch):
    native, transfer = _native_transfer(tmp_path)
    store = pairing.ObsPairingStore(_root=tmp_path, _native=native)
    cancelled = [False]
    original_move = native.move

    def move(*args, **kwargs):
        original_move(*args, **kwargs)
        cancelled[0] = True

    monkeypatch.setattr(native, "move", move)
    result = store.import_package(transfer, cancelled=lambda: cancelled[0])
    assert result.package_removed is True and store.load() == KEY
    store.close()


@windows_only
def test_store_write_and_move_failures_preserve_previous_state(tmp_path, monkeypatch):
    native, transfer = _native_transfer(tmp_path)
    store = pairing.ObsPairingStore(_root=tmp_path, _native=native)
    store.import_package(transfer)
    second = tmp_path / "second.dat"
    payload = pairing.encode_pairing_package(OTHER_KEY, pairing.ROLE_TRANSFER, _native=native)
    with native.parents(str(second.parent)):
        with native.opened(str(second), create=True, write=True, delete=True) as handle:
            native.write(handle, payload)
    monkeypatch.setattr(native, "write", lambda *_args, **_kwargs: (_ for _ in ()).throw(
        pairing.PairingStoreError("write")))
    with pytest.raises(pairing.PairingStoreError):
        store.import_package(second, replace=True)
    assert store.load() == KEY and second.exists()
    store.close()


@windows_only
def test_store_move_failure_preserves_previous_state_and_package(tmp_path, monkeypatch):
    native, transfer = _native_transfer(tmp_path)
    store = pairing.ObsPairingStore(_root=tmp_path, _native=native)
    store.import_package(transfer)
    second = tmp_path / "second.dat"
    payload = pairing.encode_pairing_package(OTHER_KEY, pairing.ROLE_TRANSFER, _native=native)
    with native.parents(str(second.parent)):
        with native.opened(str(second), create=True, write=True, delete=True) as handle:
            native.write(handle, payload)
    monkeypatch.setattr(native, "move", lambda *_args, **_kwargs: (_ for _ in ()).throw(
        pairing.PairingStoreError("move")))
    with pytest.raises(pairing.PairingStoreError):
        store.import_package(second, replace=True)
    assert store.load() == KEY and second.exists()
    store.close()


@windows_only
def test_store_postcommit_verification_failure_retains_transfer(tmp_path, monkeypatch):
    native, transfer = _native_transfer(tmp_path)
    store = pairing.ObsPairingStore(_root=tmp_path, _native=native)
    store.import_package(transfer)
    second = tmp_path / "second.dat"
    payload = pairing.encode_pairing_package(OTHER_KEY, pairing.ROLE_TRANSFER, _native=native)
    with native.parents(str(second.parent)):
        with native.opened(str(second), create=True, write=True, delete=True) as handle:
            native.write(handle, payload)
    original_load = store.load
    monkeypatch.setattr(store, "load", lambda: bytearray(KEY))
    with pytest.raises(pairing.PairingStoreCommitError):
        store.import_package(second, replace=True)
    monkeypatch.setattr(store, "load", original_load)
    assert store.load() == OTHER_KEY and second.exists()
    store.close()


@windows_only
def test_store_rejects_preexisting_inherited_file_without_repair(tmp_path):
    native, _transfer = _native_transfer(tmp_path)
    store = pairing.ObsPairingStore(_root=tmp_path, _native=native)
    path = store.path
    Path(path).write_bytes(b"ordinary inherited file")
    with pytest.raises(pairing.PairingStoreError):
        store.load()
    assert Path(path).read_bytes() == b"ordinary inherited file"
    store.close()


@windows_only
def test_store_load_leaves_unrelated_sentinels_untouched(tmp_path):
    native, _transfer = _native_transfer(tmp_path)
    sentinels = {
        tmp_path / "backup.dat": b"backup",
        tmp_path / "config.json": b"config",
        tmp_path / "model.bin": b"model",
        tmp_path / "transcript.txt": b"transcript",
    }
    for path, value in sentinels.items():
        path.write_bytes(value)
    store = pairing.ObsPairingStore(_root=tmp_path, _native=native)
    assert store.load() is None
    store.close()
    assert {path: path.read_bytes() for path in sentinels} == sentinels


@windows_only
def test_store_transfer_delete_failure_reports_package_remaining(tmp_path, monkeypatch):
    native, transfer = _native_transfer(tmp_path)
    store = pairing.ObsPairingStore(_root=tmp_path, _native=native)
    monkeypatch.setattr(native, "delete", lambda *_args, **_kwargs: (_ for _ in ()).throw(
        pairing.PairingStoreError("delete")))
    result = store.import_package(transfer)
    assert result.package_removed is False and result.replaced is False
    assert store.load() == KEY and transfer.exists()
    store.close()
