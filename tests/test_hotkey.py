from pynput import keyboard

from utterleaf.hotkey import HotkeyWatcher, combo_is_down, parse_hotkey


def test_parse_right_ctrl() -> None:
    assert parse_hotkey("right ctrl") == {keyboard.Key.ctrl_r}


def test_parse_combo() -> None:
    keys = parse_hotkey("ctrl+win")
    assert keyboard.Key.ctrl in keys
    assert keyboard.Key.cmd in keys


def test_parse_ctrl_super_alias() -> None:
    assert parse_hotkey("ctrl+super") == parse_hotkey("ctrl+win")
    assert parse_hotkey("ctrl + super") == parse_hotkey("ctrl+win")


def test_parse_function_key() -> None:
    assert parse_hotkey("f8") == {keyboard.Key.f8}


def test_right_ctrl_does_not_match_left_ctrl() -> None:
    wanted = parse_hotkey("right ctrl")
    assert combo_is_down({keyboard.Key.ctrl_r}, wanted)
    assert not combo_is_down({keyboard.Key.ctrl_l}, wanted)


def test_generic_ctrl_matches_either_side() -> None:
    wanted = parse_hotkey("ctrl+shift")
    assert combo_is_down({keyboard.Key.ctrl_l, keyboard.Key.shift_r}, wanted)


class _FakeWin:
    vkCode = 0x5B
    flags = 0


class _FakeListener:
    def __init__(self) -> None:
        self.swallowed = 0

    def suppress_event(self) -> None:
        self.swallowed += 1

    def stop(self) -> None:
        pass


def _ctrl_win_hold() -> HotkeyWatcher:
    return HotkeyWatcher(
        "ctrl+win",
        mode="hold",
        suppress=False,
        on_start=lambda: None,
        on_stop=lambda: None,
        on_cancel=lambda: None,
    )


def test_lone_win_should_still_open_start() -> None:
    watcher = _ctrl_win_hold()
    assert watcher._uses_win()
    assert not watcher._win_for_ptt

    watcher._listener = _FakeListener()
    watcher._on_press(keyboard.Key.ctrl)
    watcher._on_press(keyboard.Key.cmd)
    watcher._on_release(keyboard.Key.cmd)
    watcher._on_release(keyboard.Key.ctrl)
    assert not watcher._win_for_ptt
    watcher._win32_filter(0, _FakeWin())
    assert watcher._listener.swallowed == 0


def test_esc_clears_win_for_ptt() -> None:
    watcher = _ctrl_win_hold()
    watcher._listener = _FakeListener()
    watcher._on_press(keyboard.Key.ctrl)
    watcher._on_press(keyboard.Key.cmd)
    watcher._on_press(keyboard.Key.esc)
    assert not watcher._win_for_ptt
    watcher._on_release(keyboard.Key.cmd)
    watcher._on_release(keyboard.Key.ctrl)
    watcher._win32_filter(0, _FakeWin())
    assert watcher._listener.swallowed == 0


def test_force_stop_clears_win_for_ptt() -> None:
    watcher = _ctrl_win_hold()
    watcher._on_press(keyboard.Key.ctrl)
    watcher._on_press(keyboard.Key.cmd)
    watcher.force_stop()
    assert not watcher._win_for_ptt


def test_stop_clears_win_for_ptt() -> None:
    watcher = _ctrl_win_hold()
    watcher._on_press(keyboard.Key.ctrl)
    watcher._on_press(keyboard.Key.cmd)
    watcher.stop()
    assert not watcher._win_for_ptt
    watcher._on_release(keyboard.Key.cmd)
    watcher._on_release(keyboard.Key.ctrl)
    watcher._listener = _FakeListener()
    watcher._win32_filter(0, _FakeWin())
    assert watcher._listener.swallowed == 0


def test_toggle_ignores_key_repeat() -> None:
    starts = []
    stops = []
    watcher = HotkeyWatcher(
        "f8",
        mode="toggle",
        suppress=False,
        on_start=lambda: starts.append(1),
        on_stop=lambda: stops.append(1),
        on_cancel=lambda: None,
    )
    watcher._on_press(keyboard.Key.f8)
    watcher._on_press(keyboard.Key.f8)
    watcher._on_press(keyboard.Key.f8)
    assert starts == [1]
    assert stops == []
    watcher._on_release(keyboard.Key.f8)
    watcher._on_press(keyboard.Key.f8)
    assert stops == [1]


def test_wayland_uses_ipc_toggle_without_starting_xorg_listener(monkeypatch):
    from utterleaf import hotkey

    monkeypatch.setattr(hotkey, "is_wayland", lambda: True)

    def forbidden_listener(**kwargs):
        raise AssertionError("Wayland must not start an Xorg key listener")

    monkeypatch.setattr(hotkey.keyboard, "Listener", forbidden_listener)
    events = []
    watcher = HotkeyWatcher("f8", mode="hold", suppress=False,
                            on_start=lambda: events.append("start"),
                            on_stop=lambda: events.append("stop"),
                            on_cancel=lambda: events.append("cancel"))
    watcher.start()
    watcher.toggle()
    watcher.toggle()
    watcher.stop()
    assert events == ["start", "stop"]
    assert watcher._listener is None
