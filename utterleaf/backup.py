"""Selective, local backup validation and review. These APIs never read or write files."""

from __future__ import annotations

from dataclasses import dataclass, replace
import json
from typing import Iterable, Literal
import unicodedata

from utterleaf.config import Config

MAX_BACKUP_BYTES = 512 * 1024
MAX_VOCABULARY_BYTES = 256 * 1024
MAX_VOCABULARY_ENTRIES = 2000
MAX_TERM_CHARACTERS = 256
_BOOL_KEYS = frozenset({"text_cleanup", "remove_fillers", "fix_corrections", "beep", "tray", "indicator",
                        "speech_end_enabled", "speech_end_insert"})
_CHOICE_KEYS = frozenset({"denoise", "output_format"})
_NUMBER_KEYS = frozenset({"speech_end_pause_seconds"})
PORTABLE_PREFERENCES = tuple(sorted(_BOOL_KEYS | _CHOICE_KEYS | _NUMBER_KEYS))
_FORMAT = "utterleaf-preferences"


class BackupError(ValueError):
    """Invalid backup; messages deliberately omit imported content."""


@dataclass(frozen=True)
class BackupPlan:
    preferences: tuple[tuple[str, bool | str | float], ...]
    vocabulary: tuple[tuple[str, str], ...] | None


@dataclass(frozen=True)
class BackupValues:
    config: Config
    vocabulary_text: str
    vocabulary_conflicts: tuple[str, ...]


def _bounded_text(value: str, limit: int) -> None:
    if not isinstance(value, str) or len(value) > limit:
        raise BackupError("Text exceeds the supported size or has an invalid type")
    try:
        size = len(value.encode("utf-8"))
    except UnicodeError:
        raise BackupError("Text is not valid Unicode") from None
    if size > limit:
        raise BackupError("Text exceeds the supported byte size")


def _preferences(values: object) -> tuple[tuple[str, bool | str | float], ...]:
    if not isinstance(values, dict) or set(values) - set(PORTABLE_PREFERENCES):
        raise BackupError("Unknown or nonportable preference")
    for key, value in values.items():
        if key in _BOOL_KEYS:
            if type(value) is not bool:
                raise BackupError("Preference requires a Boolean")
        elif key in _NUMBER_KEYS:
            if type(value) not in {int, float} or not 0.5 <= float(value) <= 3.0:
                raise BackupError("Invalid speech-end pause preference")
        elif type(value) is not str or value not in (
                {"auto", "on", "off"} if key == "denoise" else {"prose", "markdown"}):
            raise BackupError("Invalid portable choice preference")
    return tuple(sorted(values.items()))


def _term(value: object, *, spoken: bool) -> str:
    if not isinstance(value, str) or not value or len(value) > MAX_TERM_CHARACTERS:
        raise BackupError("Invalid vocabulary term length or type")
    if value != value.strip() or any(unicodedata.category(char).startswith("C") or
                                     char in "\u2028\u2029" for char in value):
        raise BackupError("Vocabulary terms must be trimmed and contain no control characters")
    if spoken and ("=" in value or value.startswith("#")):
        raise BackupError("Spoken term cannot be represented in the vocabulary format")
    return value


def _vocabulary(values: object) -> tuple[tuple[str, str], ...]:
    if not isinstance(values, list) or len(values) > MAX_VOCABULARY_ENTRIES:
        raise BackupError("Invalid vocabulary list or too many entries")
    pairs = []
    seen = set()
    for item in values:
        if not isinstance(item, dict) or set(item) != {"spoken", "written"}:
            raise BackupError("Invalid vocabulary entry schema")
        spoken, written = _term(item["spoken"], spoken=True), _term(item["written"], spoken=False)
        identity = spoken.casefold()
        if identity in seen:
            raise BackupError("Duplicate spoken vocabulary term")
        seen.add(identity)
        pairs.append((spoken, written))
    _bounded_text(_dictionary(pairs), MAX_VOCABULARY_BYTES)
    return tuple(pairs)


def _dictionary(pairs: Iterable[tuple[str, str]]) -> str:
    return "".join(f"{spoken} = {written}\n" for spoken, written in pairs)


def _parse_dictionary(text: str) -> tuple[tuple[str, str], ...]:
    _bounded_text(text, MAX_VOCABULARY_BYTES)
    entries = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("=", 1)
        if len(parts) != 2:
            raise BackupError("Vocabulary line must use spoken = written")
        entries.append(dict(spoken=parts[0].strip(), written=parts[1].strip()))
    return _vocabulary(entries)


def _selection(keys: Iterable[str]) -> tuple[str, ...]:
    if isinstance(keys, str):
        raise BackupError("Select preference keys as a collection")
    selected = []
    for key in keys:
        if not isinstance(key, str) or key not in PORTABLE_PREFERENCES or key in selected:
            raise BackupError("Invalid or duplicate preference selection")
        selected.append(key)
        if len(selected) > len(PORTABLE_PREFERENCES):
            raise BackupError("Too many preference selections")
    return tuple(selected)


