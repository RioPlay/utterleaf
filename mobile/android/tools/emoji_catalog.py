#!/usr/bin/env python3
"""Build Utterleaf's bounded offline emoji catalog from pinned Unicode data."""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
ANDROID_ROOT = Path(__file__).resolve().parents[1]
UNICODE_DIR = Path(__file__).resolve().parent / "unicode"
RESOURCE = ANDROID_ROOT / "app/src/main/res/raw/emoji_catalog.txt"
NOTICE = ANDROID_ROOT / "app/src/main/assets/unicode-license.txt"
FIELD_SEPARATOR = "\t"
KEYWORD_SEPARATOR = "|"
MAGIC = "# utterleaf-emoji-catalog-v1"
CLDR_COMMIT = "acd6d88ae493633240e19a87a721076a8a75c310"
SAFE_DOCTYPE = '<!DOCTYPE ldml SYSTEM "../../common/dtd/ldml.dtd">'
MAX_INPUT_BYTES = 2_000_000
MAX_ENTRIES = 4096
MAX_CATALOG_CHARS = 1_000_000
MAX_LINE_CHARS = 4096
MAX_KEYWORDS = 128
EXPECTED_ENTRY_COUNT = 3944

PINNED = {
    "emoji-test-17.0.txt": (669326, "1d8a944f88d7952f7ef7c5167fef3c67995bcae24543949710231b03a201acda"),
    "cldr-48-annotations-en.xml": (294945, "8511aadd046fdba2f0ffe590266ced8bbf48175ad139b2675d85d7141057b235"),
    "cldr-48-annotations-derived-en.xml": (548066, "d76bd041c8c9e7b00b716aff8b7d9dbf509877010e191d5efd068be2553e066e"),
    "LICENSE-UNICODE.txt": (1995, "e7a93b009565cfce55919a381437ac4db883e9da2126fa28b91d12732bc53d96"),
}

CATEGORY_IDS = {
    "Smileys & Emotion": "smileys-emotion",
    "People & Body": "people-body",
    "Animals & Nature": "animals-nature",
    "Food & Drink": "food-drink",
    "Travel & Places": "travel-places",
    "Activities": "activities",
    "Objects": "objects",
    "Symbols": "symbols",
    "Flags": "flags",
}
EXPECTED_CATEGORY_COUNTS = {
    "smileys-emotion": 171,
    "people-body": 2418,
    "animals-nature": 160,
    "food-drink": 131,
    "travel-places": 219,
    "activities": 85,
    "objects": 266,
    "symbols": 224,
    "flags": 270,
}


@dataclass(frozen=True)
class SourceEmoji:
    codepoints: tuple[int, ...]
    category: str
    subgroup: str
    upstream_name: str


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def verify_bytes(name: str, data: bytes) -> None:
    if len(data) > MAX_INPUT_BYTES:
        raise ValueError(f"{name}: exceeds {MAX_INPUT_BYTES} byte input bound")
    expected_size, expected_hash = PINNED[name]
    if len(data) != expected_size or _sha256(data) != expected_hash:
        raise ValueError(f"{name}: pinned size or SHA-256 mismatch")


def read_pinned(name: str) -> bytes:
    data = (UNICODE_DIR / name).read_bytes()
    verify_bytes(name, data)
    return data


def _safe_xml_root(name: str, data: bytes) -> ET.Element:
    text = data.decode("utf-8")
    if re.search(r"<!ENTITY\b", text, re.IGNORECASE):
        raise ValueError(f"{name}: entity declarations are forbidden")
    declarations = re.findall(r"<!DOCTYPE[^>]*>", text, re.IGNORECASE)
    if declarations != [SAFE_DOCTYPE]:
        raise ValueError(f"{name}: unexpected or missing DOCTYPE")
    text = text.replace(SAFE_DOCTYPE, "", 1)
    try:
        return ET.fromstring(text)
    except ET.ParseError as exc:
        raise ValueError(f"{name}: malformed XML: {exc}") from exc


