"""On-screen status pill. Windows is in-process; elsewhere Tk owns a child process."""

from __future__ import annotations

import logging
import math
import queue
import subprocess
import sys
import threading

from utterleaf.host import pill_kind, ui_font

log = logging.getLogger("utterleaf")

LOOK = {
    "loading": ("Loading", "#142422", "#2DD4BF"),
    "listening": ("Listening", "#2B1618", "#E46962"),
    "transcribing": ("Transcribing", "#2A2416", "#E8C468"),
    "pasted": ("Pasted", "#14291C", "#6BCB8B"),
    "clipboard": ("On clipboard", "#1C1B1F", "#E8C468"),
    "missed": ("Didn't hear", "#1C1B1F", "#938F99"),
    "too_short": ("Too short", "#1C1B1F", "#938F99"),
    # Failures. Red accent, and the caption carries the detail.
    "no_mic": ("Microphone unavailable", "#2B1618", "#E46962"),
    "capture_error": ("Recording interrupted", "#2B1618", "#E46962"),
    "engine": ("Engine not ready", "#2B1618", "#E46962"),
    "transcribe": ("Couldn't transcribe", "#2B1618", "#E46962"),
    "no_paste": ("Couldn't paste", "#2B1618", "#E46962"),
}

ERROR_KINDS = frozenset({"no_mic", "capture_error", "engine", "transcribe", "no_paste"})

# Queue items: ("kind", caption) from set(), or "quit" from close().
PillItem = str | tuple[str, str]


def recording_caption(remaining: float, draft: str = "") -> str:
    seconds = max(0, math.ceil(remaining))
    clock = f"{seconds // 60}:{seconds % 60:02d} left"
    if seconds <= 10:
        clock += " · Finishing soon"
    return f"{clock} · {draft}" if draft else clock


def appearance(kind: str) -> tuple[str, str, str] | None:
    if kind == "hide" or kind not in LOOK:
        return None
    return LOOK[kind]


def pill_backend():
    """In-process renderer, or None when the pill is a child process (Tk main thread)."""
    if pill_kind() == "win32":
        return _run_win32
    return None


def encode_pill(kind: str, caption: str = "") -> str:
    caption = (caption or "").replace("\n", " ").replace("\t", " ")
    return f"{kind}\t{caption}\n"


def decode_pill(line: str) -> PillItem:
    raw = line.rstrip("\n\r")
    if raw == "quit":
        return "quit"
    if "\t" in raw:
        kind, caption = raw.split("\t", 1)
        return kind, caption
    return raw, ""


def spawn_pill_process():
    """Child whose main thread owns Tk. Same trick as --settings."""
    kwargs: dict = {
        "stdin": subprocess.PIPE,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "text": True,
        "encoding": "utf-8",
    }
    if sys.platform == "win32":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    exe = sys.executable
    if getattr(sys, "frozen", False):
        return subprocess.Popen([exe, "--pill"], **kwargs)
    return subprocess.Popen([exe, "-m", "utterleaf", "--pill"], **kwargs)


def run_pill() -> int:
    """`--pill` entry: Tk on this process's main thread, commands on stdin."""
    q: queue.Queue[PillItem] = queue.Queue()

    def reader() -> None:
        try:
            for line in sys.stdin:
                item = decode_pill(line)
                q.put(item)
                if item == "quit":
                    return
        except Exception:
            log.debug("Pill stdin closed", exc_info=True)
        q.put("quit")

    threading.Thread(target=reader, daemon=True, name="utterleaf-pill-stdin").start()
    _run_tk(q)
    return 0


def _guarded(target):
    """A dead pill must never take the app with it."""

    def run(q: queue.Queue[PillItem]) -> None:
        try:
            target(q)
        except Exception:
            log.exception("Indicator stopped; continuing without the pill")

    return run


