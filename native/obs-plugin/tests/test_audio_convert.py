"""Run synthetic conversion with an explicitly selected libobs; no OBS startup."""
# SPDX-License-Identifier: GPL-2.0-or-later
from __future__ import annotations

import ctypes
import os
from pathlib import Path
import sys


def main() -> None:
    runtime, fixture = (Path(value).resolve() for value in sys.argv[1:])
    # Exclude the current directory and PATH from dependency lookup, and load
    # the reviewed runtime first so the fixture binds to that exact libobs.
    with os.add_dll_directory(str(runtime.parent)):
        obs = ctypes.CDLL(str(runtime), winmode=0x1100)
        obs.obs_get_version.argtypes = []
        obs.obs_get_version.restype = ctypes.c_uint32
        if obs.obs_get_version() != (32 << 24 | 2 << 16 | 2):
            raise ValueError("The conversion fixture requires OBS 32.2.2")
        library = ctypes.CDLL(str(fixture), winmode=0x1100)
        library.main.argtypes = []
        library.main.restype = ctypes.c_int
        if library.main() != 0:
            raise RuntimeError("Native synthetic conversion failed")


if __name__ == "__main__":
    main()