def _annotation_key(value: str) -> str:
    return value.replace("\ufe0f", "")


def parse_annotations(name: str, data: bytes) -> tuple[dict[str, str], dict[str, list[str]]]:
    root = _safe_xml_root(name, data)
    names: dict[str, str] = {}
    keywords: dict[str, list[str]] = {}
    for element in root.iter("annotation"):
        cp = element.attrib.get("cp")
        value = (element.text or "").strip()
        if not cp or not value:
            continue
        key = _annotation_key(cp)
        if element.attrib.get("type") == "tts":
            names.setdefault(key, value)
            continue
        bucket = keywords.setdefault(key, [])
        for keyword in (part.strip() for part in value.split("|")):
            if keyword and keyword not in bucket:
                bucket.append(keyword)
    return names, keywords


def parse_emoji_test(data: bytes, *, enforce_catalog_contract: bool = False) -> list[SourceEmoji]:
    category: str | None = None
    subgroup: str | None = None
    entries: list[SourceEmoji] = []
    seen: set[tuple[int, ...]] = set()
    line_re = re.compile(r"^([0-9A-F ]+)\s*;\s*([^ ]+)\s*#\s*\S+\s+E[0-9.]+\s+(.+)$")
    for line_number, line in enumerate(data.decode("utf-8").splitlines(), 1):
        if line.startswith("# group: "):
            group = line.removeprefix("# group: ").strip()
            if group == "Component":
                category = None
            elif group in CATEGORY_IDS:
                category = CATEGORY_IDS[group]
            else:
                raise ValueError(f"emoji-test line {line_number}: unknown group {group!r}")
            subgroup = None
            continue
        if line.startswith("# subgroup: "):
            subgroup = line.removeprefix("# subgroup: ").strip()
            continue
        if not line or line.startswith("#"):
            continue
        match = line_re.match(line)
        if not match:
            raise ValueError(f"emoji-test line {line_number}: malformed record")
        if match.group(2) != "fully-qualified":
            continue
        if category is None:  # Component is deliberately not a palette category.
            continue
        if subgroup is None:
            raise ValueError(f"emoji-test line {line_number}: missing subgroup")
        codepoints = tuple(int(value, 16) for value in match.group(1).split())
        if not codepoints or len(codepoints) > 32 or codepoints in seen:
            raise ValueError(f"emoji-test line {line_number}: invalid or duplicate sequence")
        if any(not _valid_scalar(value) for value in codepoints):
            raise ValueError(f"emoji-test line {line_number}: invalid Unicode scalar")
        seen.add(codepoints)
        entries.append(SourceEmoji(codepoints, category, subgroup, match.group(3).strip()))
    if not entries or len(entries) > MAX_ENTRIES:
        raise ValueError("emoji-test: catalog entry count outside bounds")
    if enforce_catalog_contract:
        counts = Counter(entry.category for entry in entries)
        if len(entries) != EXPECTED_ENTRY_COUNT or counts != Counter(EXPECTED_CATEGORY_COUNTS):
            raise ValueError(f"emoji-test: pinned catalog shape changed: {len(entries)} entries, {dict(counts)}")
    return entries


def _valid_scalar(value: int) -> bool:
    return 0 <= value <= 0x10FFFF and not 0xD800 <= value <= 0xDFFF


def family_codepoints(codepoints: tuple[int, ...]) -> tuple[int, ...]:
    return tuple(value for value in codepoints if value != 0xFE0F and not 0x1F3FB <= value <= 0x1F3FF)


def _hex(codepoints: tuple[int, ...]) -> str:
    return " ".join(f"{value:X}" for value in codepoints)


def _validate_field(label: str, value: str) -> None:
    if not value or any(char in value for char in (FIELD_SEPARATOR, "\r", "\n", KEYWORD_SEPARATOR)):
        raise ValueError(f"unsafe {label} field")


