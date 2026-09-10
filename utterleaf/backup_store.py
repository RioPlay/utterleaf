"""Explicit backup file I/O and checked, rollback-on-error settings import."""
from dataclasses import dataclass, field, fields
import os
from pathlib import Path
import stat
import tempfile

from utterleaf import config
from utterleaf.backup import (BackupError, BackupPlan, BackupValues, MAX_BACKUP_BYTES,
                             MAX_VOCABULARY_BYTES, inspect_backup, merge_backup)


class BackupSaveError(BackupError):
    pass


@dataclass(frozen=True)
class ImportReview:
    plan: BackupPlan
    preference_keys: tuple[str, ...]
    vocabulary_mode: str
    values: BackupValues
    preference_changes: tuple[tuple[str, object, object], ...]
    vocabulary_counts: tuple[int, int]
    paths: tuple[Path, Path] = field(repr=False)
    originals: tuple[bytes | None, bytes | None] = field(repr=False)


def _read(path: Path, limit: int) -> bytes | None:
    try:
        info = path.lstat()
    except FileNotFoundError:
        return None
    if not stat.S_ISREG(info.st_mode) or path.is_symlink():
        raise BackupError("Choose a regular file, not a link or device")
    if info.st_size > limit:
        raise BackupError("File exceeds the supported byte size")
    with path.open("rb") as stream:
        value = stream.read(limit + 1)
    if len(value) > limit:
        raise BackupError("File exceeds the supported byte size")
    return value


def read_backup(path: Path) -> BackupPlan:
    payload = _read(Path(path), MAX_BACKUP_BYTES)
    if payload is None:
        raise BackupError("Backup file was not found")
    return inspect_backup(payload)


def write_backup(path: Path, payload: str) -> None:
    """Create a new selected file exclusively; never overwrite an existing path."""
    inspect_backup(payload)
    path = Path(path)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    identity = os.fstat(descriptor)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload.encode("utf-8"))
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        try:
            if os.path.samestat(identity, path.lstat()):
                path.unlink()
        except FileNotFoundError:
            pass
        raise


def _current(originals):
    raw_config, raw_vocabulary = originals
    try:
        values = config._parse_toml((raw_config or b"").decode("utf-8"))
        known = {item.name for item in fields(config.Config)}
        cfg = config.Config(**{key: value for key, value in values.items() if key in known})
        for key in ("allow_network", "restore_clipboard", "live_preview"):
            if type(getattr(cfg, key)) is not bool:
                raise ValueError("Invalid current privacy setting")
        vocabulary = (raw_vocabulary or b"").decode("utf-8")
    except (ValueError, TypeError, UnicodeError):
        raise BackupError("Current settings or vocabulary cannot be read safely") from None
    return cfg, vocabulary


def _atomic_write(path: Path, payload: bytes) -> None:
    # Binary mode preserves original CRLF bytes during rollback on Windows.
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="wb", dir=path.parent, suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def read_current() -> tuple[config.Config, str]:
    """Read the current export inputs within the same bounds used for import."""
    return _current((_read(config.config_path(), MAX_BACKUP_BYTES),
                     _read(config.dictionary_path(), MAX_VOCABULARY_BYTES)))


def prepare_import(plan: BackupPlan, *, preference_keys=(), vocabulary_mode="keep") -> ImportReview:
    paths = (config.config_path(), config.dictionary_path())
    originals = (_read(paths[0], MAX_BACKUP_BYTES), _read(paths[1], MAX_VOCABULARY_BYTES))
    cfg, vocabulary = _current(originals)
    keys = tuple(preference_keys)
    values = merge_backup(plan, cfg, vocabulary, preference_keys=keys, vocabulary_mode=vocabulary_mode)
    changes = tuple((key, getattr(cfg, key), getattr(values.config, key)) for key in keys)
    def entry_count(text):
        return sum(1 for line in text.splitlines() if line.strip() and not line.lstrip().startswith("#")
                   and "=" in line and all(part.strip() for part in line.split("=", 1)))
    counts = (entry_count(vocabulary), entry_count(values.vocabulary_text))
    return ImportReview(plan, keys, vocabulary_mode, values, changes, counts, paths, originals)


def apply_import(review: ImportReview) -> BackupValues:
    """Apply only an unchanged review. Roll back completed writes on later failure.

    This is not a crash-atomic filesystem transaction. The Settings dialog serializes
    its own saves; concurrent external edits are detected before each replacement.
    No reload signal is sent until both writes have succeeded.
    """
    if review.paths != (config.config_path(), config.dictionary_path()):
        raise BackupError("Settings location changed; review the import again")
    fresh = prepare_import(review.plan, preference_keys=review.preference_keys,
                           vocabulary_mode=review.vocabulary_mode)
    if fresh.originals != review.originals or fresh.values != review.values:
        raise BackupError("Settings changed since preview; review the import again")
    # No-op selections must not rewrite or create either file.
    base_cfg, base_vocabulary = _current(review.originals)
    wanted = (config._dump_toml(fresh.values.config).encode("utf-8")
              if fresh.values.config != base_cfg else review.originals[0],
              fresh.values.vocabulary_text.encode("utf-8")
              if fresh.values.vocabulary_text != base_vocabulary else review.originals[1])
    completed = []
    try:
        for index in (1, 0):
            if wanted[index] == review.originals[index]:
                continue
            if _read(review.paths[index], MAX_BACKUP_BYTES) != review.originals[index]:
                raise BackupError("Settings changed during import")
            _atomic_write(review.paths[index], wanted[index])
            completed.append(index)
    except Exception:
        failed_rollback = False
        for index in reversed(completed):
            try:
                if _read(review.paths[index], MAX_BACKUP_BYTES) != wanted[index]:
                    raise BackupError("Another writer changed the imported file")
                original = review.originals[index]
                if original is None:
                    review.paths[index].unlink()
                else:
                    _atomic_write(review.paths[index], original)
            except Exception:
                failed_rollback = True
        message = ("Import failed and rollback could not finish. Inspect settings and vocabulary before retrying."
                   if failed_rollback else "Import failed. Previous settings and vocabulary were restored.")
        raise BackupSaveError(message) from None
    return fresh.values
