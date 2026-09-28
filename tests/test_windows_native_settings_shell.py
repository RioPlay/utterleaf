from __future__ import annotations

import ctypes
from ctypes import wintypes
from dataclasses import replace
import sys

import pytest

from utterleaf.config import Config
from utterleaf.settings import SettingsSaveError
from utterleaf.settings_controller import SettingsController, SettingsDraft
from utterleaf.windows_ui.native_settings import (
    CONTROL_SPECS,
    create_native_settings_shell,
    live_native_window_count,
)


def _draft(**overrides) -> SettingsDraft:
    values = {
        "hotkey": "ctrl+win",
        "mode": "hold",
        "model": "small.en",
        "device": "auto",
        "language": "en",
        "denoise": "auto",
        "microphone": "System default",
        "beep": True,
        "indicator": True,
        "live_preview": True,
        "remove_fillers": True,
        "fix_corrections": True,
        "restore_clipboard": True,
        "allow_network": False,
        "text_cleanup": True,
        "output_format": "prose",
        "speech_end_enabled": False,
        "speech_end_pause_seconds": "1.2",
        "speech_end_insert": False,
        "start_at_login": False,
        "names": "Utterleaf = Utterleaf",
    }
    values.update(overrides)
    return SettingsDraft.from_mapping(values)


def _controller(*, apply=None, load=None, notify=None) -> SettingsController:
    return SettingsController(
        load or Config,
        apply or (lambda _config, **_values: Config()),
        notify or (lambda _command: "ok"),
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
        create_native_settings_shell(
            _draft(),
            _draft(),
            _controller(),
            visible=False,
        )
    assert live_native_window_count() == 0


@pytest.mark.skipif(sys.platform != "win32", reason="standard Win32 controls")
def test_native_control_classes_and_local_draft_round_trip():
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.GetClassNameW.argtypes = (wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
    user32.GetClassNameW.restype = ctypes.c_int
    draft = _draft(
        hotkey="Alt+Space",
        microphone="USB microphone",
        speech_end_enabled=True,
        language="de",
        model="small",
    )
    defaults = _draft(hotkey="Ctrl+Win", language="auto", model="base")

    with create_native_settings_shell(
        draft,
        defaults,
        _controller(),
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
        assert shell.read_draft() == defaults

    assert live_native_window_count() == 0


@pytest.mark.skipif(sys.platform != "win32", reason="standard Win32 controls")
def test_save_cancel_and_repeated_teardown_are_deterministic():
    original = _draft(hotkey="Alt+Space", speech_end_enabled=True)
    for action in ("cancel", "save", "cancel", "save"):
        shell = create_native_settings_shell(
            original,
            _draft(),
            _controller(),
            visible=False,
        )
        old_hwnd = shell.hwnd
        shell.invoke(action)
        assert shell.hwnd == 0
        assert shell.result is not None
        assert shell.result.action == action
        assert shell.result.draft == original
        assert (shell.result.outcome is not None) == (action == "save")
        assert not ctypes.windll.user32.IsWindow(old_hwnd)
        assert live_native_window_count() == 0


@pytest.mark.skipif(sys.platform != "win32", reason="standard Win32 controls")
def test_save_uses_shared_controller_and_preserves_hidden_fields():
    original = _draft(language="fr", model="medium", names="Camille")
    applied = []

    def apply(config, **values):
        applied.append((config, values))
        return Config()

    shell = create_native_settings_shell(
        original,
        _draft(),
        _controller(apply=apply),
        visible=False,
    )
    shell.write_draft(replace(original, hotkey="F8"))
    shell.invoke("save")

    assert shell.result is not None and shell.result.action == "save"
    assert shell.result.draft.hotkey == "F8"
    assert shell.result.draft.language == "fr"
    assert shell.result.draft.model == "medium"
    assert shell.result.draft.names == "Camille"
    assert applied[0][1] == shell.result.draft.form_values()


@pytest.mark.skipif(sys.platform != "win32", reason="standard Win32 controls")
def test_failed_save_stays_open_and_never_exposes_raw_exception():
    failure = SettingsSaveError([], "dictation settings", [], OSError("disk secret"))
    shell = create_native_settings_shell(
        _draft(),
        _draft(),
        _controller(
            apply=lambda *_args, **_kwargs: (_ for _ in ()).throw(failure)
        ),
        visible=False,
    )
    old_hwnd = shell.hwnd

    shell.invoke("save")

    assert shell.hwnd == old_hwnd
    assert shell.result is None
    assert ctypes.windll.user32.IsWindow(old_hwnd)
    status = shell._window_text(shell.control_handle("save_status"))
    assert "Could not save changes" in status
    assert "disk secret" not in status
    shell.destroy()
