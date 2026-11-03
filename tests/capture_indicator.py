"""Native Windows pill QA; saves only pill screenshots under artifacts.

Run with .venv/Scripts/python.exe tests/capture_indicator.py --output artifacts/screenshots/NEW-DIRECTORY.
No microphone, personal settings, clipboard, or existing app is touched.
"""
import argparse
import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import queue
import sys
import threading
import time
from typing import NamedTuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PIL import ImageGrab
from utterleaf.audio import microphone_error_hint
from sounddevice import PortAudioError
from utterleaf.indicator import LOOK, _run_win32

ROOT = Path(__file__).resolve().parents[1]


class CaptureCase(NamedTuple):
    name: str
    kind: str
    caption: str
    expected: tuple[int, int]
    dwell_seconds: float = 0.0


# Actual app scenarios. Keep these captions aligned with the call sites in
# Utterleaf._start_recording(), Utterleaf._recording_caption(),
# Utterleaf._stop_recording(), and microphone_error_hint().
APP_SCENARIOS = (
    CaptureCase("app-opening-microphone", "loading", "Getting your microphone ready…", (480, 86)),
    CaptureCase("app-listening-hold", "listening", "Release shortcut to finish · Esc cancels", (480, 86)),
    CaptureCase("app-transcribing", "transcribing", "", (248, 48)),
    CaptureCase(
        "app-microphone-error",
        "no_mic",
        microphone_error_hint(RuntimeError("synthetic baseline failure")),
        (480, 86),
    ),
    CaptureCase("app-model-error", "engine",
                "Open Settings → Speech & privacy to check the model, or Help for diagnostics.", (480, 86)),
    CaptureCase("app-microphone-format", "no_mic",
                microphone_error_hint(PortAudioError("Synthetic unsupported microphone configuration", -9997)),
                (480, 86)),
    CaptureCase("app-text-attention", "no_paste",
                "Use Copy last dictation in the tray menu to recover your text.", (480, 86)),
)

# Renderer-only stress cases. The long caption is deliberately synthetic UI
# stress text, not product copy. The duplicate long-listening frame verifies
# that the expanded region survives a two-second dwell; compact-again verifies
# the expanded-to-compact transition that previously regressed.
_STRESS_CAPTION = "A longer recording should keep every corner rounded and this caption readable."
RENDERER_STRESS_CASES = (
    CaptureCase("renderer-stress-compact-listening", "listening", "", (248, 48)),
    CaptureCase("renderer-stress-expanded-listening", "listening", _STRESS_CAPTION, (480, 86)),
    CaptureCase("renderer-stress-long-listening", "listening", _STRESS_CAPTION, (480, 86), 2.0),
    CaptureCase("renderer-stress-compact-model-error", "engine", "", (248, 48)),
    CaptureCase("renderer-stress-compact-again", "transcribing", "", (248, 48)),
)

CASES = APP_SCENARIOS + RENDERER_STRESS_CASES