class Indicator:
    def __init__(self, enabled: bool = True) -> None:
        self.enabled = enabled
        self._q: queue.Queue[PillItem] = queue.Queue()
        self._thread: threading.Thread | None = None
        self._proc: subprocess.Popen | None = None
        self._write_lock = threading.Lock()
        self._lifecycle_lock = threading.RLock()

    def start(self) -> None:
        with self._lifecycle_lock:
            if not self.enabled:
                return
            if self._thread is not None:
                if self._thread.is_alive():
                    return
                self._thread = None
            if self._proc is not None:
                if self._proc.poll() is None:
                    return
                self._proc = None
            target = pill_backend()
            if target is not None:
                # A previous worker may have stopped before consuming its queue.
                self._q = queue.Queue()
                self._thread = threading.Thread(
                    target=_guarded(target), args=(self._q,), name="utterleaf-indicator", daemon=True
                )
                self._thread.start()
                return
            try:
                self._proc = spawn_pill_process()
            except Exception:
                log.exception("Could not start the status pill")
                self.enabled = False

    def set(self, kind: str, caption: str = "") -> None:
        if not self.enabled:
            return
        if self._proc is not None:
            self._write(encode_pill(kind, caption))
            return
        self._q.put((kind, caption or ""))

    def _write(self, payload: str) -> None:
        proc = self._proc
        if proc is None or proc.stdin is None:
            return
        try:
            with self._write_lock:
                proc.stdin.write(payload)
                proc.stdin.flush()
        except Exception:
            log.debug("Pill process gone", exc_info=True)
            self.enabled = False

    def close(self) -> None:
        with self._lifecycle_lock:
            self.enabled = False
            proc = self._proc
            if proc is not None:
                self._write("quit\n")
                try:
                    if proc.stdin is not None:
                        proc.stdin.close()
                except OSError:
                    pass
                try:
                    proc.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    # Only terminate the child that this Indicator created.
                    proc.terminate()
                    try:
                        proc.wait(timeout=1)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.wait(timeout=1)
                self._proc = None
            worker = self._thread
            if worker is not None:
                self._q.put("quit")
                if worker is not threading.current_thread():
                    worker.join(timeout=2)
                if not worker.is_alive():
                    self._thread = None
                else:
                    # Retain the handle so start() cannot overlap this worker.
                    log.warning("Indicator is still shutting down")

def _hex_bgr(value: str) -> int:
    raw = value.lstrip("#")
    r, g, b = int(raw[0:2], 16), int(raw[2:4], 16), int(raw[4:6], 16)
    return r | (g << 8) | (b << 16)


