"""Compile the native ULAP encoder and decode its output in Python."""
# SPDX-License-Identifier: GPL-2.0-or-later
from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys

import numpy as np

from utterleaf import obs_protocol as protocol
from utterleaf.obs_mix import BusLabel, MixSnapshot, SourceAssignment


ROOT = Path(__file__).resolve().parents[1]
SESSION = b"0123456789abcdef"


def run(command: list[str | Path], *, binary: bool = False) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            [str(part) for part in command],
            cwd=ROOT,
            env={**os.environ, "PYTHONNOUSERSITE": "1", "PYTHONDONTWRITEBYTECODE": "1"},
            check=True,
            capture_output=True,
            text=not binary,
            timeout=30,
        )
    except subprocess.CalledProcessError as exc:
        diagnostics = exc.stderr if exc.stderr else exc.stdout
        raise RuntimeError(f"fixture command failed: {diagnostics!r}") from exc


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compiler", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--executable", type=Path, help="Already compiled strict native fixture")
    args = parser.parse_args()
    if args.executable is not None:
        if args.compiler is not None or args.output is not None:
            parser.error("--executable cannot be combined with --compiler or --output")
        executable = args.executable.resolve()
    else:
        if args.compiler is None or args.output is None:
            parser.error("Supply --executable or both --compiler and --output")
        output = args.output.resolve()
        output.mkdir(parents=True, exist_ok=True)
        executable = output / "audio_protocol_test.exe"
        compile_result = run([
            args.compiler.resolve(), "-std=c11",
            "-Wall", "-Wextra", "-Werror",
            ROOT / "src/audio_protocol.c", ROOT / "tests/audio_protocol_test.c",
            "-o", executable,
        ])
        if compile_result.stdout or compile_result.stderr:
            raise AssertionError("strict native compilation produced output")
    native = run([executable])
    if native.stdout.strip() != "native ULAP encoder and routing vectors and bounds passed" or native.stderr:
        raise AssertionError("unexpected native fixture output")

    emitted = run([executable, "--emit"], binary=True)
    if emitted.stderr:
        raise AssertionError("native emitter wrote diagnostics")
    decoder = protocol.FrameDecoder()
    frames = decoder.feed(emitted.stdout)
    decoder.finish()
    expected = [
        protocol.StartFrame(SESSION, 48000, 1, 6, 10),
        protocol.AudioFrame(
            SESSION, 1, 7, 456, 1,
            np.asarray((0.25, -0.25), dtype="<f4").tobytes(),
        ),
        protocol.GapFrame(SESSION, 1, 8, 2, 789),
        protocol.EndFrame(
            SESSION, protocol.EndReason.STREAM_STOPPED, ((1, 9), (2, None)),
        ),
    ]
    if frames != expected:
        raise AssertionError("Python decoder disagrees with native wire bytes")

    emitted_routing = run([executable, "--emit-routing"], binary=True)
    if emitted_routing.stderr:
        raise AssertionError("native routing emitter wrote diagnostics")
    routing = protocol.RoutingFrame(
        SESSION, 1, 0x0102030405060708, ((1, 7), (2, protocol.UINT64_MAX)),
        MixSnapshot(
            1, 6,
            (
                SourceAssignment(bytes(15) + b"\x01", "A", 2),
                SourceAssignment(bytes(15) + b"\x02", "B", 4),
            ),
            (BusLabel(1, "Main"), BusLabel(2, "Aux")),
        ),
    )
    routing_decoder = protocol.FrameDecoder(version=protocol.PROVENANCE_VERSION)
    routing_frames = routing_decoder.feed(emitted_routing.stdout)
    routing_decoder.finish()
    if routing_frames != [routing]:
        raise AssertionError("Python decoder disagrees with native routing bytes")
    if emitted_routing.stdout != protocol.encode_frame(
        routing, version=protocol.PROVENANCE_VERSION
    ):
        raise AssertionError("Python encoder disagrees with native routing bytes")
    print("native/Python ULAP interoperability passed")


if __name__ == "__main__":
    if sys.platform != "win32":
        raise SystemExit("The native ULAP fixture requires Windows")
    main()
