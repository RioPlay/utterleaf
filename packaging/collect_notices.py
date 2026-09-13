"""Collect third-party license texts into dist/Utterleaf and write THIRD-PARTY-NOTICES.md.

Runs after PyInstaller (packaging/build.ps1 calls it). PACKAGES is the curated
runtime closure: pyproject deps plus their transitive deps. Keep it in sync when
dependencies change — a missing dist-info fails the build on purpose.

PyAV/FFmpeg is deliberately absent: the wheel ships a GPL FFmpeg build, so
packaging/stubs/av replaces it and no FFmpeg code is distributed.
"""

from __future__ import annotations

import email
import hashlib
import json
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
    ("faster_whisper", "Includes the Silero VAD model; see the separate Silero entry."),
    ("ctranslate2", "Native dependencies retain their own terms; see the component notices and provenance."),
    ("tokenizers", "Includes retained license texts for the reviewed native Rust dependency closure."),
    ("onnxruntime", ""),
    ("numpy", ""),
    ("pillow", ""),
    ("sounddevice", "The Windows build includes non-ASIO PortAudio; see licenses/portaudio/LICENSE.txt."),
    ("cffi", ""),
    ("pycparser", ""),
    ("pynput", "LGPLv3. Corresponding source: https://github.com/moses-palmer/pynput"),
    ("pystray", "LGPLv3. Corresponding source: https://github.com/moses-palmer/pystray"),
    ("pyperclip", ""),
    ("websockets", "Local OBS control transport; BSD-3-Clause."),
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

Windows runtime license texts and reviewed component provenance ship under
licenses/ alongside the package notices. The bundled Tcl/Tk runtime includes
its full license.terms under _internal/_tk_data/.

PyAV/FFmpeg: not bundled. PyAV's official wheel carries a GPL build of FFmpeg
(libx264/libx265). Distributing it would put the combined work under GPL
obligations; this project is Apache-2.0 and deliberately chooses not to
accept those terms — a distribution policy, not a claim that permissive
licenses cannot be combined with GPL. Utterleaf feeds microphone audio to
faster-whisper as raw PCM. Packaged file transcription decodes integer PCM WAV
using Python's standard library and the existing NumPy resampler. Other media
formats use an explicitly selected external FFmpeg executable. The frozen build
replaces PyAV with an import-only stub (packaging/stubs/av). No FFmpeg code is
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
    # A license expression is not a substitute for the actual terms. Older
    # wheels need a version-specific, locally reviewed upstream text.
    name = (meta.get("Name") or "").lower().replace("-", "_")
    entry = runtime_notice_manifest()["packages"].get(name)
    if entry is None or entry["version"] != meta.get("Version"):
        raise SystemExit(f"collect_notices: full license text unavailable for {name} {meta.get('Version')}")
    copy_reviewed_notice_files(entry, out_dir)


def runtime_notice_manifest() -> dict:
    """Local reviewed inputs only; packaging never fetches license material."""
    path = ROOT / "packaging" / "notices" / "runtime-manifest.json"
    return json.loads(path.read_text(encoding="utf-8"))


