"""Shared Tk fixture support for behavior tests; screenshot assertions live nowhere here."""

import subprocess
import sys

import pytest

import capture_auxiliary as capture_auxiliary


@pytest.fixture(scope="module")
def working_tk_display():
    probe = subprocess.run(
        [sys.executable, "-c", "import tkinter as tk; r=tk.Tk(); r.withdraw(); r.destroy()"],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    if probe.returncode:
        pytest.skip(f"Tk needs a working display: {probe.stderr.strip()}")
