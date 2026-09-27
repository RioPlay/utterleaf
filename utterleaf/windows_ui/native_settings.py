"""Isolated standard-Win32 Settings accessibility proof.

The production application does not dispatch to this module. The proof owns no
configuration, audio, model, clipboard, network, IPC, or telemetry behavior; it
only returns a local draft when its caller explicitly runs it.

The active Windows accessibility-shell plan records independent native
``CUIAutomation`` evidence from a frozen, version-6 common-controls probe. That
evidence establishes that the standard controls used here can expose names,
control types, focusability, and Value, ExpandCollapse, Toggle, and Invoke
patterns. It does not make this unshipped, single-page experiment a release
accessibility claim.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
from dataclasses import dataclass
import sys
from typing import Final


WINDOW_TITLE: Final = "Utterleaf Settings — native accessibility proof"


@dataclass(frozen=True)
class NativeControlSpec:
    """Stable metadata for one native child control."""

    key: str
    control_id: int
    class_name: str
    text: str
    accessible_name: str
    control_type: str
    tab_stop: bool = False


CONTROL_SPECS: Final = (
    NativeControlSpec(
        "navigation_heading", 100, "Static", "Settings sections", "Settings sections", "Text"
    ),
    NativeControlSpec(
        "dictation_navigation", 101, "Button", "&Dictation", "Dictation", "Button", True
    ),
    NativeControlSpec("page_heading", 110, "Static", "Dictation", "Dictation", "Text"),
    NativeControlSpec(
        "page_description",
        111,
        "Static",
        "Choose how a take starts and which local input it uses.",
        "Choose how a take starts and which local input it uses.",
        "Text",
    ),
    NativeControlSpec(
        "hotkey_label", 120, "Static", "&Keyboard shortcut:", "Keyboard shortcut", "Text"
    ),
    NativeControlSpec("hotkey", 121, "Edit", "", "Keyboard shortcut", "Edit", True),
    NativeControlSpec(
        "microphone_label", 130, "Static", "&Input device:", "Input device", "Text"
    ),
    NativeControlSpec(
        "microphone", 131, "ComboBox", "", "Input device", "ComboBox", True
    ),
    NativeControlSpec(
        "stop_after_speech",
        140,
        "Button",
        "Stop after speech and a pause",
        "Stop after speech and a pause",
        "CheckBox",
        True,
    ),
    NativeControlSpec(
        "privacy_note",
        150,
        "Static",
        "This proof does not open the microphone or change saved settings.",
        "This proof does not open the microphone or change saved settings.",
        "Text",
    ),
    NativeControlSpec(
        "reset", 900, "Button", "&Reset to defaults", "Reset to defaults", "Button", True
    ),
    NativeControlSpec("cancel", 901, "Button", "Cancel", "Cancel", "Button", True),
    NativeControlSpec("save", 902, "Button", "&Save", "Save", "Button", True),
)


@dataclass(frozen=True)
class NativeSettingsDraft:
    """The deliberately small, local-only state represented by the proof."""

    hotkey: str = "Ctrl+Win"
    microphone: str = "System default"
    stop_after_speech: bool = False


@dataclass(frozen=True)
class NativeSettingsResult:
    """Outcome returned to an explicit caller; this module never persists it."""

    action: str
    draft: NativeSettingsDraft


_SPEC_BY_KEY: Final = {spec.key: spec for spec in CONTROL_SPECS}

WS_OVERLAPPEDWINDOW = 0x00CF0000
WS_CHILD = 0x40000000
WS_VISIBLE = 0x10000000
WS_TABSTOP = 0x00010000
WS_GROUP = 0x00020000
WS_BORDER = 0x00800000
WS_VSCROLL = 0x00200000
BS_DEFPUSHBUTTON = 0x00000001
BS_AUTOCHECKBOX = 0x00000003
ES_AUTOHSCROLL = 0x00000080
CBS_DROPDOWNLIST = 0x00000003
WM_DESTROY = 0x0002
WM_SIZE = 0x0005
WM_CLOSE = 0x0010
WM_COMMAND = 0x0111
WM_SETFONT = 0x0030
WM_NCDESTROY = 0x0082
BM_GETCHECK = 0x00F0
BM_SETCHECK = 0x00F1
BST_CHECKED = 1
CB_ADDSTRING = 0x0143
CB_GETCURSEL = 0x0147
CB_SETCURSEL = 0x014E
BN_CLICKED = 0
SW_SHOW = 5
CW_USEDEFAULT = -2147483648
DEFAULT_GUI_FONT = 17
COLOR_WINDOW = 5
ERROR_CLASS_ALREADY_EXISTS = 1410

_WINDOW_CLASS: Final = "UtterleafNativeSettingsShellV1"
_WINDOWS: dict[int, "NativeSettingsShell"] = {}
_CLASS_REGISTERED = False


if sys.platform == "win32":
    LRESULT = ctypes.c_ssize_t
    WNDPROC = ctypes.WINFUNCTYPE(
        LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM
    )

    class WNDCLASSEXW(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.UINT),
            ("style", wintypes.UINT),
            ("lpfnWndProc", WNDPROC),
            ("cbClsExtra", ctypes.c_int),
            ("cbWndExtra", ctypes.c_int),
            ("hInstance", wintypes.HINSTANCE),
            ("hIcon", wintypes.HICON),
            ("hCursor", wintypes.HANDLE),
            ("hbrBackground", wintypes.HBRUSH),
            ("lpszMenuName", wintypes.LPCWSTR),
            ("lpszClassName", wintypes.LPCWSTR),
            ("hIconSm", wintypes.HICON),
        ]

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)

    user32.DefWindowProcW.argtypes = (
        wintypes.HWND,
        wintypes.UINT,
        wintypes.WPARAM,
        wintypes.LPARAM,
    )
    user32.DefWindowProcW.restype = LRESULT
    user32.RegisterClassExW.argtypes = (ctypes.POINTER(WNDCLASSEXW),)
    user32.RegisterClassExW.restype = wintypes.ATOM
    user32.CreateWindowExW.argtypes = (
        wintypes.DWORD,
        wintypes.LPCWSTR,
        wintypes.LPCWSTR,
        wintypes.DWORD,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        wintypes.HWND,
        wintypes.HMENU,
        wintypes.HINSTANCE,
        wintypes.LPVOID,
    )
    user32.CreateWindowExW.restype = wintypes.HWND
    user32.DestroyWindow.argtypes = (wintypes.HWND,)
    user32.DestroyWindow.restype = wintypes.BOOL
    user32.IsWindow.argtypes = (wintypes.HWND,)
    user32.IsWindow.restype = wintypes.BOOL
    user32.ShowWindow.argtypes = (wintypes.HWND, ctypes.c_int)
    user32.UpdateWindow.argtypes = (wintypes.HWND,)
    user32.GetClientRect.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.RECT))
    user32.GetClientRect.restype = wintypes.BOOL
    user32.MoveWindow.argtypes = (
        wintypes.HWND,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        wintypes.BOOL,
    )
    user32.SendMessageW.argtypes = (
        wintypes.HWND,
        wintypes.UINT,
        wintypes.WPARAM,
        wintypes.LPARAM,
    )
    user32.SendMessageW.restype = LRESULT
    user32.SetWindowTextW.argtypes = (wintypes.HWND, wintypes.LPCWSTR)
    user32.SetWindowTextW.restype = wintypes.BOOL
    user32.GetWindowTextLengthW.argtypes = (wintypes.HWND,)
    user32.GetWindowTextLengthW.restype = ctypes.c_int
    user32.GetWindowTextW.argtypes = (wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
    user32.GetWindowTextW.restype = ctypes.c_int
    user32.SetFocus.argtypes = (wintypes.HWND,)
    user32.SetFocus.restype = wintypes.HWND
    user32.GetMessageW.argtypes = (
        ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT
    )
    user32.GetMessageW.restype = ctypes.c_int
    user32.IsDialogMessageW.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.MSG))
    user32.IsDialogMessageW.restype = wintypes.BOOL
    user32.TranslateMessage.argtypes = (ctypes.POINTER(wintypes.MSG),)
    user32.DispatchMessageW.argtypes = (ctypes.POINTER(wintypes.MSG),)
    user32.PostQuitMessage.argtypes = (ctypes.c_int,)
    user32.LoadCursorW.argtypes = (wintypes.HINSTANCE, wintypes.LPCWSTR)
    user32.LoadCursorW.restype = wintypes.HANDLE
    kernel32.GetModuleHandleW.argtypes = (wintypes.LPCWSTR,)
    kernel32.GetModuleHandleW.restype = wintypes.HMODULE
    kernel32.GetCurrentThreadId.restype = wintypes.DWORD
    gdi32.GetStockObject.argtypes = (ctypes.c_int,)
    gdi32.GetStockObject.restype = wintypes.HGDIOBJ

    @WNDPROC
    def _window_proc(hwnd, message, wparam, lparam):
        shell = _WINDOWS.get(int(hwnd))
        if shell is not None:
            return shell._handle_message(message, wparam, lparam)
        return user32.DefWindowProcW(hwnd, message, wparam, lparam)


def _require_windows() -> None:
    if sys.platform != "win32":
        raise OSError("The native Settings proof is available only on Windows.")


def _register_window_class() -> None:
    global _CLASS_REGISTERED
    _require_windows()
    if _CLASS_REGISTERED:
        return
    instance = kernel32.GetModuleHandleW(None)
    window_class = WNDCLASSEXW()
    window_class.cbSize = ctypes.sizeof(WNDCLASSEXW)
    window_class.style = 0x0001 | 0x0002
    window_class.lpfnWndProc = _window_proc
    window_class.hInstance = instance
    window_class.hCursor = user32.LoadCursorW(
        None, ctypes.cast(32512, wintypes.LPCWSTR)
    )
    window_class.hbrBackground = ctypes.cast(COLOR_WINDOW + 1, wintypes.HBRUSH)
    window_class.lpszClassName = _WINDOW_CLASS
    if not user32.RegisterClassExW(ctypes.byref(window_class)):
        error = ctypes.get_last_error()
        if error != ERROR_CLASS_ALREADY_EXISTS:
            raise ctypes.WinError(error)
    _CLASS_REGISTERED = True


class NativeSettingsShell:
    """One thread-owned, inert native Settings window."""

    def __init__(
        self,
        draft: NativeSettingsDraft | None = None,
        microphones: tuple[str, ...] | list[str] | None = None,
        *,
        visible: bool = True,
    ) -> None:
        _require_windows()
        _register_window_class()
        self._original = draft or NativeSettingsDraft()
        supplied = tuple(
            str(item).strip()
            for item in (microphones or ("System default",))
            if str(item).strip()
        )
        self._microphones = supplied or ("System default",)
        if self._original.microphone not in self._microphones:
            self._microphones = (self._original.microphone, *self._microphones)
        self._owner_thread_id = int(kernel32.GetCurrentThreadId())
        self._controls: dict[str, int] = {}
        self._result: NativeSettingsResult | None = None
        self._running = False

        instance = kernel32.GetModuleHandleW(None)
        hwnd = user32.CreateWindowExW(
            0,
            _WINDOW_CLASS,
            WINDOW_TITLE,
            WS_OVERLAPPEDWINDOW,
            CW_USEDEFAULT,
            CW_USEDEFAULT,
            780,
            520,
            None,
            None,
            instance,
            None,
        )
        if not hwnd:
            raise ctypes.WinError(ctypes.get_last_error())
        self._hwnd = int(hwnd)
        _WINDOWS[self._hwnd] = self
        try:
            self._create_controls(instance)
            self._layout()
            self.write_draft(self._original)
            if visible:
                user32.ShowWindow(self._hwnd, SW_SHOW)
                user32.UpdateWindow(self._hwnd)
                user32.SetFocus(self._controls["dictation_navigation"])
        except BaseException:
            self.destroy()
            raise

    @property
    def hwnd(self) -> int:
        return self._hwnd

    @property
    def result(self) -> NativeSettingsResult | None:
        return self._result

    def control_handle(self, key: str) -> int:
        """Return a child HWND for focused audits and tests."""

        return self._controls[key]

    def _assert_owner_thread(self) -> None:
        if int(kernel32.GetCurrentThreadId()) != self._owner_thread_id:
            raise RuntimeError("Native Settings windows must stay on their creating thread.")

    def _create_controls(self, instance: int) -> None:
        for spec in CONTROL_SPECS:
            style = WS_CHILD | WS_VISIBLE
            if spec.tab_stop:
                style |= WS_TABSTOP
            if spec.key == "dictation_navigation":
                style |= WS_GROUP
            elif spec.key == "hotkey":
                style |= WS_BORDER | ES_AUTOHSCROLL | WS_GROUP
            elif spec.key == "microphone":
                style |= CBS_DROPDOWNLIST | WS_VSCROLL | WS_GROUP
            elif spec.key == "stop_after_speech":
                style |= BS_AUTOCHECKBOX | WS_GROUP
            elif spec.key == "save":
                style |= BS_DEFPUSHBUTTON

            child = user32.CreateWindowExW(
                0,
                spec.class_name,
                spec.text,
                style,
                0,
                0,
                10,
                10,
                self._hwnd,
                ctypes.cast(spec.control_id, wintypes.HMENU),
                instance,
                None,
            )
            if not child:
                raise ctypes.WinError(ctypes.get_last_error())
            self._controls[spec.key] = int(child)

        font = gdi32.GetStockObject(DEFAULT_GUI_FONT)
        for child in self._controls.values():
            user32.SendMessageW(child, WM_SETFONT, font, 1)
        for microphone in self._microphones:
            value = ctypes.c_wchar_p(microphone)
            user32.SendMessageW(
                self._controls["microphone"],
                CB_ADDSTRING,
                0,
                ctypes.cast(value, ctypes.c_void_p).value,
            )

    def _move(self, key: str, x: int, y: int, width: int, height: int) -> None:
        user32.MoveWindow(self._controls[key], x, y, width, height, True)

    def _layout(self) -> None:
        if not self._hwnd:
            return
        client = wintypes.RECT()
        if not user32.GetClientRect(self._hwnd, ctypes.byref(client)):
            return
        width = max(640, client.right - client.left)
        height = max(410, client.bottom - client.top)
        margin = 24
        navigation_width = 168
        content_x = margin + navigation_width + 28
        content_width = max(320, width - content_x - margin)

        self._move("navigation_heading", margin, 24, navigation_width, 24)
        self._move("dictation_navigation", margin, 54, navigation_width, 34)
        self._move("page_heading", content_x, 24, content_width, 28)
        self._move("page_description", content_x, 58, content_width, 36)
        self._move("hotkey_label", content_x, 112, content_width, 22)
        self._move("hotkey", content_x, 136, min(330, content_width), 28)
        self._move("microphone_label", content_x, 184, content_width, 22)
        self._move("microphone", content_x, 208, min(400, content_width), 180)
        self._move("stop_after_speech", content_x, 260, content_width, 30)
        self._move("privacy_note", content_x, 306, content_width, 36)

        footer_y = height - 58
        self._move("reset", content_x, footer_y, 134, 32)
        self._move("cancel", max(content_x + 150, width - margin - 190), footer_y, 84, 32)
        self._move("save", width - margin - 96, footer_y, 96, 32)

    def write_draft(self, draft: NativeSettingsDraft) -> None:
        self._assert_owner_thread()
        user32.SetWindowTextW(self._controls["hotkey"], draft.hotkey)
        try:
            microphone_index = self._microphones.index(draft.microphone)
        except ValueError:
            microphone_index = 0
        user32.SendMessageW(
            self._controls["microphone"], CB_SETCURSEL, microphone_index, 0
        )
        user32.SendMessageW(
            self._controls["stop_after_speech"],
            BM_SETCHECK,
            BST_CHECKED if draft.stop_after_speech else 0,
            0,
        )

    def read_draft(self) -> NativeSettingsDraft:
        self._assert_owner_thread()
        hotkey = self._window_text(self._controls["hotkey"])
        index = int(
            user32.SendMessageW(self._controls["microphone"], CB_GETCURSEL, 0, 0)
        )
        microphone = (
            self._microphones[index]
            if 0 <= index < len(self._microphones)
            else self._microphones[0]
        )
        checked = int(
            user32.SendMessageW(
                self._controls["stop_after_speech"], BM_GETCHECK, 0, 0
            )
        )
        return NativeSettingsDraft(hotkey, microphone, checked == BST_CHECKED)

    @staticmethod
    def _window_text(hwnd: int) -> str:
        length = user32.GetWindowTextLengthW(hwnd)
        buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buffer, len(buffer))
        return buffer.value

    def reset_to_defaults(self) -> None:
        """Reset only the local draft; no preferences or user data are touched."""

        self.write_draft(NativeSettingsDraft())

    def invoke(self, key: str) -> None:
        """Exercise the same command path as a native button click."""

        self._assert_owner_thread()
        if key not in {"dictation_navigation", "reset", "cancel", "save"}:
            raise ValueError(f"{key!r} is not an action button")
        spec = _SPEC_BY_KEY[key]
        user32.SendMessageW(self._hwnd, WM_COMMAND, spec.control_id, self._controls[key])

    def _finish(self, action: str, draft: NativeSettingsDraft) -> None:
        self._result = NativeSettingsResult(action, draft)
        if self._hwnd:
            user32.DestroyWindow(self._hwnd)

    def _handle_message(self, message: int, wparam: int, lparam: int) -> int:
        if message == WM_COMMAND:
            control_id = int(wparam) & 0xFFFF
            notification = (int(wparam) >> 16) & 0xFFFF
            if notification == BN_CLICKED:
                if control_id == _SPEC_BY_KEY["save"].control_id:
                    self._finish("save", self.read_draft())
                    return 0
                if control_id == _SPEC_BY_KEY["cancel"].control_id:
                    self._finish("cancel", self._original)
                    return 0
                if control_id == _SPEC_BY_KEY["reset"].control_id:
                    self.reset_to_defaults()
                    return 0
                if control_id == _SPEC_BY_KEY["dictation_navigation"].control_id:
                    user32.SetFocus(self._controls["hotkey"])
                    return 0
        elif message == WM_SIZE:
            self._layout()
            return 0
        elif message == WM_CLOSE:
            self._finish("cancel", self._original)
            return 0
        elif message == WM_DESTROY:
            if self._running:
                user32.PostQuitMessage(0)
            return 0
        elif message == WM_NCDESTROY:
            old_hwnd = self._hwnd
            self._hwnd = 0
            _WINDOWS.pop(old_hwnd, None)
            return user32.DefWindowProcW(old_hwnd, message, wparam, lparam)
        return user32.DefWindowProcW(self._hwnd, message, wparam, lparam)

    def run(self) -> NativeSettingsResult:
        """Run the dialog loop and return local state without persisting it."""

        self._assert_owner_thread()
        if not self._hwnd:
            return self._result or NativeSettingsResult("cancel", self._original)
        self._running = True
        message = wintypes.MSG()
        try:
            while self._hwnd:
                state = user32.GetMessageW(ctypes.byref(message), None, 0, 0)
                if state == -1:
                    raise ctypes.WinError(ctypes.get_last_error())
                if state == 0:
                    break
                if not user32.IsDialogMessageW(self._hwnd, ctypes.byref(message)):
                    user32.TranslateMessage(ctypes.byref(message))
                    user32.DispatchMessageW(ctypes.byref(message))
        finally:
            self._running = False
            self.destroy()
        return self._result or NativeSettingsResult("cancel", self._original)

    def destroy(self) -> None:
        """Destroy the HWND deterministically without touching product state."""

        self._assert_owner_thread()
        if self._hwnd and user32.IsWindow(self._hwnd):
            user32.DestroyWindow(self._hwnd)
        elif self._hwnd:
            _WINDOWS.pop(self._hwnd, None)
            self._hwnd = 0

    def __enter__(self) -> "NativeSettingsShell":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.destroy()


def create_native_settings_shell(
    draft: NativeSettingsDraft | None = None,
    microphones: tuple[str, ...] | list[str] | None = None,
    *,
    visible: bool = True,
) -> NativeSettingsShell:
    """Create the opt-in proof; callers remain responsible for its lifetime."""

    return NativeSettingsShell(draft, microphones, visible=visible)


def run_native_settings_shell(
    draft: NativeSettingsDraft | None = None,
    microphones: tuple[str, ...] | list[str] | None = None,
) -> NativeSettingsResult:
    """Explicitly show the proof and return, but never save, its local state."""

    return create_native_settings_shell(draft, microphones, visible=True).run()


def live_native_window_count() -> int:
    """Return process-local proof windows for deterministic teardown checks."""

    return len(_WINDOWS)
