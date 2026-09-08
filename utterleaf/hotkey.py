"""Parse a hotkey string and watch for hold/toggle presses."""

from __future__ import annotations

import sys
import logging
import threading
from collections.abc import Callable

from pynput import keyboard
from utterleaf.host import is_wayland

MOD_ALIASES = {
    "ctrl": "ctrl",
    "control": "ctrl",
    "alt": "alt",
    "shift": "shift",
    "win": "cmd",
    "super": "cmd",
    "cmd": "cmd",
    "meta": "cmd",
}

SPECIAL = {
    "right ctrl": keyboard.Key.ctrl_r,
    "left ctrl": keyboard.Key.ctrl_l,
    "right alt": keyboard.Key.alt_r,
    "left alt": keyboard.Key.alt_l,
    "right shift": keyboard.Key.shift_r,
    "left shift": keyboard.Key.shift_l,
    "right win": keyboard.Key.cmd_r,
    "left win": keyboard.Key.cmd_l,
    "esc": keyboard.Key.esc,
    "escape": keyboard.Key.esc,
    "space": keyboard.Key.space,
    "tab": keyboard.Key.tab,
    "caps lock": keyboard.Key.caps_lock,
    "capslock": keyboard.Key.caps_lock,
}


def parse_hotkey(spec: str) -> set[object]:
    raw = spec.strip().lower()
    if raw in SPECIAL:
        return {SPECIAL[raw]}
    if raw.startswith("f") and raw[1:].isdigit():
        return {getattr(keyboard.Key, raw)}
    parts = [part.strip() for part in raw.replace("-", "+").split("+") if part.strip()]
    keys: set[object] = set()
    for part in parts:
        if part in SPECIAL:
            keys.add(SPECIAL[part])
            continue
        if part in MOD_ALIASES:
            keys.add(getattr(keyboard.Key, MOD_ALIASES[part]))
            continue
        if part.startswith("f") and part[1:].isdigit():
            keys.add(getattr(keyboard.Key, part))
            continue
        if len(part) == 1:
            keys.add(keyboard.KeyCode.from_char(part))
            continue
        raise ValueError(f"Unknown hotkey part: {part}")
    if not keys:
        raise ValueError(f"Empty hotkey: {spec}")
    return keys


GENERIC_GROUPS = (
    {keyboard.Key.ctrl, keyboard.Key.ctrl_l, keyboard.Key.ctrl_r},
    {keyboard.Key.alt, keyboard.Key.alt_l, keyboard.Key.alt_r, keyboard.Key.alt_gr},
    {keyboard.Key.shift, keyboard.Key.shift_l, keyboard.Key.shift_r},
    {keyboard.Key.cmd, keyboard.Key.cmd_l, keyboard.Key.cmd_r},
)

GENERIC_KEYS = {
    keyboard.Key.ctrl,
    keyboard.Key.alt,
    keyboard.Key.shift,
    keyboard.Key.cmd,
}


def _normalize_char(key: object) -> object:
    if isinstance(key, keyboard.KeyCode) and key.char:
        return keyboard.KeyCode.from_char(key.char.lower())
    return key


def _held(down: set[object], wanted: object) -> bool:
    if wanted in down:
        return True
    if wanted in GENERIC_KEYS:
        for group in GENERIC_GROUPS:
            if wanted in group and down & group:
                return True
    return False


def combo_is_down(down: set[object], wanted: set[object]) -> bool:
    return all(_held(down, key) for key in wanted)


class HotkeyWatcher:
    def __init__(
        self,
        spec: str,
        *,
        mode: str,
        suppress: bool,
        on_start: Callable[[], None],
        on_stop: Callable[[], None],
        on_cancel: Callable[[], None],
    ) -> None:
        self.wanted = parse_hotkey(spec)
        self.mode = mode
        self.suppress = suppress
        self.on_start = on_start
        self.on_stop = on_stop
        self.on_cancel = on_cancel
        self._down: set[object] = set()
        self._active = False
        self._win_for_ptt = False
        self._listener: keyboard.Listener | None = None
        self._lock = threading.Lock()

    def _combo_down(self) -> bool:
        return combo_is_down(self._down, self.wanted)

    def _on_press(self, key: object) -> None:
        if key == keyboard.Key.esc:
            if self._active:
                self._active = False
            self._win_for_ptt = False
            self.on_cancel()
            return
        token = _normalize_char(key)
        if token in self._down:
            return
        self._down.add(token)
        if not self._combo_down():
            return
        if self.mode == "toggle":
            if self._active:
                self._active = False
                self._win_for_ptt = False
                self.on_stop()
            else:
                self._active = True
                self.on_start()
            return
        if not self._active:
            self._active = True
            if self._uses_win():
                self._win_for_ptt = True
            self.on_start()

    def _on_release(self, key: object) -> None:
        self._down.discard(_normalize_char(key))
        if self.mode != "hold":
            return
        if self._active and not self._combo_down():
            self._active = False
            self._win_for_ptt = False
            self.on_stop()

    def _uses_win(self) -> bool:
        return any(
            key in self.wanted
            for key in (keyboard.Key.cmd, keyboard.Key.cmd_l, keyboard.Key.cmd_r)
        )

    def _win32_filter(self, msg, data) -> bool:
        # Swallow Win only during Ctrl+Win PTT so Win+E / Win+V still work.
        vk = getattr(data, "vkCode", None)
        if vk not in {0x5B, 0x5C} or not self._uses_win() or self._listener is None:
            return True
        flags = int(getattr(data, "flags", 0) or 0)
        if flags & 0x10:
            return True
        hold = self._win_for_ptt or self._active or _held(self._down, keyboard.Key.ctrl)
        if not hold:
            return True
        try:
            self._listener.suppress_event()
        except Exception:
            pass
        return True

    def start(self) -> None:
        if is_wayland():
            logging.getLogger("utterleaf").info(
                "Wayland: global key listening disabled; bind a desktop shortcut to utterleaf --toggle"
            )
            return
        kwargs = {}
        if sys.platform == "win32":
            kwargs["win32_event_filter"] = self._win32_filter
        self._listener = keyboard.Listener(
            on_press=self._on_press,
            on_release=self._on_release,
            suppress=self.suppress,
            **kwargs,
        )
        self._listener.start()

    def stop(self) -> None:
        self._win_for_ptt = False
        if self._listener is not None:
            self._listener.stop()
            self._listener = None

    def force_start(self) -> None:
        with self._lock:
            if self._active:
                return
            self._active = True
        self.on_start()

    def force_stop(self) -> None:
        with self._lock:
            if not self._active:
                return
            self._active = False
            self._win_for_ptt = False
        self.on_stop()

    def toggle(self) -> None:
        if self._active:
            self.force_stop()
        else:
            self.force_start()
