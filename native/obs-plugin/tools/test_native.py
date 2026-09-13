"""Build and exercise Windows admission primitives without OBS or audio."""
# SPDX-License-Identifier: GPL-2.0-or-later
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--toolchain", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if sys.platform != "win32":
        raise SystemExit("These native admission checks require Windows")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    # A failed rerun must not leave a previous passing receipt in place.
    receipt_path = output / "test-receipt.json"
    receipt_path.unlink(missing_ok=True)
    compiler = args.toolchain.resolve() / "bin/x86_64-w64-mingw32-clang.exe"
    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO)
    env["PYTHONNOUSERSITE"] = "1"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    commands = []
    logs = []
    sources = [ROOT / name for name in (
        "src/handshake.c", "src/handshake.h", "src/admission.c", "src/admission.h",
        "tests/handshake_test.c", "tests/handshake_failure_test.c",
        "tests/admission_identity_test.c",
        "tests/admission.def", "tests/test_admission.py", "tools/test_native.py",
    )]
    source_hashes = {str(path.relative_to(ROOT)): digest(path) for path in sources}

    def run(name: str, arguments: list[str | Path], timeout: int = 60) -> None:
        command = [str(arg) for arg in arguments]
        commands.append(command)
        result = subprocess.run(command, cwd=output, env=env, capture_output=True,
                                text=True, timeout=timeout)
        log = result.stdout + result.stderr
        log_path = output / (name + ".log")
        log_path.write_text(log, encoding="utf-8")
        logs.append(log_path)
        if result.returncode:
            raise RuntimeError(f"{name} failed ({result.returncode}); see its local log")
        print(f"{name}: passed", flush=True)

    flags = [compiler, "-std=c11", "-Wall", "-Wextra", "-Werror"]
    fixed = output / "handshake_test.exe"
    fault = output / "handshake_failure_test.exe"
    dll = output / "utterleaf-admission-test.dll"
    identity = output / "admission_identity_test.exe"
    run("compiler", [compiler, "--version"])
    run("handshake-build", [*flags, ROOT / "src/handshake.c",
                           ROOT / "tests/handshake_test.c", "-lbcrypt", "-o", fixed])
    run("handshake-test", [fixed])
    functions = (
        "BCryptOpenAlgorithmProvider", "BCryptGetProperty", "BCryptCreateHash",
        "BCryptHashData", "BCryptFinishHash", "BCryptDestroyHash",
        "BCryptCloseAlgorithmProvider", "GetProcessHeap", "HeapAlloc", "HeapFree",
    )
    fault_obj = output / "handshake_failure.obj"
    shim_obj = output / "handshake_shims.obj"
    run("handshake-fault-object", [*flags, *[f"-D{name}=shim_{name}" for name in functions],
                                  "-c", ROOT / "src/handshake.c", "-o", fault_obj])
    run("handshake-fault-shims", [*flags, "-c", ROOT / "tests/handshake_failure_test.c",
                                 "-o", shim_obj])
    run("handshake-fault-link", [compiler, fault_obj, shim_obj, "-o", fault])
    run("handshake-fault-test", [fault])
    run("admission-identity-build", [*flags, ROOT / "tests/admission_identity_test.c",
                                     ROOT / "src/handshake.c", "-ladvapi32", "-lbcrypt",
                                     "-o", identity])
    run("admission-identity-test", [identity])
    run("admission-build", [*flags, "-shared", ROOT / "src/admission.c",
                            ROOT / "src/handshake.c", ROOT / "tests/admission.def",
                            "-ladvapi32", "-lbcrypt", "-o", dll])
    # The outer process timeout bounds fixture failures, including a stalled
    # native operation that must retain its OVERLAPPED buffers until completion.
    run("admission-test", [sys._base_executable, ROOT / "tests/test_admission.py", dll])
    if source_hashes != {str(path.relative_to(ROOT)): digest(path) for path in sources}:
        raise RuntimeError("Source changed during native verification")
    receipt = {
        "schema": 1, "scope": "native primitives only; no OBS dispatch, arming or audio",
        "sources": source_hashes, "compiler_sha256": digest(compiler),
        "artifacts": {path.name: digest(path) for path in (fixed, fault, identity, dll)},
        "logs": {path.name: digest(path) for path in logs},
        "commands": commands,
    }
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