def copy_reviewed_notice_files(entry: dict, out_dir: Path) -> None:
    """Keep complete texts and their upstream provenance together."""
    if entry.get("review_status") != "complete":
        raise SystemExit("collect_notices: component notice review is incomplete")
    if not entry["files"]:
        raise SystemExit("collect_notices: reviewed component has no notice files")
    for item in entry["files"]:
        source_root = item.get("source_root", "notices")
        if source_root not in {"notices", "site"}:
            raise SystemExit("collect_notices: unknown reviewed notice source")
        base = SITE if source_root == "site" else ROOT / "packaging" / "notices"
        source = base / item["path"]
        if not source.is_file() or hashlib.sha256(source.read_bytes()).hexdigest() != item["sha256"]:
            raise SystemExit(f"collect_notices: missing or changed reviewed notice: {item['path']}")
        destination = out_dir / item["destination"]
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    (out_dir / "PROVENANCE.json").write_text(
        json.dumps(entry, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def copy_windows_runtime_notices(licenses_dir: Path) -> list[tuple[str, str, str, str]]:
    """Bind supplemental notices to the inspected Windows native payloads."""
    if sys.platform != "win32":
        return []
    manifest = runtime_notice_manifest()
    if manifest.get("windows_review_status") != "complete":
        raise SystemExit("collect_notices: Windows native notice review is incomplete")
    actual_python = ".".join(str(part) for part in sys.version_info[:3])
    if actual_python != manifest["python_version"]:
        raise SystemExit("collect_notices: Windows Python runtime version requires a new notice review")
    rows = []
    for key, entry in manifest["windows_runtime"].items():
        for relative, expected in entry["payloads"].items():
            payload = DIST / "_internal" / relative
            if not payload.is_file() or hashlib.sha256(payload.read_bytes()).hexdigest() != expected:
                raise SystemExit(f"collect_notices: unreviewed Windows runtime payload: {relative}")
        copy_reviewed_notice_files(entry, licenses_dir / key)
        rows.append((entry["name"], entry["version"], entry["license"],
                     f"Reviewed native component; full texts and provenance: licenses/{key}/."))
    return rows


def license_expression(meta: email.message.Message) -> str:
    if declared := meta.get("License-Expression") or meta.get("License"):
        return declared
    for classifier in meta.get_all("Classifier") or []:
        if classifier.startswith("License :: OSI Approved ::"):
            return classifier.rsplit("::", 1)[-1].strip()
    return "unknown"


def verify_media_policy(directory: Path) -> None:
    """Fail packaging if the excluded FFmpeg/PyAV native libraries leaked in."""
    prefixes = ("avcodec", "avformat", "avdevice", "avfilter", "avutil", "swscale", "swresample", "ffmpeg", "ffprobe")
    for path in directory.rglob("*"):
        if not path.is_file():
            continue
        name = path.name.lower().removeprefix("lib")
        if name.startswith("portaudio") and name.endswith("-asio.dll"):
            raise SystemExit(f"Excluded ASIO library found in packaged output: {path}")
        if name.startswith(prefixes) and any(part in name for part in (".dll", ".so", ".dylib", ".exe")):
            raise SystemExit(f"Excluded media library found in packaged output: {path}")


def copy_vad_notices(licenses_dir: Path) -> tuple[str, str, str, str]:
    """Verify the actual bundled VAD and retain upstream/model/runtime notices.

    Wheel metadata alone omits the Silero copyright and ONNX Runtime's bundled
    third-party notices in the inspected versions. Unknown model bytes need a
    fresh resource review before a new binary is distributed.
    """
    for package, expected in (("faster_whisper", "1.2.1"), ("onnxruntime", "1.28.0")):
        source_info = find_dist_info(package)
        bundled = list((DIST / "_internal").glob(f"{package}-*.dist-info"))
        if (source_info is None or metadata(source_info).get("Version") != expected
                or len(bundled) != 1 or metadata(bundled[0]).get("Version") != expected):
            raise SystemExit(f"collect_notices: unreviewed {package} version; review the VAD wrapper/runtime before distributing")
    model = DIST / "_internal" / "faster_whisper" / "assets" / "silero_vad_v6.onnx"
    approved = "4cbf549b8326f60f80f2536d9eefeb450a9abe83365a098031c89719f1be17d2"
    if (not model.is_file() or model.stat().st_size != 1245151
            or hashlib.sha256(model.read_bytes()).hexdigest() != approved):
        raise SystemExit("collect_notices: bundled Silero identity is unreviewed; review the resource before distributing")
    sources = [
        (ROOT / "packaging" / "notices" / "silero-vad-LICENSE.txt", "silero_vad", "LICENSE.txt"),
        (SITE / "onnxruntime" / "LICENSE", "onnxruntime", "LICENSE"),
        (SITE / "onnxruntime" / "ThirdPartyNotices.txt", "onnxruntime", "ThirdPartyNotices.txt"),
    ]
    for source, package, filename in sources:
        if not source.is_file():
            raise SystemExit(f"collect_notices: required VAD/runtime notice missing: {source.name}")
        destination = licenses_dir / package / filename
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    note = ("Reviewed faster-whisper 1.2.1 sequence export, 1245151 bytes; SHA-256 " + approved
            + ". Origin: https://github.com/SYSTRAN/faster-whisper/tree/65882eee9f5cdbeeb2d877f1131d48cf241b327d"
            + "; upstream model: https://github.com/snakers4/silero-vad/tree/v6.0"
            + ". Full Silero notice: licenses/silero_vad/LICENSE.txt.")
    return ("Silero VAD", "6.0 (faster-whisper export)", "MIT", note)


def main() -> int:
    if SITE is None:
        raise SystemExit("collect_notices: could not find .venv site-packages — run from the repo root")
    if not DIST.exists():
        raise SystemExit(f"collect_notices: {DIST} does not exist — run the build first")
    verify_media_policy(DIST)
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
    rows.append(copy_vad_notices(licenses_dir))
    rows.extend(copy_windows_runtime_notices(licenses_dir))
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
