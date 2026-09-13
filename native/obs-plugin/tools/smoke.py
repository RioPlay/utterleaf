#!/usr/bin/env python3
"""Load the inert development module through libobs, without the OBS app or audio."""
# SPDX-License-Identifier: GPL-2.0-or-later
from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", type=Path, required=True)
    args = parser.parse_args()
    build = args.build.resolve()
    receipt_path = build / "build-receipt.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    plugin = build / "utterleaf-obs-bridge.dll"
    runtime = Path(receipt["obs_runtime"]["path"]).resolve()
    for path, expected in ((plugin, receipt["generated"][plugin.name]),
                           (runtime, receipt["obs_runtime"]["sha256"]),
                           (Path(__file__), receipt["source"]["tools/smoke.py"])):
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError(f"The reviewed build input changed: {path.name}")
    config = build / "smoke-config"
    config.mkdir(exist_ok=True)
    # Default DLL search excludes the current directory; only this explicitly
    # selected installed runtime supplies libobs's dependencies.
    with os.add_dll_directory(str(runtime.parent)):
        obs = ctypes.CDLL(str(runtime), winmode=0x1100)
        obs.obs_get_version.argtypes = []
        obs.obs_get_version.restype = ctypes.c_uint32
        obs.obs_startup.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_void_p]
        obs.obs_startup.restype = ctypes.c_bool
        obs.obs_open_module.argtypes = [ctypes.POINTER(ctypes.c_void_p), ctypes.c_char_p, ctypes.c_char_p]
        obs.obs_open_module.restype = ctypes.c_int
        obs.obs_init_module.argtypes = [ctypes.c_void_p]
        obs.obs_init_module.restype = ctypes.c_bool
        obs.obs_shutdown.argtypes = []
        obs.obs_shutdown.restype = None
        version = obs.obs_get_version()
        if version != (32 << 24 | 2 << 16 | 2):
            raise ValueError("This native gate requires the reviewed OBS 32.2.2 runtime")
        if not obs.obs_startup(b"en-US", str(config).encode("utf-8"), None):
            raise RuntimeError("libobs startup failed")
        try:
            module = ctypes.c_void_p()
            result = obs.obs_open_module(ctypes.byref(module), str(plugin).encode("utf-8"),
                                         str(build).encode("utf-8"))
            if result != 0 or not module.value:
                raise RuntimeError(f"obs_open_module failed: {result}")
            if not obs.obs_init_module(module):
                raise RuntimeError("obs_init_module failed")
        finally:
            obs.obs_shutdown()
    evidence = {"obs_api_version": version, "obs_open_module": result,
                "obs_init_module": True, "obs_shutdown": "returned",
                "fixture": {"audio_reset": False, "sources_created": 0,
                            "obs_app_started": False},
                "build_receipt_sha256": hashlib.sha256(receipt_path.read_bytes()).hexdigest(),
                "smoke_script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                "plugin_sha256": receipt["generated"][plugin.name],
                "obs_runtime_sha256": receipt["obs_runtime"]["sha256"]}
    (build / "smoke-receipt.json").write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(evidence))


if __name__ == "__main__":
    main()
