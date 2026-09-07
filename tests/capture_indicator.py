"""Native Windows pill QA; saves only pill screenshots under artifacts.

Run with .venv/Scripts/python.exe tests/capture_indicator.py.
No microphone, personal settings, clipboard, or existing app is touched.
"""
import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import queue
import sys
import threading
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PIL import ImageGrab
from utterleaf.indicator import _run_win32


def main():
    user32, gdi32 = ctypes.windll.user32, ctypes.windll.gdi32
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
    user32.GetWindowRgn.argtypes = (wintypes.HWND, wintypes.HRGN)
    gdi32.CreateRectRgn.argtypes = (ctypes.c_int,) * 4
    gdi32.CreateRectRgn.restype = wintypes.HRGN
    gdi32.GetRgnBox.argtypes = (wintypes.HRGN, ctypes.POINTER(wintypes.RECT))
    gdi32.PtInRegion.argtypes = (wintypes.HRGN, ctypes.c_int, ctypes.c_int)
    gdi32.DeleteObject.argtypes = (wintypes.HANDLE,)
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
        output = Path(__file__).resolve().parents[1] / "artifacts" / "indicator-qa"
        output.mkdir(parents=True, exist_ok=True)
        for name, kind, caption, expected in (
            ("compact", "listening", "", (248, 48)),
            ("expanded", "listening", "A longer recording should keep every corner rounded and this caption readable.", (480, 86)),
            ("long-listening", "listening", "A longer recording should keep every corner rounded and this caption readable.", (480, 86)),
            ("compact-again", "transcribing", "", (248, 48)),
        ):
            events.put((kind, caption))
            time.sleep(2 if name == "long-listening" else .3)
            rect = wintypes.RECT()
            assert user32.GetWindowRect(hwnd, ctypes.byref(rect))
            w, h = rect.right - rect.left, rect.bottom - rect.top
            assert (w, h) == expected, (name, w, h)
            region = gdi32.CreateRectRgn(0, 0, 0, 0)
            try:
                assert user32.GetWindowRgn(hwnd, region) > 0
                bounds = wintypes.RECT()
                gdi32.GetRgnBox(region, ctypes.byref(bounds))
                assert (bounds.left, bounds.top, bounds.right, bounds.bottom) == (0, 0, w, h)
                for x, y in ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)):
                    assert not gdi32.PtInRegion(region, x, y), (name, "square corner", x, y)
                for x, y in ((0, h // 2), (w - 1, h // 2), (w // 2, 0), (w // 2, h - 1)):
                    assert gdi32.PtInRegion(region, x, y), (name, "clipped edge", x, y)
            finally:
                gdi32.DeleteObject(region)
            ImageGrab.grab(bbox=(rect.left, rect.top, rect.right, rect.bottom)).save(output / f"{name}.png")
            print(f"{name}: {w}x{h}, all four corners and edges verified")
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
    for cycle in range(3):
        print(f"Indicator lifecycle {cycle + 1}")
        main()