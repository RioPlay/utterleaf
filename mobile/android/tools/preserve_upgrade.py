"""Same-signer upgrades must keep keyboard preferences and model files."""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import tempfile
import xml.etree.ElementTree as ET

PACKAGE = "org.utterleaf.voice"
DATA = f"/data/data/{PACKAGE}"
PREFS = "shared_prefs/keyboard.xml"
MARKER = "no_backup/preserve-upgrade.bin"
ACTIVE = "no_backup/active-model"

KEYBOARD_XML = """<?xml version='1.0' encoding='utf-8' standalone='yes' ?>
<map>
    <boolean name="terminal" value="true" />
    <int name="holdDelayMs" value="500" />
</map>
"""
MARKER_BYTES = b"keep\n"
ACTIVE_BYTES = b"tiny.en\n"
GUIDE = (
    "Same-signer package updates must keep keyboard preferences and models. "
    "Reset preferences is a separate explicit action. "
    "See docs/plans/active/android-keyboard-hardening.md."
)


def parse_keyboard_prefs(xml_bytes: bytes) -> dict:
    root = ET.fromstring(xml_bytes)
    values = {}
    for child in root:
        name = child.attrib.get("name")
        if not name:
            continue
        if child.tag == "boolean":
            values[name] = child.attrib.get("value") == "true"
        elif child.tag == "int":
            values[name] = int(child.attrib.get("value", "0"))
    return values


def missing_after_upgrade(before: dict[str, bytes], after: dict[str, bytes]) -> list[str]:
    problems = []
    if PREFS in before:
        if PREFS not in after:
            problems.append(f"{PREFS} missing")
        else:
            expected = parse_keyboard_prefs(before[PREFS])
            actual = parse_keyboard_prefs(after[PREFS])
            for key, value in expected.items():
                if actual.get(key) != value:
                    problems.append(f"{PREFS} {key}={actual.get(key)!r}, expected {value!r}")
    for path in (MARKER, ACTIVE):
        if path in before and after.get(path) != before[path]:
            problems.append(f"{path} missing or changed")
    return problems


def assert_preserved(before: dict[str, bytes], after: dict[str, bytes]) -> None:
    problems = missing_after_upgrade(before, after)
    if problems:
        raise ValueError("; ".join(problems) + ". " + GUIDE)


def seed_files() -> dict[str, bytes]:
    return {
        PREFS: KEYBOARD_XML.encode(),
        MARKER: MARKER_BYTES,
        ACTIVE: ACTIVE_BYTES,
    }


def _run(args: list[str]) -> str:
    result = subprocess.run(args, check=True, capture_output=True, text=True)
    return result.stdout


def _package_uid() -> str:
    dump = _run(["adb", "shell", "dumpsys", "package", PACKAGE])
    match = re.search(r"userId=(\d+)", dump) or re.search(r"appId=(\d+)", dump)
    if not match:
        raise ValueError("Could not find package uid for upgrade seeding. " + GUIDE)
    return match.group(1)


def _write_remote(path: str, data: bytes, uid: str) -> None:
    remote = f"{DATA}/{path}"
    parent = remote.rsplit("/", 1)[0]
    _run(["adb", "shell", "mkdir", "-p", parent])
    staging = f"/data/local/tmp/utterleaf-{path.replace('/', '_')}"
    handle, tmp_path = tempfile.mkstemp()
    try:
        os.write(handle, data)
        os.close(handle)
        handle = -1
        _run(["adb", "push", tmp_path, staging])
        _run(["adb", "shell", "cp", staging, remote])
        _run(["adb", "shell", "chown", f"{uid}:{uid}", remote])
        _run(["adb", "shell", "rm", "-f", staging])
    finally:
        if handle >= 0:
            os.close(handle)
        os.unlink(tmp_path)


def _read_remote(path: str) -> bytes:
    result = subprocess.run(["adb", "exec-out", "cat", f"{DATA}/{path}"], check=True, capture_output=True)
    return result.stdout.replace(b"\r\n", b"\n")


def seed_via_adb() -> None:
    _run(["adb", "root"])
    _run(["adb", "wait-for-device"])
    uid = _package_uid()
    for path, data in seed_files().items():
        _write_remote(path, data, uid)


def verify_via_adb() -> None:
    _run(["adb", "root"])
    _run(["adb", "wait-for-device"])
    after = {path: _read_remote(path) for path in seed_files()}
    assert_preserved(seed_files(), after)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=GUIDE)
    parser.add_argument("action", choices=("seed", "verify"))
    args = parser.parse_args(argv)
    if args.action == "seed":
        seed_via_adb()
    else:
        verify_via_adb()


if __name__ == "__main__":
    main()
