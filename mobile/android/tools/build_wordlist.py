"""Build the English completion word list for the suggestion strip.

Derives a frequency-ordered word list exclusively from public-domain Project
Gutenberg texts, so the shipped resource carries no third-party license
obligations. Re-run to reproduce; the committed resource is reviewed data.

Usage: python build_wordlist.py [--min-count N] [--max-words N]
Writes mobile/android/app/src/main/res/raw/wordlist_en.txt
(one lowercase word per line, frequency-ordered, no comments).
"""
from __future__ import annotations

import collections
import re
import sys
import urllib.request
from pathlib import Path

# Public-domain texts (Project Gutenberg), chosen for plain prose coverage.
CORPUS = [
    (1342, "Pride and Prejudice"), (84, "Frankenstein"),
    (1661, "Adventures of Sherlock Holmes"), (2701, "Moby Dick"),
    (98, "A Tale of Two Cities"), (76, "Huckleberry Finn"),
    (1400, "Great Expectations"), (174, "The Picture of Dorian Gray"),
    (43, "Dr Jekyll and Mr Hyde"), (219, "Heart of Darkness"),
    (1184, "The Count of Monte Cristo"), (16, "Peter Pan"),
    (2542, "A Doll's House"), (2591, "Grimms' Fairy Tales"),
    (863, "Meditations"), (2814, "Dubliners"),
]
TOKEN = re.compile(r"[a-zA-Z]{2,}")
ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "app" / "src" / "main" / "res" / "raw" / "wordlist_en.txt"


def fetch(book_id: int) -> str:
    url = f"https://www.gutenberg.org/cache/epub/{book_id}/pg{book_id}.txt"
    with urllib.request.urlopen(url, timeout=120) as response:
        return response.read().decode("utf-8")


def words(text: str):
    return (token.group(0).lower() for token in TOKEN.finditer(text))


def build(min_count: int, max_words: int) -> list[str]:
    counts: collections.Counter[str] = collections.Counter()
    for book_id, title in CORPUS:
        print(f"fetching {book_id} {title}", file=sys.stderr)
        counts.update(words(fetch(book_id)))
    ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    selected = [word for word, count in ordered if count >= min_count][:max_words]
    return selected


def main() -> int:
    min_count = int(sys.argv[sys.argv.index("--min-count") + 1]) if "--min-count" in sys.argv else 8
    max_words = int(sys.argv[sys.argv.index("--max-words") + 1]) if "--max-words" in sys.argv else 20000
    if "--fetch" in sys.argv or not TARGET.exists():
        selected = build(min_count, max_words)
        TARGET.parent.mkdir(parents=True, exist_ok=True)
        TARGET.write_text("\n".join(selected) + "\n", encoding="ascii")
        print(f"wrote {len(selected)} words to {TARGET}", file=sys.stderr)
    validate()
    return 0


def validate() -> int:
    lines = TARGET.read_text(encoding="ascii").splitlines()
    assert 5000 <= len(lines) <= 20000, f"unexpected size {len(lines)}"
    assert all(re.fullmatch(r"[a-z]{2,}", line) for line in lines), "non word entry"
    assert len(set(lines)) == len(lines), "duplicate entries"
    print(f"validated {len(lines)} words", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
