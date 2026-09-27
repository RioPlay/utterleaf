"""Deterministic desktop UI baseline; writes screenshots under artifacts only.

Run with ``.venv/Scripts/python.exe tests/capture_settings.py`` from the owning
desktop worktree. Production actions are replaced for the whole run, so the
harness cannot open a microphone, download a model, contact the app, display a
blocking dialog, or save user preferences. Dynamic states are presentation
states: they are visual evidence, not device or end-to-end proof.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable, Iterator
from contextlib import ExitStack, contextmanager
import gc
from pathlib import Path
import sys
import time
import tkinter as tk
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PIL import ImageGrab

from utterleaf.config import Config
from utterleaf.settings import (
    SYSTEM_DEFAULT,
    FormValidationError,
    SettingsSaveError,
)
from utterleaf.settings_ui import SettingsWindow, enable_dpi_awareness


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "artifacts" / "screenshots" / "desktop-baseline"
STANDARD = (960, 780)
COMPACT = (760, 560)
WIDE = (1280, 800)
LARGE_TEXT_SCALE = 2.0
DEFAULT_VOCABULARY = "utter leaf = Utterleaf\nacme = Acme"
STUDIO_MICROPHONE = "Studio USB Microphone"
DEVICE_REFRESH_DETAIL = "Synthetic device enumeration failure"
DEVICE_REFRESH_ERROR_ACTION = (
    "Could not refresh microphones. The device list may be out of date. "
    "Check microphone access, then select Refresh to retry."
)
MICROPHONE_SUCCESS_ACTION = (
    "Audio detected. Microphone check passed; speech model not tested."
)
MICROPHONE_FORMAT_ACTION = (
    "This microphone cannot use the requested audio format. "
    "Choose another input in Settings → Dictation, then try again."
)
MODEL_ERROR_DETAIL = "Synthetic download failure: HTTP 503"

MODEL_INSTALLED_ACTION = (
    "Small English installed. Save changes to use a changed selection; "
    "reopen file transcription to reload its settings."
)
MODEL_ERROR_ACTION = (
    "Download of Small English did not finish. This model may not be available offline. "
    "Check your connection and free disk space, then retry the download."
)
MODEL_DISPLAY_NAME = "Small English"
MODEL_PURPOSE = "English-only speech recognition."
OVERSIZED_VALIDATION_LINE = 75
OVERSIZED_VALIDATION_MESSAGE = (
    "Synthetic capture fixture · Vocabulary line 75 selected after validation."
)
STATUS_EXPECTATIONS = {
    "status-v2:idle:unconfirmed": "Idle · app is running\nLoaded model for applied settings: not confirmed.",
    "status-v2:ready:tiny.en": "Ready · applied speech model loaded\nLoaded model for applied settings: Tiny English.",
    "status-v2:listening:unconfirmed": "Listening · speech capture in progress\nLoaded model for applied settings: not confirmed.",
    "status-v2:processing:unconfirmed": "Processing · preparing or transcribing speech\nLoaded model for applied settings: not confirmed.",
    "status-v2:attention:unconfirmed": "Needs attention · check the tray or open Help\nLoaded model for applied settings: not confirmed.",
    "status-v2:unknown:unconfirmed": "App is running · detailed status unavailable\nLoaded model for applied settings: not confirmed.",
    "unknown": "App is running · detailed status unavailable in this version\nLoaded model details unavailable in this version.",
    "restart-required": "Restart Utterleaf to check its status",
    None: "App not reached · Start Utterleaf, then refresh status",
}
MALFORMED_STATUS_REPLY = "private raw payload: /synthetic/user/dictation.txt"
MALFORMED_STATUS_ACTION = (
    "Could not read app status · restart Utterleaf, then retry"
)
APP_STATUS_CAPTURES = (
    ("app-status-ready.png", "status-v2:ready:tiny.en"),
    ("app-status-listening.png", "status-v2:listening:unconfirmed"),
    ("app-status-processing.png", "status-v2:processing:unconfirmed"),
    ("app-status-attention.png", "status-v2:attention:unconfirmed"),
)

PAGE_SLUGS = (
    ("Dictation", "dictation"),
    ("Vocabulary", "vocabulary"),
    ("Voice commands", "voice-commands"),
    ("Engine", "engine"),
    ("Help & diagnostics", "help-diagnostics"),
)
GUIDE_TABS = ("Tray states", "App badges", "Cutout marks", "Utterling", "Wordmark")
SEARCH_CAPTURES = (
    ("search-initial.png", "", None, False),
    ("search-results.png", "privacy", "restore_clipboard", False),
    ("search-no-results.png", "unmatched setting", None, False),
    ("search-prerequisite.png", "automatic insert", "speech_end_insert", False),
    ("search-compact-text-scale-2x.png", "privacy", "restore_clipboard", True),
    ("search-prerequisite-compact-text-scale-2x.png", "automatic insert", "speech_end_insert", True),
)

CAPTURE_INVENTORY = (
    *(f"page-{slug}-standard.png" for _, slug in PAGE_SLUGS),
    *(f"page-{slug}-lower.png" for _, slug in PAGE_SLUGS),
    "layout-dictation-compact.png",
    "layout-dictation-wide.png",
    *(filename for filename, *_ in SEARCH_CAPTURES),
    "vocabulary-empty.png",
    "vocabulary-oversized-validation-synthetic-post-dialog.png",
    "device-none.png",
    "device-selected-missing.png",
    "device-refresh-error.png",
    "microphone-opening.png",
    "microphone-listening.png",
    "microphone-low-input.png",
    "microphone-ready.png",
    "microphone-error.png",
    "microphone-unsupported-format.png",
    "microphone-unsupported-compact-text-scale-2x-focused.png",
    "model-missing.png",
    "model-incomplete.png",
    "model-downloading.png",
    "model-cancelled.png",
    "model-installed.png",
    "model-error.png",
    "engine-compact-text-scale-2x-synthetic-overview.png",
    "engine-compact-text-scale-2x-synthetic-cancel-focused.png",
    "save-clean.png",
    "save-unsaved.png",
    "save-in-progress.png",
    "save-partial-failure-post-dialog.png",
    "save-invalid-vocabulary-post-dialog.png",
    "recording-feedback-reset-staged.png",
    "reset-staged.png",
    *(filename for filename, _reply in APP_STATUS_CAPTURES),
    "help-app-running.png",
    "help-app-not-running.png",
    *(f"guide-{name.lower().replace(' ', '-')}.png" for name in GUIDE_TABS),
)
# Keep references to the real presentation transitions before the safety guard
# replaces user-invokable actions on SettingsWindow.
_REAL_REFRESH_MICS = SettingsWindow.refresh_mics
_REAL_TEST_MIC = SettingsWindow.test_mic
_REAL_DOWNLOAD_MODEL = SettingsWindow.download_model
_REAL_SAVE = SettingsWindow.save
_REAL_RESTORE_DEFAULTS = SettingsWindow.restore_defaults
_REAL_RESET_RECORDING_FEEDBACK = SettingsWindow.reset_recording_feedback


def _new_root() -> tk.Tk:
    """Retry transient Tcl teardown races while still surfacing a missing Tk install."""
    for attempt in range(3):
        try:
            return tk.Tk()
        except tk.TclError:
            if attempt == 2:
                raise
            gc.collect()
            time.sleep(0.1)
    raise AssertionError("unreachable")


def _settle(root: tk.Misc, cycles: int = 6) -> None:
    """Pump scheduled layout work so captures never record an intermediate frame."""
    for _ in range(cycles):
        root.update()
        time.sleep(0.05)


def _grab(root: tk.Misc, destination: Path) -> tuple[int, int]:
    x, y = root.winfo_rootx(), root.winfo_rooty()
    width, height = root.winfo_width(), root.winfo_height()
    if sys.platform == "win32":
        image = ImageGrab.grab(window=root.winfo_id())
    else:
        image = ImageGrab.grab(bbox=(x, y, x + width, y + height))
    image.save(destination)
    return width, height


def _capture(
    window: SettingsWindow,
    filename: str,
    page: str,
    size: tuple[int, int] = STANDARD,
    *,
    prepare: Callable[[SettingsWindow], None] | None = None,
    scroll_to: float | None = None,
    output: Path = OUTPUT,
) -> Path:
    root = window.root
    root.geometry(f"{size[0]}x{size[1]}+80+60")
    window.show_page(page)
    window.canvas.yview_moveto(0.0)
    _settle(root)
    if prepare is not None:
        prepare(window)
        _settle(root)
    if scroll_to is not None:
        window.canvas.yview_moveto(scroll_to)
        _settle(root, cycles=4)
    destination = output / filename
    width, height = _grab(root, destination)
    if (width, height) != size:
        raise AssertionError(
            f"{filename} requested {size[0]}x{size[1]}, got {width}x{height}"
        )
    print(f"{destination.name}: {page}, {width}x{height}")
    return destination


def _blocked_method(runtime: SimpleNamespace, name: str) -> Callable[..., None]:
    def blocked(_self, *_args, **_kwargs) -> None:
        runtime.blocked_actions.append(name)

    return blocked


@contextmanager
def _blocked_runtime() -> Iterator[SimpleNamespace]:
    """Replace every external or blocking Settings action for the whole run."""
    runtime = SimpleNamespace(
        vocabulary_text=DEFAULT_VOCABULARY,
        model_state="missing",
        ipc_reply=None,
        ipc_commands=[],
        ipc_calls=[],
        blocked_actions=[],
        dialogs=[],
        confirm=False,
        save_error=None,
        scale_receipts=[],
    )

    def inspect_model(name, backend):
        return SimpleNamespace(
            state=runtime.model_state,
            name=name,
            backend=backend,
            path=Path("synthetic-model-location") / name,
            missing=("config.json", "model.bin")
            if runtime.model_state in {"missing", "incomplete"}
            else (),
        )

    def ipc_send(command, **kwargs):
        runtime.ipc_commands.append(command)
        runtime.ipc_calls.append((command, kwargs))
        return runtime.ipc_reply

    def askyesno(title, message, **_kwargs):
        runtime.dialogs.append(("question", title, message))
        return runtime.confirm

    def show_dialog(kind):
        def show(title, message, **_kwargs):
            runtime.dialogs.append((kind, title, str(message)))

        return show

    def apply_form(*_args, **_kwargs):
        if runtime.save_error is not None:
            raise runtime.save_error
        raise AssertionError("The baseline harness blocked a preference write")

    def blocked_download(*_args, **_kwargs):
        raise AssertionError("The baseline harness blocked a model download")

    blocked_window_methods = (
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
    )

    from utterleaf.appearance import AppearanceGuide

    with ExitStack() as stack:
        stack.enter_context(patch("utterleaf.settings_ui.startup_enabled", return_value=False))
        stack.enter_context(
            patch(
                "utterleaf.settings_ui.dictionary_text",
                side_effect=lambda: runtime.vocabulary_text,
            )
        )
        stack.enter_context(
            patch("utterleaf.model_setup.inspect_model", side_effect=inspect_model)
        )
        stack.enter_context(
            patch("utterleaf.model_setup.run_download", side_effect=blocked_download)
        )
        stack.enter_context(patch("utterleaf.settings_ui.load", side_effect=lambda: Config()))
        stack.enter_context(patch("utterleaf.settings_ui.apply_form", side_effect=apply_form))
        stack.enter_context(patch("utterleaf.ipc.send", side_effect=ipc_send))
        stack.enter_context(
            patch("utterleaf.settings_ui.messagebox.askyesno", side_effect=askyesno)
        )
        stack.enter_context(
            patch(
                "utterleaf.settings_ui.messagebox.showerror",
                side_effect=show_dialog("error"),
            )
        )
        stack.enter_context(
            patch(
                "utterleaf.settings_ui.messagebox.showinfo",
                side_effect=show_dialog("info"),
            )
        )
        stack.enter_context(
            patch("utterleaf.settings_ui.filedialog.askopenfilename", return_value="")
        )
        stack.enter_context(
            patch("utterleaf.settings_ui.filedialog.asksaveasfilename", return_value="")
        )
        stack.enter_context(
            patch.object(
                AppearanceGuide,
                "export",
                _blocked_method(runtime, "export_artwork"),
            )
        )
        for name in blocked_window_methods:
            stack.enter_context(
                patch.object(SettingsWindow, name, _blocked_method(runtime, name))
            )
        yield runtime


@contextmanager
def _window(
    runtime: SimpleNamespace,
    *,
    cfg: Config | None = None,
    vocabulary_text: str = DEFAULT_VOCABULARY,
    model_state: str = "missing",
    visible: bool = True,
    text_scale: float | None = None,
) -> Iterator[SettingsWindow]:
    """Create one isolated, saved Settings state and always release its Tk root."""
    runtime.vocabulary_text = vocabulary_text
    runtime.model_state = model_state
    root: tk.Tk | None = None
    window: SettingsWindow | None = None
    baseline_scale: float | None = None
    active_scale: float | None = None
    try:
        root = _new_root()
        if text_scale is not None:
            if text_scale <= 0:
                raise ValueError("text_scale must be positive")
            baseline_scale = float(root.tk.call("tk", "scaling"))
            root.tk.call("tk", "scaling", baseline_scale * text_scale)
            active_scale = float(root.tk.call("tk", "scaling"))
        if not visible:
            root.withdraw()
        window = SettingsWindow(root, cfg or Config(), background=False)
        if visible:
            root.attributes("-topmost", True)
        yield window
    finally:
        if window is not None and not window.closed:
            guide = window.appearance_guide
            if guide is not None:
                try:
                    if guide.root.winfo_exists():
                        guide.close()
                except tk.TclError:
                    pass
                window.appearance_guide = None
            window.saving = False
            window.model_downloading = False
            window._reset_pending = False
            try:
                window.baseline = window._snapshot()
                if baseline_scale is not None:
                    root.tk.call("tk", "scaling", baseline_scale)
                    runtime.scale_receipts.append(
                        (
                            text_scale,
                            baseline_scale,
                            active_scale,
                            float(root.tk.call("tk", "scaling")),
                        )
                    )
                    baseline_scale = None
                window.close()
            except tk.TclError:
                pass
        if root is not None:
            try:
                if root.winfo_exists():
                    if baseline_scale is not None:
                        root.tk.call("tk", "scaling", baseline_scale)
                        runtime.scale_receipts.append(
                            (
                                text_scale,
                                baseline_scale,
                                active_scale,
                                float(root.tk.call("tk", "scaling")),
                            )
                        )
                    root.destroy()
            except tk.TclError:
                pass


def _capture_guide(
    window: SettingsWindow,
    captured: list[str],
    output: Path = OUTPUT,
) -> None:
    guide = None
    try:
        window.show_appearance()
        guide = window.appearance_guide
        for tab_name in GUIDE_TABS:
            index = list(guide.canvases).index(tab_name)
            guide.tabs.select(index)
            _settle(guide.root, cycles=4)
            destination = output / (
                "guide-" + tab_name.lower().replace(" ", "-") + ".png"
            )
            _grab(guide.root, destination)
            captured.append(destination.name)
    finally:
        if guide is not None:
            try:
                if guide.root.winfo_exists():
                    guide.close()
            except tk.TclError:
                pass
        window.appearance_guide = None


def _capture_worker_callback(window: SettingsWindow, action: Callable[[], None]) -> Callable:
    callbacks = []
    window._worker = lambda _work, done, **_kwargs: callbacks.append(done)
    action()
    if len(callbacks) != 1:
        raise AssertionError("Expected exactly one staged Settings worker callback")
    return callbacks[0]


def _stage_device_refresh(
    window: SettingsWindow,
    result: list[str] | Exception,
) -> None:
    done = _capture_worker_callback(window, lambda: _REAL_REFRESH_MICS(window))
    done(result)


def _stage_microphone(window: SettingsWindow, phase: str) -> None:
    window.mic_box.configure(values=(SYSTEM_DEFAULT, STUDIO_MICROPHONE))
    done = _capture_worker_callback(window, lambda: _REAL_TEST_MIC(window))
    if phase == "opening":
        return
    window._mic_check_listening()
    if phase == "listening":
        window.meter.configure(value=42)
        return
    if phase == "low-input":
        done(0.0)
    elif phase == "ready":
        done(0.1)
    elif phase == "error":
        from utterleaf.audio import SelectedMicrophoneUnavailable

        done(SelectedMicrophoneUnavailable("Selected microphone is unavailable"))
    elif phase == "unsupported-format":
        from sounddevice import PortAudioError

        done(PortAudioError("Synthetic unsupported microphone configuration", -9997))
    else:  # pragma: no cover - capture inventory controls the phases
        raise ValueError(phase)


def _stage_model(window: SettingsWindow, runtime: SimpleNamespace, name: str) -> None:
    initial_state = "incomplete" if name == "model-incomplete" else "missing"
    runtime.model_state = initial_state
    window.model_downloading = False
    window.refresh_model_status()
    if name in {"model-missing", "model-incomplete"}:
        return

    callbacks = []
    window._worker = lambda _action, done, **_kwargs: callbacks.append(done)
    runtime.confirm = True
    try:
        _REAL_DOWNLOAD_MODEL(window)
    finally:
        runtime.confirm = False
    if len(callbacks) != 1:
        raise AssertionError("Expected one staged model-download callback")
    if name == "model-downloading":
        return

    done = callbacks[0]
    if name == "model-cancelled":
        runtime.model_state = "incomplete"
        window.cancel_model_download()
        done(RuntimeError("Download cancelled"))
    elif name == "model-installed":
        runtime.model_state = "installed"
        done(None)
    elif name == "model-error":
        runtime.model_state = "incomplete"
        done(RuntimeError(MODEL_ERROR_DETAIL))
    else:  # pragma: no cover - capture inventory controls the states
        raise ValueError(name)


def _focus_model_cancel(window: SettingsWindow) -> None:
    """Use the production FocusIn reveal path for the staged Cancel action."""

    window.model_cancel_button.focus_force()


def _sync_worker(action, done, **_kwargs) -> None:
    try:
        result = action()
    except Exception as exc:  # Production _worker forwards exceptions to done.
        result = exc
    done(result)


def _stage_save_in_progress(window: SettingsWindow) -> None:
    window.vars["beep"].set(not window.vars["beep"].get())
    window._worker = lambda _action, _done, **_kwargs: None
    _REAL_SAVE(window)


def _stage_partial_save(window: SettingsWindow, runtime: SimpleNamespace) -> None:
    window.vars["beep"].set(not window.vars["beep"].get())
    runtime.save_error = SettingsSaveError(
        ["dictation settings"],
        "vocabulary",
        ["start at login"],
        OSError("locked"),
    )
    window._worker = _sync_worker
    try:
        _REAL_SAVE(window)
    finally:
        runtime.save_error = None


def _stage_invalid_vocabulary(window: SettingsWindow) -> None:
    window.names.delete("1.0", "end")
    window.names.insert("1.0", "utter leaf Utterleaf\nacme = Acme")
    # Let <<Modified>> finish its ordinary dirty-state transition before the
    # production validation callback applies the durable post-dialog state.
    _settle(window.root, cycles=2)
    window._show_invalid_field(
        FormValidationError(
            "names",
            "Vocabulary line 1: use spoken = written.",
            line=1,
        )
    )


def _stage_oversized_vocabulary_validation(window: SettingsWindow) -> None:
    """Force the compact accessibility case without a native dialog."""

    window.names.configure(height=40)
    window.names.delete("1.0", "end")
    window.names.insert(
        "1.0",
        "\n".join(
            f"spoken form {line} = replacement {line}" for line in range(1, 81)
        ),
    )
    # Settle the ordinary dirty transition before the production callback
    # selects and reveals the deliberately lower validation line.
    _settle(window.root, cycles=2)
    window._show_invalid_field(
        FormValidationError(
            "names",
            OVERSIZED_VALIDATION_MESSAGE,
            line=OVERSIZED_VALIDATION_LINE,
        )
    )


def _stage_reset(window: SettingsWindow, runtime: SimpleNamespace) -> None:
    runtime.confirm = True
    try:
        _REAL_RESTORE_DEFAULTS(window)
    finally:
        runtime.confirm = False


def _stage_feedback_reset(window: SettingsWindow, runtime: SimpleNamespace) -> None:
    """Stage the production section reset while retaining unrelated drafts."""
    before = window._snapshot()
    runtime.confirm = True
    try:
        _REAL_RESET_RECORDING_FEEDBACK(window)
    finally:
        runtime.confirm = False
    after = window._snapshot()
    feedback = {"indicator", "live_preview", "beep"}
    if any(after[key] != before[key] for key in before if key not in feedback):
        raise AssertionError("Recording feedback reset changed an unrelated draft")


def _stage_app_status(
    window: SettingsWindow,
    runtime: SimpleNamespace,
    reply: str | None,
) -> str:
    runtime.ipc_reply = reply
    command_count = len(runtime.ipc_commands)
    call_count = len(runtime.ipc_calls)
    message = window._connection_status()
    commands = runtime.ipc_commands[command_count:]
    expected = [("status-detail", {"exact_reply": True})]
    if reply == "unknown":
        expected.append(("status", {}))
    if commands != [command for command, _kwargs in expected] or runtime.ipc_calls[call_count:] != expected:
        raise AssertionError(f"Unexpected snapshot query sequence: {runtime.ipc_calls[call_count:]!r}")
    window.connection.set(message)
    return message


def _record(captured: list[str], path: Path) -> None:
    captured.append(path.name)


def _stage_search(window: SettingsWindow, query: str, key: str | None) -> None:
    """Use the production search, indexing only its static product terminology."""
    window.open_search()
    window.search_query.set(query)
    if key is not None:
        index = next(index for index, target in enumerate(window.search_matches) if target.key == key)
        window.search_results.selection_clear(0, "end")
        window.search_results.selection_set(index)
        window.search_results.activate(index)
        window.search_results.see(index)
        window._search_selection()
        window.search_results.focus_force()


def main(output: Path = OUTPUT) -> None:
    output.mkdir(parents=True, exist_ok=True)
    enable_dpi_awareness()
    captured: list[str] = []

    def capture(*args, **kwargs) -> Path:
        return _capture(*args, output=output, **kwargs)

    with _blocked_runtime() as runtime:
        # Real steady pages, lower-page coverage, and the three review widths.
        with _window(runtime) as window:
            for page, slug in PAGE_SLUGS:
                _record(captured, capture(window, f"page-{slug}-standard.png", page))
            for page, slug in PAGE_SLUGS:
                _record(
                    captured,
                    capture(
                        window,
                        f"page-{slug}-lower.png",
                        page,
                        scroll_to=1.0,
                    ),
                )
            _record(
                captured,
                capture(
                    window,
                    "layout-dictation-compact.png",
                    "Dictation",
                    COMPACT,
                ),
            )
            _record(
                captured,
                capture(
                    window,
                    "layout-dictation-wide.png",
                    "Dictation",
                    WIDE,
                ),
            )

        for filename, query, key, large in SEARCH_CAPTURES:
            with _window(runtime, text_scale=LARGE_TEXT_SCALE if large else None) as window:
                _record(captured, capture(
                    window, filename, "Dictation", COMPACT if large else STANDARD,
                    prepare=lambda state, text=query, target=key: _stage_search(state, text, target),
                ))

        with _window(runtime, vocabulary_text="") as window:
            _record(
                captured,
                capture(window, "vocabulary-empty.png", "Vocabulary"),
            )

        with _window(runtime) as window:
            _record(
                captured,
                capture(
                    window,
                    "vocabulary-oversized-validation-synthetic-post-dialog.png",
                    "Vocabulary",
                    COMPACT,
                    prepare=_stage_oversized_vocabulary_validation,
                ),
            )

        with _window(runtime) as window:
            _stage_device_refresh(window, [])
            _record(captured, capture(window, "device-none.png", "Dictation"))

        with _window(runtime, cfg=Config(microphone=STUDIO_MICROPHONE)) as window:
            _stage_device_refresh(window, ["Laptop microphone"])
            _record(
                captured,
                capture(window, "device-selected-missing.png", "Dictation"),
            )

        with _window(runtime) as window:
            _stage_device_refresh(window, RuntimeError(DEVICE_REFRESH_DETAIL))
            _record(
                captured,
                capture(window, "device-refresh-error.png", "Dictation"),
            )

        microphone_captures = (
            ("microphone-opening.png", "opening"),
            ("microphone-listening.png", "listening"),
            ("microphone-low-input.png", "low-input"),
            ("microphone-ready.png", "ready"),
            ("microphone-error.png", "error"),
            ("microphone-unsupported-format.png", "unsupported-format"),
        )
        for filename, phase in microphone_captures:
            with _window(
                runtime,
                cfg=Config(microphone=STUDIO_MICROPHONE),
            ) as window:
                _stage_microphone(window, phase)
                _record(captured, capture(window, filename, "Dictation"))

        with _window(runtime, text_scale=LARGE_TEXT_SCALE,
                     cfg=Config(microphone=STUDIO_MICROPHONE)) as window:
            _stage_microphone(window, "unsupported-format")
            _record(captured, capture(
                window, "microphone-unsupported-compact-text-scale-2x-focused.png",
                "Dictation", COMPACT,
                prepare=lambda state: state.mic_details_button.focus_force(),
            ))

        for name in (
            "model-missing",
            "model-incomplete",
            "model-downloading",
            "model-cancelled",
            "model-installed",
            "model-error",
        ):
            model_state = {
                "model-missing": "missing",
                "model-incomplete": "incomplete",
                "model-downloading": "missing",
                "model-cancelled": "incomplete",
                "model-installed": "installed",
                "model-error": "incomplete",
            }[name]
            with _window(runtime, model_state=model_state) as window:
                _stage_model(window, runtime, name)
                _record(captured, capture(window, f"{name}.png", "Engine"))

        for filename, focus_cancel in (
            ("engine-compact-text-scale-2x-synthetic-overview.png", False),
            ("engine-compact-text-scale-2x-synthetic-cancel-focused.png", True),
        ):
            with _window(runtime, text_scale=LARGE_TEXT_SCALE) as window:
                # This holds the production completion callback without starting
                # its worker; all download and network entry points remain blocked.
                _stage_model(window, runtime, "model-downloading")
                _record(
                    captured,
                    capture(
                        window,
                        filename,
                        "Engine",
                        COMPACT,
                        prepare=_focus_model_cancel if focus_cancel else None,
                    ),
                )

        with _window(runtime) as window:
            _record(captured, capture(window, "save-clean.png", "Dictation"))

        with _window(runtime) as window:
            _record(
                captured,
                capture(
                    window,
                    "save-unsaved.png",
                    "Dictation",
                    prepare=lambda state: state.vars["beep"].set(
                        not state.vars["beep"].get()
                    ),
                ),
            )

        with _window(runtime) as window:
            _record(
                captured,
                capture(
                    window,
                    "save-in-progress.png",
                    "Dictation",
                    prepare=_stage_save_in_progress,
                ),
            )

        with _window(runtime) as window:
            _record(
                captured,
                capture(
                    window,
                    "save-partial-failure-post-dialog.png",
                    "Dictation",
                    prepare=lambda state: _stage_partial_save(state, runtime),
                ),
            )

        with _window(runtime) as window:
            _record(
                captured,
                capture(
                    window,
                    "save-invalid-vocabulary-post-dialog.png",
                    "Vocabulary",
                    prepare=_stage_invalid_vocabulary,
                ),
            )

        changed = Config(
            hotkey="f8",
            model="base",
            device="cpu",
            language="es",
            beep=False,
            indicator=True,
            live_preview=True,
        )
        with _window(runtime, cfg=changed) as window:
            _record(
                captured,
                capture(
                    window,
                    "recording-feedback-reset-staged.png",
                    "Dictation",
                    prepare=lambda state: _stage_feedback_reset(state, runtime),
                    scroll_to=1.0,
                ),
            )

        with _window(runtime, cfg=changed) as window:
            _record(
                captured,
                capture(
                    window,
                    "reset-staged.png",
                    "Help & diagnostics",
                    prepare=lambda state: _stage_reset(state, runtime),
                ),
            )

        for filename, reply in APP_STATUS_CAPTURES:
            with _window(runtime) as window:
                _stage_app_status(window, runtime, reply)
                _record(captured, capture(window, filename, "Dictation"))

        for filename, reply in (
            ("help-app-running.png", "status-v2:idle:unconfirmed"),
            ("help-app-not-running.png", None),
        ):
            with _window(runtime) as window:
                _stage_app_status(window, runtime, reply)
                _record(
                    captured,
                    capture(window, filename, "Help & diagnostics"),
                )

        with _window(runtime) as window:
            _capture_guide(window, captured, output)

    if tuple(captured) != CAPTURE_INVENTORY:
        raise AssertionError(
            "Capture inventory drifted:\n"
            f"expected {CAPTURE_INVENTORY!r}\n"
            f"captured {tuple(captured)!r}"
        )
    print(f"Captured {len(captured)} desktop baseline images in {output}")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=OUTPUT,
        help="candidate screenshot directory (default: historical baseline directory)",
    )
    return parser.parse_args()


if __name__ == "__main__":
    main(_parse_args().output)
