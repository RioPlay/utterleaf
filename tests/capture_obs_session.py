"""Capture inert OBS session UI states for visual QA; opens no OBS or audio APIs."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
import time
import tkinter as tk
from types import SimpleNamespace

from PIL import ImageGrab

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from utterleaf.obs_session_ui import ObsSessionWindow
from utterleaf.obs_mix import BusLabel, MixSnapshot, SourceAssignment
from utterleaf.obs_protocol import RoutingFrame


class SnapshotSource:
    def __init__(self, value):
        self.value = value

    def snapshot(self):
        return self.value


class InertActions:
    def __getattr__(self, name):
        def unexpected(*_args):
            raise AssertionError(f"capture helper unexpectedly invoked {name}")

        return unexpected


def session(state, message, *, degraded=False, primary=None, buses=(), seconds=0.0):
    return SimpleNamespace(
        state=state,
        message=message,
        control_degraded=degraded,
        primary_bus=primary,
        buses=buses,
        captured_seconds=seconds,
    )


def recognition(state, message, *, preview="", tracks=0, completed=0, incomplete=False):
    return SimpleNamespace(
        state=state,
        message=message,
        preview=preview,
        track_count=tracks,
        completed_tracks=completed,
        incomplete=incomplete,
    )


STATES = {
    "disabled": (
        session("disabled", "OBS transcription is off."),
        recognition("waiting", "Connect to local OBS to begin."),
    ),
    "ready": (
        session("ready", "Authenticated locally. OBS is idle and ready to arm."),
        recognition("waiting", "Choose optional OBS mixes, then arm the next stream."),
    ),
    "armed": (
        session("armed", "Start streaming in OBS when you are ready."),
        recognition("waiting", "Waiting for the authenticated stream to begin."),
    ),
    "active": (
        session("active", "Receiving the explicitly armed OBS stream.", primary=0,
                buses=(0, 2), seconds=74.2),
        recognition(
            "running", "Transcribing two selected OBS mixes locally.",
            preview=(
                "Mix 1\nWelcome back. Today we are reviewing the launch plan and the final questions.\n\n"
                "Mix 3\nThe music bed fades under the conversation while the complete stream mix continues."
            ),
            tracks=2,
        ),
    ),
    "degraded": (
        session("active", "Audio remains authenticated and continues locally.", degraded=True,
                primary=2, buses=(0, 2, 5), seconds=188.4),
        recognition(
            "running", "OBS controls disconnected; accepted audio is still being transcribed.",
            preview=(
                "Mix 3\nThe control connection dropped, but this already authenticated capture remains active.\n\n"
                "Mix 1\nUse Stop to end the local capture when the control connection is unavailable."
            ),
            tracks=3,
            completed=1,
        ),
    ),
    "incomplete": (
        session("incomplete", "The stream ended before every selected mix finished.",
                primary=1, buses=(0, 1), seconds=246.0),
        recognition(
            "incomplete", "Recovered transcript retained for review or explicit export.",
            preview=(
                "Mix 2\nThe recovered portion remains available. Review it before exporting or discarding.\n\n"
                "Mix 1\nThe final words from this mix were not received."
            ),
            tracks=2,
            completed=1,
            incomplete=True,
        ),
    ),
}

STATES["active"][0].routing = RoutingFrame(
    b"s" * 16, 2, 80_000_000_000, ((0, 20), (2, 20)),
    MixSnapshot(0, 5,
                (SourceAssignment(b"a" * 16, "Host microphone", 5),
                 SourceAssignment(b"b" * 16, "Guest call and desktop audio", 5)),
                (BusLabel(0, "Mix 1"), BusLabel(2, "Mix 3"))),
)

CAPTURES = (
    ("disabled", "disabled", "840x720+80+60"),
    ("ready", "ready", "840x720+80+60"),
    ("armed", "armed", "840x720+80+60"),
    ("active", "active", "840x720+80+60"),
    ("degraded", "degraded", "840x720+80+60"),
    ("incomplete", "incomplete", "840x720+80+60"),
    ("compact-disabled", "disabled", "560x520+80+60"),
    ("compact-active", "active", "560x520+80+60"),
    ("compact-degraded", "degraded", "560x520+80+60"),
    ("active-mixes", "active", "840x720+80+60"),
    ("compact-mixes", "active", "560x520+80+60"),
)


def capture(output: Path | None = None) -> Path:
    source_root = Path(__file__).resolve().parents[1]
    output = Path(output) if output is not None else (
        source_root / ".grok" / "obs-session-controller" / "ui"
    )
    output.mkdir(parents=True, exist_ok=True)
    root = tk.Tk()
    root.geometry("1x1+0+0")
    controller = SnapshotSource(STATES["disabled"][0])
    coordinator = SnapshotSource(STATES["disabled"][1])
    window = ObsSessionWindow(root, controller, coordinator, InertActions(), poll_ms=60_000)
    window.root.geometry("840x720+80+60")
    window.root.attributes("-topmost", True)
    window.root.deiconify()
    window.root.lift()
    try:
        for name, state_name, geometry in CAPTURES:
            controller.value, coordinator.value = STATES[state_name]
            window.root.geometry(geometry)
            window.refresh()
            window.preview_tabs.select(1 if name.endswith("-mixes") else 0)
            for _ in range(5):
                root.update()
                time.sleep(0.04)
            width, height = window.root.winfo_width(), window.root.winfo_height()
            expected_width, expected_height = map(int, geometry.split("+")[0].split("x"))
            if (width, height) != (expected_width, expected_height) or not window.root.winfo_ismapped():
                raise RuntimeError(f"{name} did not map at {expected_width}x{expected_height}")
            image = ImageGrab.grab(window=window.root.winfo_id())
            extrema = image.convert("RGB").getextrema()
            if image.size != (width, height) or not any(low != high for low, high in extrema):
                raise RuntimeError(f"{name} capture is blank or has the wrong dimensions")
            image.save(output / f"{name}.png")
    finally:
        window.closed = True
        window.root.destroy()
        root.destroy()
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="directory for PNG captures")
    arguments = parser.parse_args()
    print(capture(arguments.output))