def main(*, capture: bool = True, output: Path | None = None):
    output = (output or ROOT / "artifacts/screenshots/desktop-indicator-recovery").resolve()
    if not output.is_relative_to(ROOT / "artifacts"):
        raise ValueError("Capture output must stay inside this checkout's artifacts directory")
    if capture:
        output.mkdir(parents=True, exist_ok=False)
    user32, gdi32, dwmapi = ctypes.windll.user32, ctypes.windll.gdi32, ctypes.windll.dwmapi
    # Reproduce a settings window selecting DPI mode before the indicator starts.
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
    user32.SetThreadDpiAwarenessContext.argtypes = (ctypes.c_void_p,)
    user32.SetThreadDpiAwarenessContext.restype = ctypes.c_void_p
    user32.SetThreadDpiAwarenessContext(ctypes.c_void_p(-4))
    user32.FindWindowExW.argtypes = (wintypes.HWND, wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR)
    user32.FindWindowExW.restype = wintypes.HWND
    user32.GetWindowThreadProcessId.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.DWORD))
    user32.GetClassNameW.argtypes = (wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
    user32.GetClassInfoW.argtypes = (wintypes.HINSTANCE, wintypes.LPCWSTR, ctypes.c_void_p)
    ctypes.windll.kernel32.GetModuleHandleW.restype = wintypes.HMODULE
    class_name = ctypes.create_unicode_buffer(256)
    user32.GetWindowRect.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.RECT))
    user32.SendMessageTimeoutW.argtypes = (
        wintypes.HWND,
        wintypes.UINT,
        wintypes.WPARAM,
        wintypes.LPARAM,
        wintypes.UINT,
        wintypes.UINT,
        ctypes.POINTER(ctypes.c_size_t),
    )
    user32.SendMessageTimeoutW.restype = ctypes.c_ssize_t
    user32.RedrawWindow.argtypes = (wintypes.HWND, ctypes.c_void_p, wintypes.HRGN, wintypes.UINT)
    user32.RedrawWindow.restype = wintypes.BOOL
    dwmapi.DwmFlush.argtypes = ()
    dwmapi.DwmFlush.restype = ctypes.c_long
    user32.GetWindowRgn.argtypes = (wintypes.HWND, wintypes.HRGN)
    gdi32.CreateRectRgn.argtypes = (ctypes.c_int,) * 4
    gdi32.CreateRectRgn.restype = wintypes.HRGN
    gdi32.GetRgnBox.argtypes = (wintypes.HRGN, ctypes.POINTER(wintypes.RECT))
    gdi32.PtInRegion.argtypes = (wintypes.HRGN, ctypes.c_int, ctypes.c_int)
    gdi32.DeleteObject.argtypes = (wintypes.HANDLE,)
    gdi32.CreateCompatibleDC.argtypes = (wintypes.HDC,)
    gdi32.CreateCompatibleDC.restype = wintypes.HDC
    gdi32.CreateFontW.argtypes = (ctypes.c_int,) * 5 + (wintypes.DWORD,) * 8 + (wintypes.LPCWSTR,)
    gdi32.CreateFontW.restype = wintypes.HANDLE
    gdi32.SelectObject.argtypes = (wintypes.HDC, wintypes.HANDLE)
    gdi32.SelectObject.restype = wintypes.HANDLE
    gdi32.GetTextExtentPoint32W.argtypes = (
        wintypes.HDC, wintypes.LPCWSTR, ctypes.c_int, ctypes.POINTER(wintypes.SIZE))
    gdi32.DeleteDC.argtypes = (wintypes.HDC,)
    events = queue.Queue()
    worker = threading.Thread(target=_run_win32, args=(events,), daemon=True)
    worker.start()
    hwnd = None
    try:
        deadline = time.monotonic() + 5
        while not hwnd and time.monotonic() < deadline:
            candidate = None
            while True:
                candidate = user32.FindWindowExW(None, candidate, None, "Utterleaf")
                if not candidate:
                    break
                pid = wintypes.DWORD()
                user32.GetWindowThreadProcessId(candidate, ctypes.byref(pid))
                if pid.value == os.getpid():
                    hwnd = candidate
                    break
            time.sleep(.05)
        assert hwnd, "Indicator did not create its native window"
        assert user32.GetClassNameW(hwnd, class_name, len(class_name))
        def flush_renderer(name: str) -> None:
            # The native renderer normally drains its queue from a 30 ms timer.
            # Dispatch that existing message with a timeout, repaint synchronously,
            # then wait for desktop composition before measuring or capturing.
            result = ctypes.c_size_t()
            assert user32.SendMessageTimeoutW(
                hwnd,
                0x0113,  # WM_TIMER
                1,
                0,
                0x0001 | 0x0002,  # SMTO_BLOCK | SMTO_ABORTIFHUNG
                1000,
                ctypes.byref(result),
            ), (name, "renderer did not process its queue")
            assert user32.RedrawWindow(
                hwnd,
                None,
                None,
                0x0001 | 0x0100,  # RDW_INVALIDATE | RDW_UPDATENOW
            ), (name, "renderer did not repaint")
            assert dwmapi.DwmFlush() == 0, (name, "desktop composition did not flush")

        for case in CASES:
            events.put((case.kind, case.caption))
            flush_renderer(case.name)
            if case.dwell_seconds:
                deadline = time.monotonic() + case.dwell_seconds
                while time.monotonic() < deadline:
                    time.sleep(min(.05, max(0, deadline - time.monotonic())))
                flush_renderer(case.name)
            rect = wintypes.RECT()
            assert user32.GetWindowRect(hwnd, ctypes.byref(rect))
            w, h = rect.right - rect.left, rect.bottom - rect.top
            assert (w, h) == case.expected, (case.name, w, h)
            # Match the actual renderer's headline font and box, not only the
            # outer window. An ellipsized error title must fail this check.
            dc = gdi32.CreateCompatibleDC(None)
            font = gdi32.CreateFontW(18, 0, 0, 0, 600, 0, 0, 0, 1, 0, 0, 5, 0, "Segoe UI")
            previous = gdi32.SelectObject(dc, font)
            try:
                size = wintypes.SIZE()
                label = LOOK[case.kind][0]
                assert gdi32.GetTextExtentPoint32W(dc, label, len(label), ctypes.byref(size))
                assert size.cx <= w - 58, (case.name, "headline clipped", size.cx, w - 58)
                assert size.cy <= 24, (case.name, "headline too tall", size.cy)
            finally:
                gdi32.SelectObject(dc, previous)
                gdi32.DeleteObject(font)
                gdi32.DeleteDC(dc)
            region = gdi32.CreateRectRgn(0, 0, 0, 0)
            try:
                assert user32.GetWindowRgn(hwnd, region) > 0
                bounds = wintypes.RECT()
                gdi32.GetRgnBox(region, ctypes.byref(bounds))
                assert (bounds.left, bounds.top, bounds.right, bounds.bottom) == (0, 0, w, h)
                for x, y in ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)):
                    assert not gdi32.PtInRegion(region, x, y), (case.name, "square corner", x, y)
                for x, y in ((0, h // 2), (w - 1, h // 2), (w // 2, 0), (w // 2, h - 1)):
                    assert gdi32.PtInRegion(region, x, y), (case.name, "clipped edge", x, y)
            finally:
                gdi32.DeleteObject(region)
            if capture:
                ImageGrab.grab(bbox=(rect.left, rect.top, rect.right, rect.bottom)).save(
                    output / f"indicator-{case.name}.png"
                )
            print(f"{case.name}: {w}x{h}, headline {size.cx}px fits; all four corners and edges verified")
    finally:
        events.put("quit")
        worker.join(timeout=5)
        assert not worker.is_alive(), "Indicator did not shut down"
        if class_name.value:
            info = ctypes.create_string_buffer(1024)
            instance = ctypes.windll.kernel32.GetModuleHandleW(None)
            assert not user32.GetClassInfoW(instance, class_name.value, info), "Window class retained a stale callback"
            print("Window class unregistered after shutdown")


if __name__ == "__main__":
    if sys.platform != "win32":
        raise SystemExit("The native pill baseline is Windows-only; use the Tk indicator tests on other platforms.")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/screenshots/desktop-indicator-recovery")
    args = parser.parse_args()
    for cycle in range(3):
        print(f"Indicator lifecycle {cycle + 1}")
        main(capture=cycle == 0, output=args.output)
