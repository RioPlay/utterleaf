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
SOURCES = (
    "bridge", "plugin_state", "pairing_ui", "vendor_dispatch", "pairing_store",
    "authorization", "admission", "handshake", "crypto", "session_protocol",
    "audio_protocol", "audio_queue", "audio_convert", "audio_capture",
    "audio_stream", "frontend_dispatch",
)
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
    (output / "build-receipt.json").unlink(missing_ok=True)
    lock = json.loads((ROOT / "dependencies.json").read_text(encoding="utf-8"))
    revision = lock["obs_revision"]
    prefix = f"https://raw.githubusercontent.com/obsproject/obs-studio/{revision}/"
    websocket_url = ("https://raw.githubusercontent.com/obsproject/obs-websocket/"
                     + lock["obs_websocket_revision"] + "/lib/obs-websocket-api.h")
    for relative, resource in lock["resources"].items():
        path = (headers / relative).resolve()
        expected_url = websocket_url if relative == "obs-websocket/obs-websocket-api.h" else prefix + relative
        if not path.is_relative_to(headers) or resource["url"] != expected_url:
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
    frontend = args.obs_bin.resolve() / "obs-frontend-api.dll"
    runtime_hash = digest(obs)
    frontend_hash = digest(frontend)
    source_names = ["src/" + name + ".c" for name in SOURCES]
    source_names += ["src/" + name + ".h" for name in SOURCES if name != "bridge"]
    source_names += ["src/bridge.def", "src/bridge.rc", "src/bridge.manifest",
                     "dependencies.json", "COPYING", "tools/build.py", "tools/smoke.py"]
    source_hashes = {name: digest(ROOT / name) for name in source_names}
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
    run([str(tools / "gendef.exe"), "--no-include-current-dir", str(frontend)])
    run([str(tools / "llvm-dlltool.exe"), "-m", "i386:x86-64", "-d",
         str(output / "obs-frontend-api.def"), "-l", str(output / "libobs-frontend.dll.a")])
    resource_object = output / "bridge-resource.o"
    run([str(tools / "x86_64-w64-mingw32-windres.exe"), "-I", str(ROOT / "src"),
         "-i", str(ROOT / "src/bridge.rc"), "-O", "coff", "-o", str(resource_object)])
    plugin = output / "utterleaf-obs-bridge.dll"
    objects, dependency_files = [], []
    for name in SOURCES:
        obj, dep = output / (name + ".o"), output / (name + ".d")
        run([str(compiler), "-std=c11", "-D_M_X64=100", "-Wall", "-Wextra", "-Werror", "-O2",
             f"-ffile-prefix-map={ROOT}=native/obs-plugin", f"-I{headers / 'libobs'}",
             f"-I{headers / 'frontend/api'}", f"-I{headers / 'obs-websocket'}", f"-I{output}",
             "-MD", "-MF", str(dep), "-c", str(ROOT / ("src/" + name + ".c")), "-o", str(obj)])
        objects.append(obj)
        dependency_files.append(dep)
    run([str(compiler), "-shared", *map(str, objects), str(resource_object),
         str(ROOT / "src/bridge.def"), str(output / "libobs.dll.a"), str(output / "libobs-frontend.dll.a"),
         "-lbcrypt", "-lcrypt32", "-ladvapi32", "-lshell32", "-lole32", "-luuid", "-luser32",
         "-Wl,--no-insert-timestamp,--exclude-all-symbols", "-o", str(plugin)])
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
               "api-ms-win-crt-heap-l1-1-0.dll", "api-ms-win-crt-string-l1-1-0.dll",
               "obs-frontend-api.dll", "bcrypt.dll", "crypt32.dll", "advapi32.dll",
               "shell32.dll", "ole32.dll", "user32.dll"}
    if {name.lower() for name in imports} != allowed or len(imports) != len(allowed):
        raise ValueError(f"Unreviewed runtime import: {imports}")
    if digest(obs) != runtime_hash or digest(frontend) != frontend_hash:
        raise ValueError("OBS runtime changed during the build")
    if any(digest(ROOT / name) != expected for name, expected in source_hashes.items()):
        raise ValueError("Native source changed during the build")

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
    websocket_header = (headers / "obs-websocket/obs-websocket-api.h").read_text(encoding="utf-8")
    websocket_notice = re.match(r"\s*(/\*.*?\*/)", websocket_header, flags=re.S)
    if websocket_notice is None or "GNU General Public License" not in websocket_notice[1]:
        raise ValueError("Missing obs-websocket header license")
    (output / "OBS-WEBSOCKET-NOTICE.txt").write_text(websocket_notice[1] + "\n\nGPL terms: see COPYING-OBS.txt.\n", encoding="utf-8")
    # This development receipt is not a complete binary redistribution review.
    shutil.copyfile(args.toolchain / "LICENSE.TXT", output / "LLVM-LICENSE.txt")
    generated = [plugin, output / "obsconfig.h", output / "obs.def", output / "libobs.dll.a",
                 output / "obs-frontend-api.def", output / "libobs-frontend.dll.a", resource_object,
                 *objects, *dependency_files, output / "pe-inventory.txt", output / "LLVM-LICENSE.txt",
                 output / "COPYING.txt", output / "COPYING-OBS.txt", output / "OBS-HEADER-NOTICES.txt",
                 output / "OBS-WEBSOCKET-NOTICE.txt"]
    receipt = {"obs_revision": revision, "obs_runtime": {"path": str(obs), "sha256": runtime_hash},
               "obs_frontend_runtime": {"path": str(frontend), "sha256": frontend_hash},
               "obs_websocket_revision": lock["obs_websocket_revision"],
               "compiler": {"version": version.strip(), "sha256": digest(compiler)},
               "invoked_tools": {name: digest(tools / name) for name in (
                   compiler.name, "gendef.exe", "llvm-dlltool.exe", "llvm-readobj.exe",
                   "x86_64-w64-mingw32-windres.exe")},
               "toolchain_scope": "Installed toolchain is not fully pinned: driver configuration, linker, headers and static runtime inputs remain unbound",
               "source": source_hashes,
               "inputs": lock["resources"], "generated": {p.name: digest(p) for p in generated},
               "exports": exports, "imports": imports, "commands": commands,
               "distribution": "development only; no OBS DLLs included; runtime/source distribution review remains open"}
    (output / "build-receipt.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(plugin)


if __name__ == "__main__":
    main()