def export_backup(cfg: Config, vocabulary_text: str, *,
                  preference_keys: Iterable[str] | None = None,
                  include_vocabulary: bool = True) -> str:
    """Return reviewable JSON, with no path metadata or automatic file creation.

    Only the seven PORTABLE_PREFERENCES are eligible. Omitted vocabulary is null,
    distinct from an explicitly exported empty vocabulary. Comments are excluded.
    """
    if type(include_vocabulary) is not bool:
        raise BackupError("Vocabulary inclusion requires a Boolean")
    keys = _selection(PORTABLE_PREFERENCES if preference_keys is None else preference_keys)
    preferences = dict(_preferences({key: getattr(cfg, key) for key in keys}))
    pairs = _parse_dictionary(vocabulary_text) if include_vocabulary else None
    result = json.dumps({"format": _FORMAT, "version": 1, "preferences": preferences,
                         "vocabulary": None if pairs is None else [dict(spoken=s, written=w) for s, w in pairs]},
                        ensure_ascii=False, indent=2) + "\n"
    _bounded_text(result, MAX_BACKUP_BYTES)
    return result


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise BackupError("Duplicate JSON key")
        result[key] = value
    return result


def _invalid_constant(_value):
    raise BackupError("Non-finite JSON values are not supported")


def inspect_backup(payload: str | bytes) -> BackupPlan:
    """Validate bounded JSON and return immutable review data; never opens a path."""
    if isinstance(payload, bytes):
        if len(payload) > MAX_BACKUP_BYTES:
            raise BackupError("Backup exceeds the supported byte size")
        try:
            payload = payload.decode("utf-8")
        except UnicodeError:
            raise BackupError("Backup must be UTF-8") from None
    _bounded_text(payload, MAX_BACKUP_BYTES)
    try:
        value = json.loads(payload, object_pairs_hook=_unique_object, parse_constant=_invalid_constant)
    except (ValueError, RecursionError):
        raise BackupError("Malformed backup JSON") from None
    if not isinstance(value, dict) or set(value) != {"format", "version", "preferences", "vocabulary"}:
        raise BackupError("Unexpected backup schema")
    if value["format"] != _FORMAT or type(value["version"]) is not int or value["version"] != 1:
        raise BackupError("Unsupported backup format or version")
    return BackupPlan(_preferences(value["preferences"]),
                      None if value["vocabulary"] is None else _vocabulary(value["vocabulary"]))


def merge_backup(plan: BackupPlan, cfg: Config, current_vocabulary: str, *,
                 preference_keys: Iterable[str] = (),
                 vocabulary_mode: Literal["keep", "merge", "replace"] = "keep") -> BackupValues:
    """Build candidate values after explicit choices; do not mutate cfg or save.

    Merge preserves existing text/comments and existing definitions on conflicts.
    Replace must be explicitly requested. By default nothing is selected to change.
    Callers must present the candidate, obtain confirmation, and persist atomically.
    """
    if not isinstance(plan, BackupPlan):
        raise BackupError("Expected a reviewed backup plan")
    # Plans are public data classes; revalidate before constructing candidates.
    try:
        raw_preferences = dict(plan.preferences)
        if len(raw_preferences) != len(plan.preferences):
            raise BackupError("Duplicate preference in plan")
        preferences = dict(_preferences(raw_preferences))
        incoming = None if plan.vocabulary is None else _vocabulary(
            [dict(spoken=s, written=w) for s, w in plan.vocabulary])
    except (TypeError, ValueError):
        raise BackupError("Invalid backup plan") from None
    keys = _selection(preference_keys)
    if set(keys) - set(preferences):
        raise BackupError("Selected preference is absent from backup")
    if vocabulary_mode not in {"keep", "merge", "replace"}:
        raise BackupError("Choose keep, merge, or replace vocabulary")
    if vocabulary_mode != "keep" and incoming is None:
        raise BackupError("Backup contains no vocabulary selection")
    text = current_vocabulary
    conflicts = []
    if vocabulary_mode == "replace":
        text = _dictionary(incoming)
    elif vocabulary_mode == "merge":
        existing = _parse_dictionary(current_vocabulary)
        known = {spoken.casefold(): written for spoken, written in existing}
        additions = []
        for spoken, written in incoming:
            if spoken.casefold() in known:
                if known[spoken.casefold()] != written:
                    conflicts.append(spoken)
            else:
                additions.append((spoken, written))
        if len(existing) + len(additions) > MAX_VOCABULARY_ENTRIES:
            raise BackupError("Merged vocabulary has too many entries")
        if additions:
            text += ("\n" if text and not text.endswith("\n") else "") + _dictionary(additions)
        _bounded_text(text, MAX_VOCABULARY_BYTES)
    return BackupValues(replace(cfg, **{key: preferences[key] for key in keys}), text, tuple(conflicts))
