from pathlib import Path

import pytest

from utterleaf import config
from utterleaf import backup_store
from utterleaf.backup import BackupError, export_backup, inspect_backup
from utterleaf.backup_store import (BackupSaveError, apply_import, prepare_import,
                                   read_backup, read_current, write_backup)


@pytest.fixture
def files(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "config_path", lambda: tmp_path / "config.toml")
    monkeypatch.setattr(config, "dictionary_path", lambda: tmp_path / "dictionary.txt")
    config.save(config.Config(allow_network=False, restore_clipboard=True, beep=True))
    config.dictionary_path().write_text("# keep\nold = Original\n", encoding="utf-8")
    return config.config_path(), config.dictionary_path()


def plan():
    return inspect_backup(export_backup(config.Config(beep=False), "new = New\n"))


def test_review_cancel_and_apply_preserve_privacy(files):
    before = [path.read_bytes() for path in files]
    review = prepare_import(plan(), preference_keys=["beep"], vocabulary_mode="merge")
    assert [path.read_bytes() for path in files] == before
    assert review.preference_changes == (("beep", True, False),)
    result = apply_import(review)
    assert config.load().beep is False
    assert config.load().allow_network is False
    assert config.load().restore_clipboard is True
    assert result.vocabulary_text.encode("utf-8") == files[1].read_bytes() == before[1] + b"new = New\n"


def test_partial_save_rolls_back_exact_original_files(files, monkeypatch):
    before = [path.read_bytes() for path in files]
    review = prepare_import(plan(), preference_keys=["beep"], vocabulary_mode="replace")
    original_write = backup_store._atomic_write
    def fail_config(path, text):
        if path == files[0]:
            raise OSError("synthetic disk failure")
        return original_write(path, text)
    monkeypatch.setattr(backup_store, "_atomic_write", fail_config)
    with pytest.raises(BackupSaveError, match="restored"):
        apply_import(review)
    assert [path.read_bytes() for path in files] == before
    assert sorted(path.name for path in files[0].parent.iterdir()) == ["config.toml", "dictionary.txt"]


def test_failed_import_removes_new_vocabulary_file(files, monkeypatch):
    files[1].unlink()
    review = prepare_import(plan(), preference_keys=["beep"], vocabulary_mode="merge")
    original_write = backup_store._atomic_write
    def fail_config(path, text):
        if path == files[0]:
            raise OSError("synthetic failure")
        return original_write(path, text)
    monkeypatch.setattr(backup_store, "_atomic_write", fail_config)
    with pytest.raises(BackupSaveError):
        apply_import(review)
    assert not files[1].exists()
    assert config.load().beep is True


def test_stale_review_rejected_without_reverting_new_privacy_choice(files):
    review = prepare_import(plan(), preference_keys=["beep"], vocabulary_mode="replace")
    config.save(config.Config(beep=True, allow_network=False, restore_clipboard=False))
    before = [path.read_bytes() for path in files]
    with pytest.raises(BackupError, match="changed since preview"):
        apply_import(review)
    assert [path.read_bytes() for path in files] == before


def test_rollback_does_not_clobber_a_later_external_edit(files, monkeypatch):
    review = prepare_import(plan(), preference_keys=["beep"], vocabulary_mode="replace")
    original_write = backup_store._atomic_write
    def external_writer(path, text):
        if path == files[0]:
            files[1].write_text("external = Change\n", encoding="utf-8")
            raise OSError("synthetic failure")
        return original_write(path, text)
    monkeypatch.setattr(backup_store, "_atomic_write", external_writer)
    with pytest.raises(BackupSaveError, match="rollback could not finish"):
        apply_import(review)
    assert files[1].read_text() == "external = Change\n"
    assert config.load().beep is True


def test_noop_import_preserves_bytes_and_does_not_create_missing_files(files):
    before = files[0].read_bytes()
    files[1].unlink()
    apply_import(prepare_import(plan()))
    assert files[0].read_bytes() == before
    assert not files[1].exists()


def test_review_cannot_change_destination(files, monkeypatch, tmp_path):
    review = prepare_import(plan(), preference_keys=["beep"])
    other = tmp_path / "other.toml"
    monkeypatch.setattr(config, "config_path", lambda: other)
    with pytest.raises(BackupError, match="location changed"):
        apply_import(review)
    assert not other.exists()


def test_exclusive_export_refuses_existing_file_and_does_not_apply_import(tmp_path):
    path = tmp_path / "backup.json"
    payload = export_backup(config.Config(), "name = Námé")
    write_backup(path, payload)
    assert read_backup(path) == inspect_backup(payload)
    before = path.read_bytes()
    with pytest.raises(FileExistsError):
        write_backup(path, export_backup(config.Config(beep=False), ""))
    assert path.read_bytes() == before


def test_export_failure_cleans_partial_new_file(tmp_path, monkeypatch):
    path = tmp_path / "backup.json"
    def fail(_fd):
        raise OSError("synthetic sync failure")
    monkeypatch.setattr("utterleaf.backup_store.os.fsync", fail)
    with pytest.raises(OSError):
        write_backup(path, export_backup(config.Config(), ""))
    assert not path.exists()


def test_bounded_file_reads_reject_oversize_and_directories(tmp_path):
    path = tmp_path / "large.json"
    path.write_bytes(b" " * (512 * 1024 + 1))
    for invalid in (path, tmp_path):
        with pytest.raises(BackupError):
            read_backup(invalid)


def test_tampered_candidate_is_rejected(files):
    review = prepare_import(plan(), preference_keys=["beep"])
    review.values.config.allow_network = True
    with pytest.raises(BackupError):
        apply_import(review)
    assert config.load().allow_network is False


def test_failed_atomic_replacement_leaves_original_and_no_temporary_file(files, monkeypatch):
    before = [path.read_bytes() for path in files]
    review = prepare_import(plan(), preference_keys=["beep"], vocabulary_mode="replace")
    def fail(*_args):
        raise OSError("synthetic replace failure")
    monkeypatch.setattr(Path, "replace", fail)
    with pytest.raises(BackupSaveError):
        apply_import(review)
    assert [path.read_bytes() for path in files] == before
    assert len(list(files[0].parent.iterdir())) == 2


def test_invalid_current_privacy_type_rejected_without_rewriting(files):
    files[0].write_text('allow_network = "false"\n', encoding="utf-8")
    before = files[0].read_bytes()
    with pytest.raises(BackupError):
        prepare_import(plan(), preference_keys=["beep"])
    assert files[0].read_bytes() == before


def test_current_export_inputs_use_bounded_reader(files):
    files[1].write_bytes(b"x" * (256 * 1024 + 1))
    with pytest.raises(BackupError, match="byte size"):
        read_current()
