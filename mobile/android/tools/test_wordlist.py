"""Validate the packaged completion word list (public-domain provenance)."""
from __future__ import annotations

import re
from pathlib import Path

WORDLIST = Path(__file__).resolve().parents[1] / "app" / "src" / "main" / "res" / "raw" / "wordlist_en.txt"


def load() -> list[str]:
    text = WORDLIST.read_text(encoding="ascii")
    lines = text.splitlines()
    assert 5000 <= len(lines) <= 20000, f"unexpected word count {len(lines)}"
    assert all(re.fullmatch(r"[a-z]{2,}", line) for line in lines), "non word entry"
    assert len(set(lines)) == len(lines), "duplicate entries"
    return lines


def test_wordlist_is_present_clean_and_bounded() -> None:
    words = load()
    assert "the" == words[0]
    assert len(words) >= 9000
