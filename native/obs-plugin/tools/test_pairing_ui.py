#!/usr/bin/env python3
"""Build and run the isolated native pairing TaskDialog fixture on Windows."""
# SPDX-License-Identifier: GPL-2.0-or-later

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--toolchain", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    receipt_path = output / "pairing-ui-receipt.json"
    receipt_path.unlink(missing_ok=True)
    captures = output / "captures"
    captures.mkdir(exist_ok=True)
    compiler = args.toolchain.resolve() / "bin/x86_64-w64-mingw32-clang.exe"
    windres = args.toolchain.resolve() / "bin/x86_64-w64-mingw32-windres.exe"
    resource = output / "pairing-ui-resource.o"
    pairing_ui_object = output / "pairing-ui.o"
    fixture_object = output / "pairing-ui-test.o"
    executable = output / "pairing-ui-test.exe"
    sources = [
        ROOT / "src/pairing_ui.c",
        ROOT / "src/pairing_ui.h",
        ROOT / "src/plugin_state.h",
        ROOT / "src/authorization.h",
        ROOT / "src/admission.h",
        ROOT / "src/pairing_store.h",
        ROOT / "src/bridge.rc",
        ROOT / "src/bridge.manifest",
        ROOT / "tests/pairing_ui_test.c",
        Path(__file__).resolve(),
    ]
    initial_hashes = {str(path.relative_to(ROOT)): digest(path) for path in sources}
    commands: list[list[str]] = []

    def run(name: str, command: list[str | Path], timeout: int) -> str:
        normalized = [str(part) for part in command]
        commands.append(normalized)
        result = subprocess.run(
            normalized,
            cwd=output,
            env={
                **os.environ,
                "PYTHONNOUSERSITE": "1",
                "PYTHONDONTWRITEBYTECODE": "1",
                "UL_PAIRING_UI_CAPTURE_DIR": str(captures),
            },
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        log = result.stdout + result.stderr
        (output / f"{name}.log").write_text(log, encoding="utf-8")
        if result.returncode:
            raise RuntimeError(f"{name} failed ({result.returncode}); see {name}.log")
        print(f"{name}: passed", flush=True)
        return log

    run(
        "pairing-ui-resource-build",
        [windres, "-I", ROOT / "src", "-i", ROOT / "src/bridge.rc", "-O", "coff", "-o", resource],
        30,
    )
    run(
        "pairing-ui-build",
        [
            compiler,
            "-std=c11",
            "-D_M_X64=100",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-DLoadLibraryExW=fixture_LoadLibraryExW",
            "-DGetProcAddress=fixture_GetProcAddress",
            ROOT / "src/pairing_ui.c",
            "-c",
            "-o",
            pairing_ui_object,
        ],
        30,
    )
    run(
        "pairing-ui-fixture-build",
        [
            compiler,
            "-std=c11",
            "-D_M_X64=100",
            "-Wall",
            "-Wextra",
            "-Werror",
            ROOT / "tests/pairing_ui_test.c",
            "-c",
            "-o",
            fixture_object,
        ],
        30,
    )
    run(
        "pairing-ui-link",
        [
            compiler,
            pairing_ui_object,
            fixture_object,
            resource,
            "-lcomctl32",
            "-lole32",
            "-luuid",
            "-lshell32",
            "-lgdi32",
            "-luser32",
            "-o",
            executable,
        ],
        30,
    )
    log = run("pairing-ui-test", [executable], 20)

    expected_captures = [captures / name for name in ("unpaired.bmp", "paired.bmp", "storage-error.bmp")]
    if any(not path.is_file() or path.stat().st_size < 1024 for path in expected_captures):
        raise RuntimeError("The fixture did not produce all three bounded UI captures")
    final_hashes = {str(path.relative_to(ROOT)): digest(path) for path in sources}
    if final_hashes != initial_hashes:
        raise RuntimeError("Pairing UI fixture sources changed during verification")
    receipt = {
        "schema": 1,
        "scope": (
            "isolated native fixture: real common-controls TaskDialog activation, "
            "rendering and targeted Escape cancellation; no OBS, consumer pairing, "
            "configuration or audio"
        ),
        "limitations": "fixture UI only; no real OBS frontend or physical interaction acceptance",
        "instrumentation": (
            "pass-through LoadLibraryExW/GetProcAddress wrappers record the real module and function; "
            "the TaskDialogIndirect wrapper validates its config, then calls the recorded Windows function"
        ),
        "sources": initial_hashes,
        "compiler_sha256": digest(compiler),
        "windres_sha256": digest(windres),
        "artifacts": {
            path.name: digest(path)
            for path in [resource, pairing_ui_object, fixture_object, executable, *expected_captures]
        },
        "commands": commands,
        "fixture_output": log.splitlines(),
    }
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(receipt_path)


if __name__ == "__main__":
    main()
