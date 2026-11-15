"""Pure helpers for adding entries to the personal vocabulary draft."""

from __future__ import annotations

import unicodedata


def append_vocabulary_entry(existing: str, spoken: str, written: str) -> str:
    """Return ``existing`` with one valid dictionary entry appended.

    Existing text is retained byte-for-character at the Python string level,
    including comments and malformed lines. Only valid existing entries are
    considered when checking for duplicate spoken phrases.
    """
    if not isinstance(existing, str):
        raise TypeError("Existing vocabulary must be text.")
    spoken = _entry_value(spoken, "Spoken phrase")
    written = _entry_value(written, "Write as")
    if "=" in spoken:
        raise ValueError("Spoken phrase cannot contain =.")
    if spoken.lstrip().startswith("#"):
        raise ValueError("Spoken phrase cannot start with #.")

    candidate = spoken.strip().casefold()
    for raw in existing.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        prior, prior_written = line.split("=", 1)
        if prior.strip() and prior_written.strip() and prior.strip().casefold() == candidate:
            raise ValueError("That spoken phrase is already in your vocabulary.")

    separator = "" if not existing or existing.endswith(("\n", "\r")) else "\n"
    return f"{existing}{separator}{spoken} = {written}"


def _entry_value(value: str, label: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{label} must be text.")
    if not value or not value.strip():
        raise ValueError(f"{label} cannot be blank.")
    if "\x00" in value:
        raise ValueError(f"{label} cannot contain NUL.")
    if any(char in "\r\n\v\f\x1c\x1d\x1e\x85" or unicodedata.category(char) in {"Zl", "Zp"}
           for char in value):
        raise ValueError(f"{label} must be a single line.")
    return value