def build_catalog() -> str:
    emoji_data = read_pinned("emoji-test-17.0.txt")
    annotation_sources = (
        ("cldr-48-annotations-en.xml", read_pinned("cldr-48-annotations-en.xml")),
        ("cldr-48-annotations-derived-en.xml", read_pinned("cldr-48-annotations-derived-en.xml")),
    )
    names: dict[str, str] = {}
    keywords: dict[str, list[str]] = {}
    for source_name, data in annotation_sources:
        source_names, source_keywords = parse_annotations(source_name, data)
        for key, value in source_names.items():
            names.setdefault(key, value)
        for key, values in source_keywords.items():
            bucket = keywords.setdefault(key, [])
            for value in values:
                if value not in bucket:
                    bucket.append(value)

    entries = parse_emoji_test(emoji_data, enforce_catalog_contract=True)
    lines = [
        MAGIC,
        "# SPDX-License-Identifier: Unicode-3.0",
        "# unicode=17.0",
        f"# cldr=48@{CLDR_COMMIT}",
        f"# count={len(entries)}",
    ]
    missing_annotations: list[str] = []
    for entry in entries:
        sequence = "".join(chr(value) for value in entry.codepoints)
        annotation_key = _annotation_key(sequence)
        name = names.get(annotation_key)
        entry_keywords = keywords.get(annotation_key, [])
        if not name or not entry_keywords:
            missing_annotations.append(_hex(entry.codepoints))
            continue
        for keyword in entry_keywords:
            _validate_field("keyword", keyword)
        if len(entry.subgroup) > 128 or len(name) > 256:
            raise ValueError("annotation text exceeds runtime field bounds")
        if len(entry_keywords) > MAX_KEYWORDS or any(len(value) > 128 for value in entry_keywords):
            raise ValueError("keywords exceed runtime field bounds")
        fields = (
            _hex(entry.codepoints),
            entry.category,
            entry.subgroup,
            _hex(family_codepoints(entry.codepoints)),
            name,
            KEYWORD_SEPARATOR.join(entry_keywords),
        )
        for label, value in zip(("sequence", "category", "subgroup", "family", "name"), fields[:-1]):
            _validate_field(label, value)
        record = FIELD_SEPARATOR.join(fields)
        if len(record) > MAX_LINE_CHARS:
            raise ValueError("generated record exceeds runtime line bound")
        lines.append(record)
    if missing_annotations:
        sample = ", ".join(missing_annotations[:5])
        raise ValueError(f"missing CLDR name/keywords for {len(missing_annotations)} entries: {sample}")
    result = "\n".join(lines) + "\n"
    if len(result) > MAX_CATALOG_CHARS:
        raise ValueError("generated catalog exceeds runtime character bound")
    return result


def expected_outputs() -> tuple[bytes, bytes]:
    catalog = build_catalog().encode("utf-8")
    license_data = read_pinned("LICENSE-UNICODE.txt")
    return catalog, license_data


def _check_file(path: Path, expected: bytes) -> bool:
    if not path.is_file() or path.read_bytes() != expected:
        print(f"out of date: {path.relative_to(ROOT)}", file=sys.stderr)
        return False
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="regenerate the catalog and bundled notice")
    args = parser.parse_args(argv)
    try:
        catalog, notice = expected_outputs()
    except (OSError, UnicodeError, ValueError) as exc:
        print(f"emoji catalog error: {exc}", file=sys.stderr)
        return 1
    if args.write:
        RESOURCE.parent.mkdir(parents=True, exist_ok=True)
        NOTICE.parent.mkdir(parents=True, exist_ok=True)
        RESOURCE.write_bytes(catalog)
        NOTICE.write_bytes(notice)
        print(f"wrote {RESOURCE.relative_to(ROOT)} ({len(catalog)} bytes, {_sha256(catalog)})")
        print(f"wrote {NOTICE.relative_to(ROOT)} ({len(notice)} bytes, {_sha256(notice)})")
        return 0
    return 0 if _check_file(RESOURCE, catalog) and _check_file(NOTICE, notice) else 1


if __name__ == "__main__":
    raise SystemExit(main())
