"""Regression checks for the side-effect-free desktop baseline harness."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess
import sys

import pytest

from utterleaf.audio import SelectedMicrophoneUnavailable, microphone_error_hint
from utterleaf.config import Config


SOURCE = Path(__file__).with_name("capture_settings.py")
SPEC = importlib.util.spec_from_file_location("utterleaf_capture_settings", SOURCE)
assert SPEC is not None and SPEC.loader is not None
capture_settings = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(capture_settings)


@pytest.fixture(scope="module", autouse=True)
def working_tk_display():
    probe = subprocess.run(
        [
            sys.executable,
            "-c",
            "import tkinter as tk; root = tk.Tk(); root.withdraw(); root.destroy()",
        ],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    if probe.returncode:
        pytest.skip(f"Tk needs a working display: {probe.stderr.strip()}")
    yield


def test_capture_inventory_is_explicit_complete_and_unique():
    inventory = capture_settings.CAPTURE_INVENTORY
    assert len(inventory) == 56
    for filename, *_ in capture_settings.SEARCH_CAPTURES:
        assert filename in inventory
    assert len(inventory) == len(set(inventory))
    assert "save-clean.png" in inventory
    assert "reset-staged.png" in inventory
    assert "recording-feedback-reset-staged.png" in inventory
    assert "vocabulary-empty.png" in inventory
    assert (
        "vocabulary-oversized-validation-synthetic-post-dialog.png" in inventory
    )
    assert "device-refresh-error.png" in inventory
    assert "microphone-unsupported-format.png" in inventory
    assert "microphone-unsupported-compact-text-scale-2x-focused.png" in inventory
    assert "engine-compact-text-scale-2x-synthetic-overview.png" in inventory
    assert (
        "engine-compact-text-scale-2x-synthetic-cancel-focused.png" in inventory
    )
    for filename, _reply in capture_settings.APP_STATUS_CAPTURES:
        assert filename in inventory
    assert "save-partial-failure-post-dialog.png" in inventory
    assert "save-invalid-vocabulary-post-dialog.png" in inventory
    assert "save-partial-failure.png" not in inventory
    assert "save-invalid-vocabulary.png" not in inventory
    assert (
        capture_settings.COMPACT[0]
        < capture_settings.STANDARD[0]
        < capture_settings.WIDE[0]
    )
    assert (
        capture_settings.COMPACT[1]
        < capture_settings.STANDARD[1]
        < capture_settings.WIDE[1]
    )
    for _, slug in capture_settings.PAGE_SLUGS:
        assert f"page-{slug}-standard.png" in inventory
        assert f"page-{slug}-lower.png" in inventory


def test_search_staging_preserves_preferences_and_has_no_external_actions():
    with capture_settings._blocked_runtime() as runtime:
        with capture_settings._window(runtime, visible=False) as window:
            before = window._snapshot()
            for _filename, query, key, _large in capture_settings.SEARCH_CAPTURES:
                capture_settings._stage_search(window, query, key)
                assert window.search_open
                assert window.search_query.get() == query
                if key is not None:
                    selected = window.search_results.curselection()[0]
                    assert window.search_matches[selected].key == key
                if key == "speech_end_insert":
                    assert "Enable Stop after speech first." in window.search_detail.get()
                assert window._snapshot() == before
                window.close_search()
                assert window.search_query.get() == ""
        assert runtime.blocked_actions == []
        assert runtime.ipc_commands == []
        assert runtime.dialogs == []


def test_runtime_blocks_every_user_invokable_external_action():
    with capture_settings._blocked_runtime() as runtime:
        with capture_settings._window(runtime, visible=False) as window:
            window.mic_button.invoke()
            window.refresh_button.invoke()
            window.model_download_button.invoke()
            window.save()
            window.show_backup()
            window.show_obs_pairing()
            window.diagnostics()
            window.refresh_connection()
            window.cuda_setup()
            window.export_report()

            from utterleaf.appearance import AppearanceGuide

            AppearanceGuide.export(object())

        assert set(runtime.blocked_actions) == {
            "test_mic",
            "refresh_mics",
            "download_model",
            "save",
            "show_backup",
            "show_obs_pairing",
            "refresh_connection",
            "diagnostics",
            "cuda_setup",
            "export_report",
            "export_artwork",
        }
        assert runtime.ipc_commands == []
        assert runtime.dialogs == []


def test_two_x_engine_capture_restores_scale_and_keeps_actions_mapped():
    with capture_settings._blocked_runtime() as runtime:
        with capture_settings._window(
            runtime,
            text_scale=capture_settings.LARGE_TEXT_SCALE,
        ) as window:
            window.root.geometry(
                f"{capture_settings.COMPACT[0]}x{capture_settings.COMPACT[1]}"
            )
            capture_settings._stage_model(window, runtime, "model-downloading")
            window.show_page("Engine")
            capture_settings._settle(window.root, cycles=2)
            capture_settings._focus_model_cancel(window)
            capture_settings._settle(window.root, cycles=2)

            assert window.root.focus_get() == window.model_cancel_button
            assert window.model_download_button.winfo_ismapped()
            assert window.model_cancel_button.winfo_ismapped()
            viewport_top = window.canvas.winfo_rooty()
            viewport_bottom = viewport_top + window.canvas.winfo_height()
            cancel_top = window.model_cancel_button.winfo_rooty()
            assert cancel_top >= viewport_top
            assert (
                cancel_top + window.model_cancel_button.winfo_height()
                <= viewport_bottom
            )

        assert len(runtime.scale_receipts) == 1
        multiplier, baseline, active, restored = runtime.scale_receipts[0]
        assert multiplier == capture_settings.LARGE_TEXT_SCALE
        assert active == pytest.approx(baseline * multiplier, rel=0.02)
        assert restored == pytest.approx(baseline, rel=0.01)

        with capture_settings._window(runtime, visible=False) as ordinary:
            assert float(ordinary.root.tk.call("tk", "scaling")) == pytest.approx(
                baseline,
                rel=0.01,
            )
        assert len(runtime.scale_receipts) == 1


def test_staged_states_use_production_callbacks_and_do_not_leak():
    saved = "All changes saved · Dictation stays on this device"
    with capture_settings._blocked_runtime() as runtime:
        with capture_settings._window(
            runtime,
            cfg=Config(microphone=capture_settings.STUDIO_MICROPHONE),
            visible=False,
        ) as window:
            capture_settings._stage_device_refresh(window, ["Laptop microphone"])
            assert window.status.get() == saved
            assert window.mic_message.get() == (
                "Selected microphone is unavailable. Reconnect it or choose another input and Save."
            )

        with capture_settings._window(runtime, visible=False) as window:
            dialogs_before = len(runtime.dialogs)
            capture_settings._stage_device_refresh(
                window,
                RuntimeError(capture_settings.DEVICE_REFRESH_DETAIL),
            )
            assert window.mic_message.get() == (
                capture_settings.DEVICE_REFRESH_ERROR_ACTION
            )
            assert capture_settings.DEVICE_REFRESH_DETAIL not in window.mic_message.get()
            assert str(window.mic_details_button.cget("state")) == "normal"
            assert window.mic_details_button.winfo_manager() == "pack"
            assert all(
                capture_settings.DEVICE_REFRESH_DETAIL not in dialog[2]
                for dialog in runtime.dialogs[dialogs_before:]
            )

            window.mic_details_button.invoke()
            assert runtime.dialogs[-1][:2] == ("info", "Microphone check details")
            assert runtime.dialogs[-1][2].endswith(
                "RuntimeError: " + capture_settings.DEVICE_REFRESH_DETAIL
            )

            capture_settings._stage_device_refresh(window, ["Laptop microphone"])
            assert window.error_details[window.mic_details_button] == ""
            assert str(window.mic_details_button.cget("state")) == "disabled"
            assert window.mic_details_button.winfo_manager() == ""

        for phase, message, meter in (
            ("opening", "Opening your microphone…", 0),
            ("listening", "Speak now… checking for five seconds.", 42),
        ):
            with capture_settings._window(
                runtime,
                cfg=Config(microphone=capture_settings.STUDIO_MICROPHONE),
                visible=False,
            ) as window:
                capture_settings._stage_microphone(window, phase)
                assert window.mic_message.get() == message
                assert str(window.mic_button.cget("text")) == "Stop"
                assert float(window.meter.cget("value")) == meter

        outcomes = {
            "low-input": (
                "Very little audio detected. Check your input device and microphone level."
            ),
            "ready": capture_settings.MICROPHONE_SUCCESS_ACTION,
            "unsupported-format": capture_settings.MICROPHONE_FORMAT_ACTION,
            "error": microphone_error_hint(
                SelectedMicrophoneUnavailable("Selected microphone is unavailable")
            ),
        }
        for phase, message in outcomes.items():
            with capture_settings._window(
                runtime,
                cfg=Config(microphone=capture_settings.STUDIO_MICROPHONE),
                visible=False,
            ) as window:
                capture_settings._stage_microphone(window, phase)
                assert window.status.get() == saved
                assert window.mic_message.get() == message
                assert float(window.meter.cget("value")) == 0
                assert window.mic_button.cget("text") == "Test"

        for state, description in (
            ("missing", "Missing — download this model before using it offline."),
            (
                "incomplete",
                "Incomplete — required files are missing or invalid. Download to finish setup.",
            ),
        ):
            with capture_settings._window(
                runtime,
                model_state=state,
                visible=False,
            ) as window:
                capture_settings._stage_model(window, runtime, f"model-{state}")
                assert window.model_status.get() == (
                    f"{capture_settings.MODEL_DISPLAY_NAME}\n"
                    f"{capture_settings.MODEL_PURPOSE}\n{description}"
                )
                assert "small.en" not in window.model_status.get()
                assert "ctranslate2" not in window.model_status.get()
                assert "CPU / NVIDIA" not in window.model_status.get()
                assert window.model_info_button.cget("text") == "Model details…"
                assert window.model_info_button.winfo_manager() == "pack"
                assert window.model_details_button.cget("text") == (
                    "Download error details…"
                )
                assert window.model_details_button.winfo_manager() == ""
                assert str(window.model_download_button.cget("state")) == "normal"

        with capture_settings._window(runtime, visible=False) as window:
            capture_settings._stage_model(window, runtime, "model-downloading")
            assert window.model_downloading
            assert window.model_action_status.get() == (
                "Downloading Small English… Keep this window open; Cancel stops the download."
            )
            assert "small.en" not in window.model_status.get()
            assert "ctranslate2" not in window.model_status.get()
            assert "CPU / NVIDIA" not in window.model_status.get()
            assert str(window.model_download_button.cget("state")) == "disabled"
            assert str(window.model_cancel_button.cget("state")) == "normal"

        with capture_settings._window(
            runtime,
            model_state="incomplete",
            visible=False,
        ) as window:
            capture_settings._stage_model(window, runtime, "model-cancelled")
            assert not window.model_downloading
            assert window.model_action_status.get() == (
                "Download cancelled. Partial files are kept so you can retry."
            )
            assert "small.en" not in window.model_status.get()
            assert "ctranslate2" not in window.model_status.get()
            assert "CPU / NVIDIA" not in window.model_status.get()
            assert str(window.model_cancel_button.cget("state")) == "disabled"

        with capture_settings._window(
            runtime,
            model_state="installed",
            visible=False,
        ) as window:
            capture_settings._stage_model(window, runtime, "model-installed")
            assert window.status.get() == saved
            assert window.model_status.get() == (
                "Small English\n"
                "English-only speech recognition.\n"
                "Installed — required files found locally. Loading has not been tested."
            )
            assert "small.en" not in window.model_status.get()
            assert "ctranslate2" not in window.model_status.get()
            assert "CPU / NVIDIA" not in window.model_status.get()
            assert (
                window.model_action_status.get()
                == capture_settings.MODEL_INSTALLED_ACTION
            )

        with capture_settings._window(
            runtime,
            model_state="incomplete",
            visible=False,
        ) as window:
            dialogs_before = len(runtime.dialogs)
            capture_settings._stage_model(window, runtime, "model-error")
            assert window.status.get() == saved
            assert window.model_action_status.get() == capture_settings.MODEL_ERROR_ACTION
            assert (
                capture_settings.MODEL_ERROR_DETAIL
                not in window.model_action_status.get()
            )
            assert "small.en" not in window.model_status.get()
            assert "ctranslate2" not in window.model_status.get()
            assert "CPU / NVIDIA" not in window.model_status.get()
            assert window.model_info_button.cget("text") == "Model details…"
            assert window.model_info_button.winfo_manager() == "pack"
            assert str(window.model_details_button.cget("state")) == "normal"
            assert window.model_details_button.cget("text") == (
                "Download error details…"
            )
            assert window.model_details_button.winfo_manager() == "pack"
            assert all(
                capture_settings.MODEL_ERROR_DETAIL not in dialog[2]
                for dialog in runtime.dialogs[dialogs_before:]
            )

            window.model_info_button.invoke()
            assert runtime.dialogs[-1][:2] == (
                "info",
                "Selected speech model details",
            )
            assert "Model: Small English" in runtime.dialogs[-1][2]
            assert "Identifier: small.en" in runtime.dialogs[-1][2]
            assert "Backend: ctranslate2" in runtime.dialogs[-1][2]

            window.model_details_button.invoke()
            assert runtime.dialogs[-1][:2] == ("info", "Model download details")
            assert runtime.dialogs[-1][2].endswith(
                "RuntimeError: " + capture_settings.MODEL_ERROR_DETAIL
            )

            capture_settings._stage_model(window, runtime, "model-installed")
            assert window.error_details[window.model_details_button] == ""
            assert str(window.model_details_button.cget("state")) == "disabled"
            assert window.model_details_button.winfo_manager() == ""
            assert window.model_info_button.winfo_manager() == "pack"

        with capture_settings._window(runtime, visible=False) as window:
            commands_before = len(runtime.ipc_commands)
            calls_before = len(runtime.ipc_calls)
            expected_calls = []
            for reply, expected in capture_settings.STATUS_EXPECTATIONS.items():
                assert (
                    capture_settings._stage_app_status(window, runtime, reply)
                    == expected
                )
                expected_calls.append(("status-detail", {"exact_reply": True}))
                if reply == "unknown":
                    expected_calls.append(("status", {}))
            restart_message = capture_settings._stage_app_status(
                window,
                runtime,
                "restart-required",
            )
            assert "running" not in restart_message.lower()
            malformed_message = capture_settings._stage_app_status(
                window,
                runtime,
                capture_settings.MALFORMED_STATUS_REPLY,
            )
            assert malformed_message == capture_settings.MALFORMED_STATUS_ACTION
            assert (
                capture_settings.MALFORMED_STATUS_REPLY not in malformed_message
            )
            expected_calls.extend([("status-detail", {"exact_reply": True})] * 2)
            assert runtime.ipc_calls[calls_before:] == expected_calls
            assert runtime.ipc_commands[commands_before:] == [command for command, _kwargs in expected_calls]

        with capture_settings._window(runtime, visible=False) as window:
            capture_settings._stage_save_in_progress(window)
            assert window.saving
            assert window.status.get() == "Saving changes…"
            assert str(window.save_button.cget("state")) == "disabled"
            assert str(window.reset_button.cget("state")) == "disabled"

        with capture_settings._window(runtime, visible=False) as window:
            capture_settings._stage_partial_save(window, runtime)
            assert window.status.get() == "Some changes saved"
            assert runtime.dialogs[-1][0] == "error"
            assert "locked" not in runtime.dialogs[-1][2]
            assert "locked" in window._save_details
            assert window.save_details_button.winfo_manager() == "grid"

        with capture_settings._window(runtime, visible=False) as window:
            capture_settings._stage_invalid_vocabulary(window)
            capture_settings._settle(window.root, cycles=1)
            assert window.status.get() == "Vocabulary line 1: use spoken = written."
            assert window.names.get("sel.first", "sel.last") == "utter leaf Utterleaf"

        with capture_settings._window(runtime, visible=False) as window:
            dialogs_before = len(runtime.dialogs)
            capture_settings._stage_oversized_vocabulary_validation(window)
            capture_settings._settle(window.root, cycles=1)
            assert int(window.names.cget("height")) == 40
            assert window.names.index("insert") == (
                f"{capture_settings.OVERSIZED_VALIDATION_LINE}.0"
            )
            assert window.names.get("sel.first", "sel.last") == (
                "spoken form 75 = replacement 75"
            )
            assert window.status.get() == (
                capture_settings.OVERSIZED_VALIDATION_MESSAGE
            )
            assert runtime.dialogs[dialogs_before:] == [
                (
                    "error",
                    "Check your settings",
                    capture_settings.OVERSIZED_VALIDATION_MESSAGE,
                )
            ]

        changed = Config(
            hotkey="f8", model="base", beep=False, indicator=True, live_preview=True
        )
        with capture_settings._window(
            runtime,
            cfg=changed,
            visible=False,
        ) as window:
            window.vars["device"].set("gpu")
            before = window._snapshot()
            baseline = dict(window.baseline)
            cfg = window.cfg
            capture_settings._stage_feedback_reset(window, runtime)
            assert window.vars["indicator"].get() is Config().indicator
            assert window.vars["live_preview"].get() is Config().live_preview
            assert window.vars["beep"].get() is Config().beep
            assert window.vars["device"].get() == "gpu"
            assert all(
                window._snapshot()[key] == value
                for key, value in before.items()
                if key not in {"indicator", "live_preview", "beep"}
            )
            assert window.cfg is cfg and window.baseline == baseline
            assert not window._reset_pending and not window._resetting_feedback
            assert window.status.get() == (
                "Recording feedback defaults ready · Save changes to apply"
            )

        with capture_settings._window(
            runtime,
            cfg=changed,
            visible=False,
        ) as window:
            capture_settings._stage_reset(window, runtime)
            assert window._reset_pending
            assert window.status.get() == "Defaults ready to review · Save changes to apply"

        # A new scenario starts clean even after dirty, failed, and reset states.
        with capture_settings._window(runtime, visible=False) as window:
            assert window.status.get() == saved
            assert str(window.save_button.cget("state")) == "disabled"
            assert window.vars["beep"].get() is True
            assert window.names.get("1.0", "end-1c") == capture_settings.DEFAULT_VOCABULARY
