"""Recovery transitions exercise real Tk controls with all external edges held."""

from contextlib import contextmanager
from pathlib import Path
import tkinter as tk
from unittest.mock import patch

import pytest

from test_capture_auxiliary import capture_auxiliary
from utterleaf import file_decoder_ui, file_ui
from utterleaf.config import Config
from utterleaf.ui_feedback import technical_details


RAW_ERROR = "Synthetic private/path/東京\x00\u202e: decoder permission detail"


@contextmanager
def opened_surface(kind="file", scale=1.0):
    with capture_auxiliary.blocked_runtime() as runtime, \
            capture_auxiliary.owned_root(scale) as (owner, errors):
        owner.deiconify()
        owner.update()
        # Keep the owner alive until owned_root restores Tk's process-wide scale.
        window = (file_ui.FileWindow(tk.Toplevel(owner), Config()) if kind == "file"
                  else file_decoder_ui.DecoderDialog(owner))
        try:
            yield window, runtime
        finally:
            if kind == "file":
                window.close()
            elif window.root.winfo_exists():
                window.root.destroy()
        assert not errors, errors
        assert not runtime.violations


def file_error(window, runtime):
    runtime.open_path = "Synthetic speech.wav"
    window.choose()
    window.start()
    window.events.put(("error", RAW_ERROR))
    capture_auxiliary.file_events(window)


def assert_no_details(window):
    assert window.feedback.details == window.feedback.problem == ""
    assert not window.feedback.details_button.winfo_ismapped()
    assert window.feedback.details_button.instate(["disabled"])


def test_file_failure_keeps_safe_copy_and_retry_clears_obsolete_details():
    with opened_surface() as (window, runtime):
        file_error(window, runtime)
        assert "Couldn't transcribe this file" in window.status.get()
        assert "No transcript is available" in window.status.get()
        assert "Transcribe to retry" in window.status.get()
        assert "private/path" not in window.status.get()
        assert window.feedback.details == technical_details(RAW_ERROR)
        assert runtime.dialogs == []
        assert window.result is None
        assert not window.busy
        assert window.export_button.instate(["disabled"])
        window.feedback.details_button.invoke()
        assert runtime.dialogs[-1][1] == technical_details(RAW_ERROR)

        window.start()
        assert window.busy
        assert_no_details(window)
        assert runtime.threads == ["utterleaf-file", "utterleaf-file"]
        window.events.put(("progress", ("recognizing", 0.4)))
        capture_auxiliary.file_events(window)
        assert "Recognizing" in window.status.get()
        assert_no_details(window)


def test_cancelled_retry_drops_late_error_and_does_not_restore_details():
    with opened_surface() as (window, runtime):
        file_error(window, runtime)
        window.start()
        window.cancel()
        window.events.put(("error", RAW_ERROR))
        capture_auxiliary.file_events(window)
        assert "Cancelled" in window.status.get()
        assert not window.busy
        assert window.result is None
        assert_no_details(window)
        assert runtime.dialogs == []


@pytest.mark.parametrize("action", ["discard", "choose"])
def test_file_discard_or_new_file_clears_details(action):
    with opened_surface() as (window, runtime):
        file_error(window, runtime)
        runtime.open_path = "Another synthetic file.wav"
        getattr(window, action)()
        assert_no_details(window)
        assert window.result is None
        if action == "choose":
            assert window.path == Path(runtime.open_path)
        assert runtime.dialogs == []


def test_file_close_clears_details_and_rejects_queued_late_errors():
    with opened_surface() as (window, runtime):
        file_error(window, runtime)
        feedback = window.feedback
        pending = window.events
        window.close()
        pending.put(("error", RAW_ERROR))
        window.poll()
        assert feedback.details == feedback.problem == ""
        assert window.events.empty()
        assert window.cancel_event.is_set()
        feedback.show_details()
        assert runtime.dialogs == []


@pytest.mark.parametrize("replace_existing", [False, True])
def test_export_failure_retains_preview_and_reports_uncertain_destination(replace_existing, tmp_path):
    with opened_surface() as (window, runtime):
        capture_auxiliary.stage_file(window, runtime, "result")
        original_result = window.result
        original_text = window.preview.get("1.0", "end-1c")
        window.preview.tag_add("sel", "1.0", "1.9")
        runtime.save_path = str(tmp_path / "Synthetic transcript.txt")
        runtime.confirm = replace_existing
        outcomes = ([FileExistsError("already exists")] if replace_existing else []) + [OSError(RAW_ERROR)]
        with patch.object(file_ui, "export_transcript", side_effect=outcomes) as export:
            window.export()
        assert export.call_count == (2 if replace_existing else 1)
        if replace_existing:
            assert export.call_args.kwargs["overwrite"] is True
        assert window.result is original_result
        assert window.preview.get("1.0", "end-1c") == original_text
        assert tuple(map(str, window.preview.tag_ranges("sel"))) == ("1.0", "1.9")
        assert str(window.preview.cget("state")) == "disabled"
        assert not window.export_button.instate(["disabled"])
        assert "Your preview is still available" in window.status.get()
        assert "Check the destination file" in window.status.get()
        assert "nothing" not in window.status.get().lower()
        assert "private/path" not in window.status.get()
        assert window.feedback.details == technical_details(RAW_ERROR)
        assert runtime.dialogs == []
        assert list(tmp_path.iterdir()) == []

        with patch.object(file_ui, "export_transcript") as export:
            window.export()
        export.assert_called_once()
        assert "Exported TXT" in window.status.get()
        assert_no_details(window)
        assert window.result is original_result


