from __future__ import annotations

import ctypes
from ctypes import wintypes
import sys

import pytest

from utterleaf.windows_ui.native_settings import (
    CONTROL_SPECS,
    NativeSettingsDraft,
    create_native_settings_shell,
    live_native_window_count,
)


def test_control_metadata_is_named_stable_and_uses_standard_classes():
    assert len({spec.key for spec in CONTROL_SPECS}) == len(CONTROL_SPECS)
    assert len({spec.control_id for spec in CONTROL_SPECS}) == len(CONTROL_SPECS)
    assert all(spec.accessible_name.strip() for spec in CONTROL_SPECS)
    assert {spec.class_name for spec in CONTROL_SPECS} <= {
        "Button",
        "ComboBox",
        "Edit",
        "Static",
    }
    assert {
        "dictation_navigation",
        "hotkey",
        "microphone",
        "stop_after_speech",
        "reset",
        "cancel",
        "save",
    } <= {spec.key for spec in CONTROL_SPECS}
    assert {spec.control_type for spec in CONTROL_SPECS if spec.tab_stop} == {
        "Button",
        "CheckBox",
        "ComboBox",
        "Edit",
    }


def test_non_windows_creation_fails_without_side_effects():
    if sys.platform == "win32":
        pytest.skip("Windows exercises the native lifecycle below")
    with pytest.raises(OSError, match="only on Windows"):
        create_native_settings_shell(visible=False)
    assert live_native_window_count() == 0


@pytest.mark.skipif(sys.platform != "win32", reason="standard Win32 controls")
def test_native_control_classes_and_local_draft_round_trip():
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.GetClassNameW.argtypes = (wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
    user32.GetClassNameW.restype = ctypes.c_int
    draft = NativeSettingsDraft("Alt+Space", "USB microphone", True)

    with create_native_settings_shell(
        draft,
        ("System default", "USB microphone"),
        visible=False,
    ) as shell:
        assert live_native_window_count() == 1
        assert shell.read_draft() == draft
        for spec in CONTROL_SPECS:
            buffer = ctypes.create_unicode_buffer(64)
            assert user32.GetClassNameW(
                shell.control_handle(spec.key), buffer, len(buffer)
            )
            assert buffer.value.casefold() == spec.class_name.casefold()

        shell.reset_to_defaults()
        assert shell.read_draft() == NativeSettingsDraft()

    assert live_native_window_count() == 0


@pytest.mark.skipif(sys.platform != "win32", reason="standard Win32 controls")
def test_save_cancel_and_repeated_teardown_are_deterministic():
    original = NativeSettingsDraft("Alt+Space", "System default", True)
    for action in ("cancel", "save", "cancel", "save"):
        shell = create_native_settings_shell(original, visible=False)
        old_hwnd = shell.hwnd
        shell.invoke(action)
        assert shell.hwnd == 0
        assert shell.result is not None
        assert shell.result.action == action
        assert not ctypes.windll.user32.IsWindow(old_hwnd)
        assert live_native_window_count() == 0
