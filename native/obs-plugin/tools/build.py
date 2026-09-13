#!/usr/bin/env python3
"""Build the separate development OBS DLL from pinned public headers."""
# SPDX-License-Identifier: GPL-2.0-or-later
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
ISC_HEADERS = (
    "callback/calldata.h", "callback/proc.h", "callback/signal.h",
    "util/base.h", "util/bmem.h", "util/c99defs.h", "util/darray.h",
    "util/text-lookup.h", "util/util_uint64.h",
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--toolchain", type=Path, required=True, help="LLVM-MinGW root")
    parser.add_argument("--obs-bin", type=Path, required=True, help="Installed OBS 32.2.2 bin/64bit directory")
    parser.add_argument("--headers", type=Path, required=True, help="Public-header cache")
    parser.add_argument("--output", type=Path, required=True, help="Separate development build directory")
    parser.add_argument("--fetch", action="store_true", help="Explicitly acquire missing pinned public headers")
    args = parser.parse_args()
    headers, output = args.headers.resolve(), args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    lock = json.loads((ROOT / "dependencies.json").read_text(encoding="utf-8"))
    revision = lock["obs_revision"]
    prefix = f"https://raw.githubusercontent.com/obsproject/obs-studio/{revision}/"
    for relative, resource in lock["resources"].items():
        path = (headers / relative).resolve()
        if not path.is_relative_to(headers) or resource["url"] != prefix + relative:
            raise ValueError("Unexpected public-header path or origin")
        if not path.is_file():
            if not args.fetch:
                raise FileNotFoundError(f"Missing {relative}; use --fetch to acquire pinned inputs")
            with urllib.request.urlopen(resource["url"], timeout=30) as response:
                data = response.read(resource["bytes"] + 1)
            if len(data) != resource["bytes"] or hashlib.sha256(data).hexdigest() != resource["sha256"]:
                raise ValueError(f"Public-header verification failed: {relative}")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        if path.stat().st_size != resource["bytes"] or digest(path) != resource["sha256"]:
            raise ValueError(f"Pinned input differs: {relative}")

    template = (headers / "libobs/obsconfig.h.in").read_text(encoding="utf-8")
    config = re.sub(r"^#cmakedefine (\w+).*$", r"/* #undef \1 */", template, flags=re.M)
    config = config.replace("@OBS_RELEASE_CANDIDATE@", "0").replace("@OBS_BETA@", "0")
    if "@" in config or "#cmakedefine" in config:
        raise ValueError("Unrecognized generated OBS configuration input")
    (output / "obsconfig.h").write_text(config, encoding="utf-8")

    tools = args.toolchain.resolve() / "bin"
    compiler = tools / "x86_64-w64-mingw32-clang.exe"
    obs = args.obs_bin.resolve() / "obs.dll"
    runtime_hash = digest(obs)
    commands: list[list[str]] = []

    def run(command: list[str]) -> str:
        commands.append(command)
        result = subprocess.run(command, cwd=output, check=True, capture_output=True,
                                text=True, timeout=60)
        return result.stdout + result.stderr

    version = run([str(compiler), "--version"])
    if "Target: x86_64-w64-windows-gnu" not in version:
        raise ValueError("The build requires the x64 Windows GNU C ABI")
    run([str(tools / "gendef.exe"), "--no-include-current-dir", str(obs)])
    run([str(tools / "llvm-dlltool.exe"), "-m", "i386:x86-64", "-d",
         str(output / "obs.def"), "-l", str(output / "libobs.dll.a")])
    plugin = output / "utterleaf-obs-bridge.dll"
    run([str(compiler), "-std=c11", "-D_M_X64=100", "-Wall", "-Wextra", "-Werror",
         "-O2", "-shared", f"-ffile-prefix-map={ROOT}=native/obs-plugin",
         f"-I{headers / 'libobs'}", f"-I{output}", str(ROOT / "src/bridge.c"),
         str(ROOT / "src/bridge.def"), str(output / "libobs.dll.a"),
         "-Wl,--no-insert-timestamp,--exclude-all-symbols", "-MD", "-MF",
         str(output / "bridge.d"), "-o", str(plugin)])
    inventory = run([str(tools / "llvm-readobj.exe"), "--file-headers", "--coff-imports",
                     "--coff-exports", str(plugin)])
    (output / "pe-inventory.txt").write_text(inventory, encoding="utf-8")
    if "Machine: IMAGE_FILE_MACHINE_AMD64" not in inventory:
        raise ValueError("Unexpected plugin architecture")
    exports = re.findall(r"Export \{.*?\n  Name: ([^\n]+)", inventory, re.S)
    expected = {line.strip() for line in (ROOT / "src/bridge.def").read_text().splitlines()[2:]}
    if set(exports) != expected or len(exports) != len(expected):
        raise ValueError(f"Unexpected exports: {exports}")
    imports = re.findall(r"Import \{\s*Name: ([^\n]+)", inventory)
    allowed = {"obs.dll", "kernel32.dll", "api-ms-win-crt-runtime-l1-1-0.dll",
               "api-ms-win-crt-private-l1-1-0.dll", "api-ms-win-crt-stdio-l1-1-0.dll",
               "api-ms-win-crt-heap-l1-1-0.dll", "api-ms-win-crt-string-l1-1-0.dll"}
    if {name.lower() for name in imports} != allowed or len(imports) != len(allowed):
        raise ValueError(f"Unreviewed runtime import: {imports}")
    if digest(obs) != runtime_hash:
        raise ValueError("OBS runtime changed during the build")

    shutil.copyfile(headers / "COPYING", output / "COPYING-OBS.txt")
    shutil.copyfile(ROOT / "COPYING", output / "COPYING.txt")
    notices = ["OBS public-header notices\nGPL terms: see COPYING-OBS.txt.\n"
               "The following headers have separate ISC-style terms.\n"]
    for relative in ISC_HEADERS:
        name = "libobs/" + relative
        if name not in lock["resources"]:
            raise ValueError(f"Notice input is not pinned: {name}")
        content = (headers / name).read_text(encoding="utf-8")
        notice = re.match(r"\s*(/\*.*?\*/)", content, flags=re.S)
        if notice is None or "Permission to use, copy, modify, and distribute" not in notice[1]:
            raise ValueError(f"Expected header notice is missing: {name}")
        notices.append(f"\n{name}\n{notice[1]}\n")
    (output / "OBS-HEADER-NOTICES.txt").write_text("".join(notices), encoding="utf-8")
    # This development receipt is not a complete binary redistribution review.
    shutil.copyfile(args.toolchain / "LICENSE.TXT", output / "LLVM-LICENSE.txt")
    generated = [plugin, output / "obsconfig.h", output / "obs.def", output / "libobs.dll.a",
                 output / "bridge.d", output / "pe-inventory.txt", output / "LLVM-LICENSE.txt",
                 output / "COPYING.txt", output / "COPYING-OBS.txt", output / "OBS-HEADER-NOTICES.txt"]
    receipt = {"obs_revision": revision, "obs_runtime": {"path": str(obs), "sha256": runtime_hash},
               "compiler": {"version": version.strip(), "sha256": digest(compiler)},
               "invoked_tools": {name: digest(tools / name) for name in (
                   compiler.name, "gendef.exe", "llvm-dlltool.exe", "llvm-readobj.exe")},
               "toolchain_scope": "Installed toolchain is not fully pinned: driver configuration, linker, headers and static runtime inputs remain unbound",
               "source": {name: digest(ROOT / name) for name in (
                   "src/bridge.c", "src/bridge.def", "dependencies.json", "COPYING",
                   "tools/build.py", "tools/smoke.py")},
               "inputs": lock["resources"], "generated": {p.name: digest(p) for p in generated},
               "exports": exports, "imports": imports, "commands": commands,
               "distribution": "development only; no OBS DLLs included; runtime/source distribution review remains open"}
    (output / "build-receipt.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(plugin)


if __name__ == "__main__":
    main()