def test_decoder_picker_and_trust_cancellation_never_select_a_program():
    with opened_surface("decoder") as (dialog, runtime):
        with patch.object(file_decoder_ui, "select_decoder") as select, \
                patch.object(file_decoder_ui.messagebox, "askyesno", return_value=False) as consent:
            dialog.choose()
            consent.assert_not_called()
            runtime.open_path = "Synthetic trusted-tools/ffmpeg.exe"
            dialog.choose()
            consent.assert_called_once()
            assert "trusted source" in consent.call_args.args[1]
            select.assert_not_called()
        assert "No FFmpeg selected" in dialog.status.get()
        assert_no_details(dialog)
        assert runtime.dialogs == []


@pytest.mark.parametrize("failure", [OSError, FileExistsError])
def test_export_destination_validation_failure_preserves_preview_without_writing(failure, tmp_path):
    with opened_surface() as (window, runtime):
        capture_auxiliary.stage_file(window, runtime, "result")
        result = window.result
        preview = window.preview.get("1.0", "end-1c")
        runtime.save_path = str(tmp_path / "Synthetic transcript.txt")
        with patch.object(Path, "resolve", side_effect=failure(RAW_ERROR)), \
                patch.object(file_ui, "export_transcript") as export, \
                patch.object(file_ui.messagebox, "askyesno") as consent:
            window.export()
        export.assert_not_called()
        consent.assert_not_called()
        assert window.result is result
        assert window.preview.get("1.0", "end-1c") == preview
        assert "Your preview is still available" in window.status.get()
        assert "Check the destination file" in window.status.get()
        assert "private/path" not in window.status.get()
        assert window.feedback.details == technical_details(RAW_ERROR)
        assert runtime.dialogs == []
        assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("operation", ["refresh", "choose", "forget", "download"])
def test_decoder_failures_keep_raw_context_out_of_primary_copy(operation):
    with opened_surface("decoder") as (dialog, runtime):
        runtime.decoder = {"path": "Synthetic trusted-tools/ffmpeg.exe"}
        dialog.refresh()
        selected = dict(runtime.decoder)
        if operation == "refresh":
            runtime.decoder = RuntimeError(RAW_ERROR)
            dialog.refresh()
            runtime.decoder = selected
        elif operation == "choose":
            runtime.open_path = "Synthetic other-tools/ffmpeg.exe"
            runtime.confirm = True
            with patch.object(file_decoder_ui, "select_decoder", side_effect=RuntimeError(RAW_ERROR)) as select:
                dialog.choose()
            select.assert_called_once_with(runtime.open_path)
            assert "Verify the installation and publisher checksum" in dialog.status.get()
        elif operation == "forget":
            with patch.object(file_decoder_ui, "forget_decoder", side_effect=OSError(RAW_ERROR)):
                dialog.forget()
            assert "could not confirm" in dialog.status.get()
        else:
            with patch.object(file_decoder_ui.webbrowser, "open", side_effect=OSError(RAW_ERROR)) as browser:
                dialog.download_page()
            browser.assert_called_once_with(file_decoder_ui.DOWNLOAD_URL)
            assert file_decoder_ui.DOWNLOAD_URL in dialog.status.get()
        assert "Couldn't" in dialog.status.get()
        assert "private/path" not in dialog.status.get()
        assert dialog.feedback.details == technical_details(RAW_ERROR)
        assert runtime.dialogs == []
        assert runtime.decoder == selected
        dialog.feedback.details_button.invoke()
        assert runtime.dialogs[-1][1] == technical_details(RAW_ERROR)
        dialog.refresh()
        assert "Selected: ffmpeg.exe" in dialog.status.get()
        assert_no_details(dialog)


def test_decoder_browser_refusal_is_visible_without_selecting_anything():
    with opened_surface("decoder") as (dialog, runtime):
        with patch.object(file_decoder_ui.webbrowser, "open", return_value=False):
            dialog.download_page()
        assert "Couldn't open download page" in dialog.status.get()
        assert "browser did not accept" in dialog.feedback.details
        assert runtime.decoder is None
        assert runtime.dialogs == []


