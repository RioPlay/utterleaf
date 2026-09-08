"""Collect third-party license texts into dist/Utterleaf and write THIRD-PARTY-NOTICES.md.

Runs after PyInstaller (packaging/build.ps1 calls it). PACKAGES is the curated
runtime closure: pyproject deps plus their transitive deps. Keep it in sync when
dependencies change — a missing dist-info fails the build on purpose.

PyAV/FFmpeg is deliberately absent: the wheel ships a GPL FFmpeg build, so
packaging/stubs/av replaces it and no FFmpeg code is distributed.
"""

from __future__ import annotations

import email
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist" / "Utterleaf"


def site_packages() -> Path | None:
    """The project venv's site-packages, Windows or POSIX layout."""
    windows = ROOT / ".venv" / "Lib" / "site-packages"
    if windows.is_dir():
        return windows
    candidates = sorted((ROOT / ".venv" / "lib").glob("python*/site-packages"))
    if candidates:
        return candidates[-1]
    return None


SITE = site_packages()

# dist-info names for everything the frozen app ships. The notice column adds
# context the license files themselves don't have (LGPL source offers, bundles).
PACKAGES: list[tuple[str, str]] = [
    ("faster_whisper", ""),
    ("ctranslate2", ""),
    ("tokenizers", ""),
    ("onnxruntime", ""),
    ("numpy", ""),
    ("pillow", ""),
    ("sounddevice", "Bundles PortAudio; the PortAudio license ships under _sounddevice_data."),
    ("cffi", ""),
    ("pycparser", ""),
    ("pynput", "LGPLv3. Corresponding source: https://github.com/moses-palmer/pynput"),
    ("pystray", "LGPLv3. Corresponding source: https://github.com/moses-palmer/pystray"),
    ("pyperclip", ""),
    ("pywin32_ctypes", ""),
    ("six", ""),
    ("huggingface_hub", ""),
    ("hf_xet", ""),
    ("httpx", ""),
    ("httpcore", ""),
    ("h11", ""),
    ("anyio", ""),
    ("idna", ""),
    ("certifi", ""),
    ("fsspec", ""),
    ("filelock", ""),
    ("packaging", ""),
    ("pyyaml", ""),
    ("tqdm", ""),
    ("colorama", ""),
    ("typing_extensions", ""),
    ("protobuf", ""),
    ("flatbuffers", ""),
    ("pygments", ""),
    ("click", ""),
]

NVIDIA_PACKAGES = [
    "nvidia_cublas_cu12",
    "nvidia_cudnn_cu12",
    "nvidia_cuda_runtime_cu12",
    "nvidia_cuda_nvrtc_cu12",
]

HEADER = """\
Utterleaf — third-party notices

Utterleaf is licensed under the Apache License, Version 2.0 (see LICENSE and
NOTICE). It bundles the packages below; each entry's license text ships next
to this file under licenses/<package>/.

Python itself is PSF-licensed (https://www.python.org/psf/license/) and the
bundled Tcl/Tk runtime uses the Tcl license
(https://www.tcl.tk/software/tcltk/license.html).

PyAV/FFmpeg: not bundled. PyAV's official wheel carries a GPL build of FFmpeg
(libx264/libx265). Distributing it would put the combined work under GPL
obligations; this project is Apache-2.0 and deliberately chooses not to
accept those terms — a distribution policy, not a claim that permissive
licenses cannot be combined with GPL. Utterleaf feeds microphone audio to
faster-whisper as raw PCM and never uses PyAV, so the frozen build replaces
it with an import-only stub (packaging/stubs/av). No FFmpeg code is
distributed.

"""


def metadata(dist_info: Path) -> email.message.Message:
    with open(dist_info / "METADATA", encoding="utf-8") as fh:
        return email.message_from_file(fh)


def find_dist_info(name: str) -> Path | None:
    if SITE is None:
        return None
    matches = sorted(SITE.glob(f"{name}-*.dist-info"))
    if not matches:
        if sys.platform == "win32":
            raise SystemExit(f"collect_notices: {name} not found in {SITE} — update PACKAGES")
        # macOS/Linux dependency closures legitimately omit Windows-only or
        # conditional packages (pywin32_ctypes, colorama, ...); skip them.
        print(f"collect_notices: {name} not bundled on {sys.platform}; skipping its notice")
        return None
    return matches[-1]


def copy_license_files(dist_info: Path, meta: email.message.Message, out_dir: Path) -> None:
    copied = False
    # PEP 639 wheels keep every license under <dist-info>/licenses/ — take the
    # whole tree so bundled-library licenses (numpy's lapack_lite, svml, ...) ship too.
    tree = dist_info / "licenses"
    if tree.is_dir():
        for src in tree.rglob("*"):
            if src.is_file():
                dest = out_dir / src.relative_to(tree)
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dest)
                copied = True
    for entry in meta.get_all("License-File") or []:
        for base in (tree, dist_info, SITE):
            src = base / entry
            if src.exists():
                dest = out_dir / src.relative_to(base)
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dest)
                copied = True
                break
        else:
            raise SystemExit(f"collect_notices: {dist_info.name} lists missing license file {entry}")
    if copied:
        return
    # Old-style wheels carry no License-File; keep the declared expression on record.
    declared = meta.get("License-Expression") or meta.get("License") or "(see package metadata)"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "LICENSE-DECLARED.txt").write_text(
        f"{meta.get('Name')} {meta.get('Version')}: {declared}\n", encoding="utf-8"
    )


def license_expression(meta: email.message.Message) -> str:
    if declared := meta.get("License-Expression") or meta.get("License"):
        return declared
    for classifier in meta.get_all("Classifier") or []:
        if classifier.startswith("License :: OSI Approved ::"):
            return classifier.rsplit("::", 1)[-1].strip()
    return "unknown"


def main() -> int:
    if SITE is None:
        raise SystemExit("collect_notices: could not find .venv site-packages — run from the repo root")
    if not DIST.exists():
        raise SystemExit(f"collect_notices: {DIST} does not exist — run the build first")
    shutil.copy2(ROOT / "LICENSE", DIST / "LICENSE")
    shutil.copy2(ROOT / "NOTICE", DIST / "NOTICE")
    licenses_dir = DIST / "licenses"
    if licenses_dir.exists():
        shutil.rmtree(licenses_dir)
    rows = []
    names = [name for name, _ in PACKAGES]
    notes = dict(PACKAGES)
    if (DIST / "_internal" / "nvidia").exists():
        names.extend(NVIDIA_PACKAGES)
        for name in NVIDIA_PACKAGES:
            notes[name] = "NVIDIA proprietary; redistributable with the application per its EULA."
    for name in names:
        dist_info = find_dist_info(name)
        if dist_info is None:
            continue
        meta = metadata(dist_info)
        expression = license_expression(meta)
        copy_license_files(dist_info, meta, licenses_dir / name)
        rows.append((meta.get("Name") or name, meta.get("Version") or "?", expression, notes[name]))
    lines = [HEADER]
    for pkg, version, expression, note in sorted(rows, key=lambda r: r[0].lower()):
        lines.append(f"* {pkg} {version} — {expression}")
        if note:
            lines.append(f"  {note}")
    lines.append("")
    (DIST / "THIRD-PARTY-NOTICES.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"Notices for {len(rows)} packages -> {licenses_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
