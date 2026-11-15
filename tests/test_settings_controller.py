from __future__ import annotations

import pytest

from utterleaf.config import Config
from utterleaf.settings import SettingsSaveError
from utterleaf.settings_controller import SettingsController, SettingsDraft


def draft_values(**overrides):
    values = {
        "hotkey": "ctrl+win",
        "mode": "hold",
        "model": "small.en",
        "device": "auto",
        "language": "en",
        "denoise": "auto",
        "microphone": "System default",
        "beep": True,
        "indicator": False,
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
    return values


def test_draft_round_trip_is_independent_and_shape_checked():
    source = draft_values()
    draft = SettingsDraft.from_mapping(source)
    source["hotkey"] = "f8"
    assert draft.hotkey == "ctrl+win"
    assert draft.form_values() == draft_values()

    with pytest.raises(ValueError, match="missing: names"):
        SettingsDraft.from_mapping(
            {
                key: value
                for key, value in draft_values().items()
                if key != "names"
            }
        )
    with pytest.raises(ValueError, match="unexpected: search"):
        SettingsDraft.from_mapping({**draft_values(), "search": "private value"})


def test_commit_uses_loaded_config_and_notifies_once():
    original = Config(hotkey="f8")
    updated = Config(hotkey="ctrl+win")
    calls = []

    def apply(config, **values):
        calls.append(("apply", config, values))
        return updated

    controller = SettingsController(
        lambda: original,
        apply,
        lambda command: calls.append(("notify", command)) or "ok",
    )
    outcome = controller.commit(SettingsDraft.from_mapping(draft_values()))

    assert outcome.config is updated and outcome.reply == "ok" and outcome.error is None
    assert calls[0][0:2] == ("apply", original)
    assert calls[0][2] == draft_values()
    assert calls[1] == ("notify", "reload")


def test_commit_reset_uses_defaults_without_loading_saved_config():
    seen = []

    def apply(config, **_values):
        seen.append(config)
        return config

    controller = SettingsController(
        lambda: pytest.fail("reset loaded the broken saved config"),
        apply,
        lambda _command: "ok",
    )
    outcome = controller.commit(
        SettingsDraft.from_mapping(draft_values()),
        reset_defaults=True,
    )

    assert seen == [Config()] and outcome.config == Config()


def test_partial_save_failure_notifies_and_preserves_structured_error():
    failure = SettingsSaveError(
        ["dictation settings"],
        "vocabulary",
        ["start at login"],
        OSError("disk full"),
    )
    notifications = []

    controller = SettingsController(
        Config,
        lambda *_args, **_kwargs: (_ for _ in ()).throw(failure),
        lambda command: notifications.append(command) or "ok",
    )
    outcome = controller.commit(SettingsDraft.from_mapping(draft_values()))

    assert outcome.error is failure and outcome.config is None
    assert outcome.reload_error is None and notifications == ["reload"]


def test_reload_failure_distinguishes_saved_config_from_failed_save():
    reload_failure = OSError("app unavailable")

    controller = SettingsController(
        Config,
        lambda *_args, **_kwargs: Config(hotkey="f8"),
        lambda _command: (_ for _ in ()).throw(reload_failure),
    )
    outcome = controller.commit(SettingsDraft.from_mapping(draft_values()))

    assert outcome.config == Config(hotkey="f8")
    assert outcome.error is None and outcome.reload_error is reload_failure