def test_decoder_successful_choose_forget_and_close_clear_old_details():
    with opened_surface("decoder") as (dialog, runtime):
        dialog.feedback.error("Earlier failure", "Setup needs attention.", "Try again.", RAW_ERROR)
        runtime.open_path = "Synthetic trusted-tools/ffmpeg.exe"
        runtime.confirm = True

        def selected(name):
            runtime.decoder = {"path": name}

        with patch.object(file_decoder_ui, "select_decoder", side_effect=selected) as select:
            dialog.choose()
        select.assert_called_once_with(runtime.open_path)
        assert_no_details(dialog)
        assert "Selected: ffmpeg.exe" in dialog.status.get()
        dialog.feedback.error("Earlier failure", "Setup needs attention.", "Try again.", RAW_ERROR)
        with patch.object(file_decoder_ui, "forget_decoder", side_effect=lambda: setattr(runtime, "decoder", None)):
            dialog.forget()
        assert "No FFmpeg selected" in dialog.status.get()
        assert_no_details(dialog)
        dialog.feedback.error("Earlier failure", "Setup needs attention.", "Try again.", RAW_ERROR)
        dialog.root.destroy()
        assert dialog.feedback.details == dialog.feedback.problem == ""
        dialog.feedback.show_details()
        assert runtime.dialogs == []


@pytest.mark.parametrize("kind", ["file", "decoder"])
@pytest.mark.parametrize("scale", [1.0, 1.5, 2.0])
def test_mapped_failure_reveals_primary_copy_and_details_without_stealing_focus(kind, scale):
    with opened_surface(kind, scale) as (window, runtime):
        size = "760x560" if kind == "file" else "560x500"
        window.root.geometry(size + "+50+40")
        window.root.deiconify()
        window.root.update()
        # Keep focus on a persistent footer action during asynchronous feedback.
        footer = [child for child in window.root.winfo_children()
                  if hasattr(child, "controls")][0]
        footer.controls[-1].focus_force()
        window.root.update()
        focused = window.root.focus_get()
        if kind == "file":
            file_error(window, runtime)
        else:
            runtime.open_path = "Synthetic trusted-tools/ffmpeg.exe"
            runtime.confirm = True
            with patch.object(file_decoder_ui, "select_decoder", side_effect=OSError(RAW_ERROR)):
                window.choose()
        window.root.update()
        assert window.root.focus_get() is focused
        canvas = window.content.canvas
        for widget in (window.feedback.label, window.feedback.details_button):
            assert widget.winfo_ismapped()
            assert widget.winfo_rooty() >= canvas.winfo_rooty()
            assert widget.winfo_rooty() + widget.winfo_height() <= canvas.winfo_rooty() + canvas.winfo_height()
        assert runtime.dialogs == []


@pytest.mark.parametrize("kind", ["file", "decoder"])
@pytest.mark.parametrize("scale", [1.0, 1.5, 2.0])
def test_details_keyboard_focus_reveals_action_after_compact_resize(kind, scale):
    with opened_surface(kind, scale) as (window, runtime):
        if kind == "file":
            file_error(window, runtime)
        else:
            runtime.decoder = RuntimeError(RAW_ERROR)
            window.refresh()
        details = window.feedback.details_button
        minimum = (760, 560) if kind == "file" else (560, 500)
        state = (window.status.get(), window.feedback.details)
        for width, height in (minimum, (1000, 620), minimum):
            window.root.geometry(f"{width}x{height}+50+40")
            window.root.update()
            assert (window.root.winfo_width(), window.root.winfo_height()) == (width, height)
            before = details.tk_focusPrev()
            assert before is not None and before != details
            before.focus_force()
            window.root.update()
            assert window.root.focus_get() == before
            before.event_generate("<Tab>")
            window.root.update()
            assert window.root.focus_get() == details, {
                "size": (width, height), "before": str(before),
                "focused": str(window.root.focus_get()), "expected": str(details),
                "next": str(before.tk_focusNext()), "view": window.content.canvas.yview(),
                "details_y": details.winfo_rooty(), "canvas_y": window.content.canvas.winfo_rooty(),
            }
            canvas = window.content.canvas
            left, top = canvas.winfo_rootx(), canvas.winfo_rooty()
            x, y = details.winfo_rootx(), details.winfo_rooty()
            assert left <= x < x + details.winfo_width() <= left + canvas.winfo_width()
            assert top <= y < y + details.winfo_height() <= top + canvas.winfo_height()
            assert details.winfo_width() >= details.winfo_reqwidth()
            assert details.winfo_height() >= details.winfo_reqheight()
            assert (window.status.get(), window.feedback.details) == state
        assert runtime.dialogs == []
        details.event_generate("<KeyPress-space>")
        details.event_generate("<KeyRelease-space>")
        capture_auxiliary.settle(window.root)
        assert runtime.dialogs == [(window.feedback.problem + " — Details", state[1])]