def _run_win32(q: queue.Queue[PillItem]) -> None:
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    gdi32 = ctypes.windll.gdi32
    kernel32 = ctypes.windll.kernel32
    # wparam/lparam are pointer-sized; the c_int default truncates them and the callback raises.
    user32.DefWindowProcW.argtypes = (
        wintypes.HWND,
        wintypes.UINT,
        wintypes.WPARAM,
        wintypes.LPARAM,
    )
    user32.DefWindowProcW.restype = ctypes.c_ssize_t

    # Tk may have already selected process DPI awareness. A thread context keeps
    # the window size, paint coordinates and clipping region in physical pixels.
    user32.SetThreadDpiAwarenessContext.argtypes = (ctypes.c_void_p,)
    user32.SetThreadDpiAwarenessContext.restype = ctypes.c_void_p
    user32.SetThreadDpiAwarenessContext(ctypes.c_void_p(-4))

    # Native handles are pointer-sized; ctypes defaults would truncate on x64.
    def bind(dll, name, result, *args):
        function = getattr(dll, name)
        function.restype = result
        function.argtypes = args

    H, I, U = wintypes.HANDLE, ctypes.c_int, wintypes.UINT
    bind(gdi32, "CreateRoundRectRgn", H, I, I, I, I, I, I)
    bind(gdi32, "CreateCompatibleDC", H, H)
    bind(gdi32, "CreateCompatibleBitmap", H, H, I, I)
    bind(gdi32, "SelectObject", H, H, H)
    bind(gdi32, "DeleteObject", I, H)
    bind(gdi32, "DeleteDC", I, H)
    bind(gdi32, "CreateSolidBrush", H, wintypes.DWORD)
    bind(gdi32, "CreateFontW", H, *((I,) * 5 + (wintypes.DWORD,) * 8 + (wintypes.LPCWSTR,)))
    bind(gdi32, "Ellipse", I, H, I, I, I, I)
    bind(gdi32, "BitBlt", I, H, I, I, I, I, H, I, I, wintypes.DWORD)
    bind(gdi32, "SetBkMode", I, H, I)
    bind(gdi32, "SetTextColor", wintypes.DWORD, H, wintypes.DWORD)
    bind(user32, "CreateWindowExW", H, wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR,
         wintypes.DWORD, I, I, I, I, H, H, H, ctypes.c_void_p)
    bind(user32, "SetWindowRgn", I, H, H, I)
    bind(user32, "SetWindowPos", I, H, H, I, I, I, I, U)
    bind(user32, "SetLayeredWindowAttributes", I, H, wintypes.DWORD, wintypes.BYTE, wintypes.DWORD)
    bind(user32, "InvalidateRect", I, H, ctypes.c_void_p, I)
    bind(user32, "ShowWindow", I, H, I)
    bind(user32, "DestroyWindow", I, H)
    bind(user32, "IsWindow", I, H)
    bind(user32, "UnregisterClassW", I, wintypes.LPCWSTR, H)
    bind(user32, "SetTimer", ctypes.c_size_t, H, ctypes.c_size_t, U, ctypes.c_void_p)
    bind(kernel32, "GetModuleHandleW", H, wintypes.LPCWSTR)

    WS_POPUP = 0x80000000
    WS_EX_TOPMOST = 0x00000008
    WS_EX_TRANSPARENT = 0x00000020
    WS_EX_TOOLWINDOW = 0x00000080
    WS_EX_NOACTIVATE = 0x08000000
    WS_EX_LAYERED = 0x00080000
    LWA_ALPHA = 0x00000002
    SW_SHOWNOACTIVATE = 4
    WM_PAINT = 0x000F
    WM_ERASEBKGND = 0x0014
    WM_TIMER = 0x0113
    WM_DESTROY = 0x0002
    WM_NCHITTEST = 0x0084
    HTTRANSPARENT = -1
    SPI_GETWORKAREA = 0x0030
    SWP_NOACTIVATE = 0x0010
    HWND_TOPMOST = -1
    SRCCOPY = 0x00CC0020
    TRANSPARENT = 1
    DT_SINGLELINE = 0x0020
    DT_VCENTER = 0x0004
    DT_WORDBREAK = 0x0010
    DT_NOPREFIX = 0x0800
    DT_END_ELLIPSIS = 0x00008000
    DT_WORD_ELLIPSIS = 0x00040000

    compact = (248, 48)
    expanded = (480, 86)
    width, height = compact
    state = {
        "kind": "hide",
        "label": "",
        "caption": "",
        "fill": 0x1A1614,
        "accent": 0x4D4DFF,
        "width": compact[0],
        "height": compact[1],
    }

    WNDPROC = ctypes.WINFUNCTYPE(
        ctypes.c_ssize_t, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM
    )

    class RECT(ctypes.Structure):
        _fields_ = (
            ("left", ctypes.c_long),
            ("top", ctypes.c_long),
            ("right", ctypes.c_long),
            ("bottom", ctypes.c_long),
        )

    class PAINTSTRUCT(ctypes.Structure):
        _fields_ = (
            ("hdc", wintypes.HDC),
            ("fErase", wintypes.BOOL),
            ("rcPaint", RECT),
            ("fRestore", wintypes.BOOL),
            ("fIncUpdate", wintypes.BOOL),
            ("rgbReserved", wintypes.BYTE * 32),
        )

    class WNDCLASSW(ctypes.Structure):
        _fields_ = (
            ("style", wintypes.UINT),
            ("lpfnWndProc", WNDPROC),
            ("cbClsExtra", ctypes.c_int),
            ("cbWndExtra", ctypes.c_int),
            ("hInstance", wintypes.HINSTANCE),
            ("hIcon", wintypes.HICON),
            ("hCursor", wintypes.HCURSOR),
            ("hbrBackground", wintypes.HBRUSH),
            ("lpszMenuName", wintypes.LPCWSTR),
            ("lpszClassName", wintypes.LPCWSTR),
        )

    bind(user32, "BeginPaint", H, H, ctypes.POINTER(PAINTSTRUCT))
    bind(user32, "EndPaint", I, H, ctypes.POINTER(PAINTSTRUCT))
    bind(user32, "DrawTextW", I, H, wintypes.LPCWSTR, I, ctypes.POINTER(RECT), U)
    bind(user32, "FillRect", I, H, ctypes.POINTER(RECT), H)
    bind(user32, "RegisterClassW", wintypes.ATOM, ctypes.POINTER(WNDCLASSW))

    def position(w: int, h: int) -> tuple[int, int]:
        area = RECT()
        user32.SystemParametersInfoW(SPI_GETWORKAREA, 0, ctypes.byref(area), 0)
        x = area.left + max(0, (area.right - area.left - w) // 2)
        y = area.bottom - h - 18
        return x, y

    def clip_round(w: int, h: int) -> None:
        """Round all four corners; expanded captions need room beside their text."""
        diameter = min(h, 32) if state["caption"] else h
        rgn = gdi32.CreateRoundRectRgn(0, 0, w + 1, h + 1, diameter, diameter)
        if not rgn:
            return
        # SetWindowRgn takes ownership of the region on success.
        if not user32.SetWindowRgn(hwnd, rgn, True):
            gdi32.DeleteObject(rgn)

    def apply_kind(kind: str, caption: str = "") -> None:
        look = appearance(kind)
        if look is None:
            if state["kind"] == "hide":
                return
            state["kind"] = "hide"
            state["caption"] = ""
            user32.SetLayeredWindowAttributes(hwnd, 0, 0, LWA_ALPHA)
            return
        label, fill, accent = look
        caption = caption.strip()
        # Live preview repeats the same draft; unchanged pills must not repaint.
        if state["kind"] == kind and state["caption"] == caption:
            return
        state["kind"] = kind
        state["label"] = label
        state["caption"] = caption
        state["fill"] = _hex_bgr(fill)
        state["accent"] = _hex_bgr(accent)
        w, h = expanded if state["caption"] else compact
        state["width"], state["height"] = w, h
        x, y = position(w, h)
        user32.SetWindowPos(hwnd, HWND_TOPMOST, x, y, w, h, SWP_NOACTIVATE)
        clip_round(w, h)
        user32.InvalidateRect(hwnd, None, False)
        user32.SetLayeredWindowAttributes(hwnd, 0, 235, LWA_ALPHA)

    def wndproc(hwnd, msg, wparam, lparam):
        if msg == WM_NCHITTEST:
            return HTTRANSPARENT
        if msg == WM_ERASEBKGND:
            return 1
        if msg == WM_TIMER:
            item = None
            try:
                while True:
                    item = q.get_nowait()
                    if item == "quit":
                        user32.DestroyWindow(hwnd)
                        return 0
            except queue.Empty:
                pass
            if item is not None:
                if isinstance(item, tuple):
                    apply_kind(item[0], item[1] if len(item) > 1 else "")
                else:
                    apply_kind(str(item))
            return 0
        if msg == WM_PAINT:
            ps = PAINTSTRUCT()
            hdc = user32.BeginPaint(hwnd, ctypes.byref(ps))
            w, h = int(state["width"]), int(state["height"])
            # Paint off-screen and blit once; staged GDI passes flash.
            mem = gdi32.CreateCompatibleDC(hdc)
            bmp = gdi32.CreateCompatibleBitmap(hdc, w, h)
            old_bmp = gdi32.SelectObject(mem, bmp)
            fill = gdi32.CreateSolidBrush(state["fill"])
            # The window region alone defines the rounded outline. Fill every
            # bitmap pixel so a second, slightly different RoundRect cannot
            # expose uninitialized corner pixels after a resize.
            surface = RECT(0, 0, w, h)
            user32.FillRect(mem, ctypes.byref(surface), fill)
            gdi32.DeleteObject(fill)
            if state["kind"] != "hide":
                cy = 16 if state["caption"] else (h - 16) // 2
                dot = gdi32.CreateSolidBrush(state["accent"])
                old = gdi32.SelectObject(mem, dot)
                gdi32.Ellipse(mem, 18, cy, 34, cy + 16)
                gdi32.SelectObject(mem, old)
                gdi32.DeleteObject(dot)
                gdi32.SetBkMode(mem, TRANSPARENT)
                gdi32.SetTextColor(mem, 0x00E5E1E6)
                font = gdi32.CreateFontW(
                    18, 0, 0, 0, 600, 0, 0, 0, 1, 0, 0, 5, 0, "Segoe UI"
                )
                prev = gdi32.SelectObject(mem, font)
                label_box = RECT(44, cy - 4, w - 14, cy + 20)
                user32.DrawTextW(
                    mem,
                    state["label"],
                    -1,
                    ctypes.byref(label_box),
                    DT_SINGLELINE | DT_VCENTER | DT_END_ELLIPSIS | DT_NOPREFIX,
                )
                if state["caption"]:
                    gdi32.SetTextColor(mem, 0x00D0C4CA)
                    small = gdi32.CreateFontW(
                        15, 0, 0, 0, 400, 0, 0, 0, 1, 0, 0, 5, 0, "Segoe UI"
                    )
                    gdi32.SelectObject(mem, small)
                    box = RECT(18, 44, w - 20, h - 12)
                    user32.DrawTextW(
                        mem,
                        state["caption"][:160],
                        -1,
                        ctypes.byref(box),
                        DT_WORDBREAK | DT_WORD_ELLIPSIS | DT_NOPREFIX,
                    )
                    gdi32.SelectObject(mem, font)
                    gdi32.DeleteObject(small)
                gdi32.SelectObject(mem, prev)
                gdi32.DeleteObject(font)
            gdi32.BitBlt(hdc, 0, 0, w, h, mem, 0, 0, SRCCOPY)
            gdi32.SelectObject(mem, old_bmp)
            gdi32.DeleteObject(bmp)
            gdi32.DeleteDC(mem)
            user32.EndPaint(hwnd, ctypes.byref(ps))
            return 0
        if msg == WM_DESTROY:
            user32.PostQuitMessage(0)
            return 0
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    proc = WNDPROC(wndproc)
    class_name = f"UtterleafIndicator-{threading.get_ident()}"
    wc = WNDCLASSW()
    wc.lpfnWndProc = proc
    wc.hInstance = kernel32.GetModuleHandleW(None)
    wc.hbrBackground = 0  # Dark class-brush erase flashes; WM_ERASEBKGND is a no-op instead.
    wc.lpszClassName = class_name
    if not user32.RegisterClassW(ctypes.byref(wc)):
        log.error("Could not register indicator window class")
        return

    hwnd = None
    try:
        x, y = position(compact[0], compact[1])
        ex = WS_EX_TOPMOST | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE | WS_EX_LAYERED | WS_EX_TRANSPARENT
        hwnd = user32.CreateWindowExW(
            ex,
            class_name,
            "Utterleaf",
            WS_POPUP,
            x,
            y,
            compact[0],
            compact[1],
            None,
            None,
            wc.hInstance,
            None,
        )
        if not hwnd:
            log.warning("Could not create indicator window")
            return
        user32.SetLayeredWindowAttributes(hwnd, 0, 0, LWA_ALPHA)
        clip_round(compact[0], compact[1])
        user32.ShowWindow(hwnd, SW_SHOWNOACTIVATE)
        user32.SetTimer(hwnd, 1, 30, None)
    
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
    finally:
        # Keep proc alive until both the HWND and its class registration are
        # gone. A later settings toggle must never reuse an old callback.
        if hwnd and user32.IsWindow(hwnd):
            user32.DestroyWindow(hwnd)
        if not user32.UnregisterClassW(class_name, wc.hInstance):
            log.error("Could not unregister indicator window class")

def _run_tk(q: queue.Queue[PillItem]) -> None:
    try:
        import tkinter as tk
    except Exception:
        log.warning("No tkinter; on-screen indicator disabled")
        return

    root = tk.Tk()
    root.overrideredirect(True)
    root.attributes("-topmost", True)
    try:
        root.attributes("-alpha", 0.0)
    except tk.TclError:
        pass
    root.configure(bg="#1C1B1F")
    width, height = 196, 44
    canvas = tk.Canvas(root, width=width, height=height, highlightthickness=0, bd=0, bg="#1C1B1F")
    canvas.pack()

    def paint(kind: str, caption: str = "") -> None:
        look = appearance(kind)
        w, h = (460, 84) if caption else (220, 48)
        sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
        canvas.config(width=w, height=h)
        root.geometry(f"{w}x{h}+{(sw - w) // 2}+{sh - h - 72}")
        # Flush the resize synchronously so the window is never narrower
        # than the caption already laid out on the canvas.
        root.update_idletasks()
        canvas.delete("all")
        if look is None:
            try:
                root.attributes("-alpha", 0.0)
            except tk.TclError:
                pass
            return
        label, fill, accent = look
        canvas.create_rectangle(1, 1, w - 2, h - 2, fill=fill, outline=fill)
        canvas.create_oval(16, 16, 30, 30, fill=accent, outline=accent)
        family = ui_font()
        canvas.create_text(42, 23, text=label, fill="#E6E1E5", font=(family, 11, "bold"), anchor="w")
        if caption:
            # A character limit alone does not constrain pixels with a
            # proportional font. Wrap to the canvas and ellipsize excess lines.
            shown = caption.replace("\n", " ")[:160]
            item = canvas.create_text(
                18,
                44,
                text=shown,
                fill="#CAC4D0",
                font=(family, 10),
                anchor="nw",
                width=w - 36,
            )
            while shown and canvas.bbox(item)[3] > h - 8:
                shown = shown[:-1].rstrip()
                canvas.itemconfigure(item, text=shown + "…")
        try:
            root.attributes("-alpha", 0.94)
        except tk.TclError:
            pass

    def poll() -> None:
        item = None
        try:
            while True:
                item = q.get_nowait()
                if item == "quit":
                    root.destroy()
                    return
        except queue.Empty:
            pass
        if item is not None:
            if isinstance(item, tuple):
                paint(item[0], item[1] if len(item) > 1 else "")
            else:
                paint(str(item))
        root.after(40, poll)

    root.deiconify()
    paint("hide")
    root.after(40, poll)
    root.mainloop()
