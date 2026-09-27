"""Keep synthetic auxiliary captures deterministic and free of external actions."""

from contextlib import contextmanager
import importlib.util
import json
from pathlib import Path
from pkgutil import resolve_name
import subprocess
import sys
import threading
import tkinter as tk
from types import SimpleNamespace
from unittest.mock import Mock

import pytest


SOURCE = Path(__file__).with_name("capture_auxiliary.py")
SPEC = importlib.util.spec_from_file_location("utterleaf_capture_auxiliary", SOURCE)
assert SPEC is not None and SPEC.loader is not None
capture_auxiliary = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(capture_auxiliary)


@pytest.fixture(scope="module")
def working_tk_display():
    probe = subprocess.run(
        [sys.executable, "-c", "import tkinter as tk; r=tk.Tk(); r.withdraw(); r.destroy()"],
        capture_output=True, text=True, timeout=10, check=False,
    )
    if probe.returncode:
        pytest.skip(f"Tk needs a working display: {probe.stderr.strip()}")


def descendants(widget):
    for child in widget.winfo_children():
        yield child
        yield from descendants(child)


def test_inventory_is_explicit_unique_and_presentation_only():
    inventory = capture_auxiliary.INVENTORY
    assert len(inventory) == len(set(inventory)) == 21
    assert inventory[:10] == tuple(f"file-{state}.png" for state in capture_auxiliary.FILE_STATES)
    assert set(inventory[10:]) == {
        "file-result-compact-text-2x.png", "decoder-none.png", "decoder-selected.png",
        "decoder-error.png", "decoder-compact-text-2x.png", "review-insert.png",
        "review-copy-only.png", "review-compact.png", "review-compact-text-2x.png",
        "file-error-compact-text-2x.png", "decoder-error-compact-text-2x.png",
    }


def test_guard_holds_expected_worker_targets_and_rejects_other_workers():
    called = []
    with capture_auxiliary.blocked_runtime() as runtime:
        for name in ("utterleaf-file", "utterleaf-review-control"):
            threading.Thread(target=lambda: called.append(True), name=name).start()
        assert runtime.threads == ["utterleaf-file", "utterleaf-review-control"]
        assert called == []
        with pytest.raises(AssertionError, match="unexpected worker"):
            threading.Thread(target=lambda: called.append(True), name="unexpected").start()
        assert runtime.violations == ["unexpected worker"]
        assert called == []


def test_guard_blocks_aliases_and_underlying_external_boundaries():
    targets = (
        "utterleaf.file_ui.transcribe_file", "utterleaf.file_ui._work",
        "utterleaf.file_transcription.transcribe_file", "utterleaf.transcript.export_transcript",
        "utterleaf.file_decoder.decoder_selection", "utterleaf.file_decoder.select_decoder",
        "utterleaf.file_decoder.forget_decoder", "utterleaf.file_decoder_ui.select_decoder",
        "utterleaf.file_decoder_ui.forget_decoder", "utterleaf.config.load", "utterleaf.config.save",
        "utterleaf.settings.launch_settings", "subprocess.Popen", "webbrowser.open",
        "socket.socket", "socket.create_connection", "tkinter.Misc.clipboard_clear",
        "tkinter.Misc.clipboard_append",
    )
    with capture_auxiliary.blocked_runtime() as runtime:
        for target in targets:
            with pytest.raises(AssertionError, match="Auxiliary capture blocked"):
                resolve_name(target)()
        assert runtime.violations == list(targets)
        assert runtime.threads == []


def test_export_is_intercepted_and_requires_a_staged_failure():
    with capture_auxiliary.blocked_runtime() as runtime:
        with pytest.raises(AssertionError, match="unstaged export"):
            capture_auxiliary.file_ui.export_transcript("synthetic.txt", "sample")
        runtime.export_error = OSError("Synthetic destination failure")
        with pytest.raises(OSError, match="Synthetic destination failure"):
            capture_auxiliary.file_ui.export_transcript("synthetic.txt", "sample")
        assert len(runtime.exports) == 2
        assert runtime.exports[0] == (("synthetic.txt", "sample"), {})
        assert runtime.violations == ["unstaged export"]


@pytest.mark.parametrize("state", capture_auxiliary.FILE_STATES)
def test_file_states_use_production_transitions_without_running_work(state, working_tk_display, monkeypatch):
    with capture_auxiliary.blocked_runtime() as runtime, capture_auxiliary.owned_root() as (root, errors):
        window = capture_auxiliary.file_ui.FileWindow(root, capture_auxiliary.Config())
        initial_poll = window.poll_id
        methods = {}
        for name in ("choose", "start", "cancel", "poll", "export"):
            methods[name] = Mock(wraps=getattr(window, name))
            monkeypatch.setattr(window, name, methods[name])
        capture_auxiliary.stage_file(window, runtime, state)

        started = state not in {"empty", "selected"}
        assert methods["choose"].call_count == int(state != "empty")
        assert methods["start"].call_count == int(started)
        assert methods["cancel"].call_count == int(state in {"cancelling", "cancelled"})
        assert methods["poll"].call_count == int(state not in {"empty", "selected", "opening"})
        assert methods["export"].call_count == int(state == "export-error")
        assert runtime.threads == (["utterleaf-file"] if started else [])
        assert window.busy == (state in {"opening", "recognizing", "cancelling"})
        assert window.events.empty()
        timers = root.tk.call("after", "info")
        assert window.poll_id in timers
        if methods["poll"].called:
            assert initial_poll not in timers  # The drain replaces, not duplicates, its timer.
        assert not errors and not runtime.violations

        text = window.preview.get("1.0", "end").strip()
        if state in {"result", "export-error"}:
            assert window.result == capture_auxiliary.SAMPLE_RESULT
            assert text == capture_auxiliary.SAMPLE_TEXT
        else:
            assert text == ""
        if state in {"cancelling", "cancelled"}:
            assert window.cancel_event.is_set()
        if state == "cancelled":
            assert "Cancelled" in window.status.get()
        if state == "error":
            assert "Couldn't transcribe this file" in window.status.get()
            assert "Synthetic failure" not in window.status.get()
            assert "Synthetic failure" in window.feedback.details
        if state == "export-error":
            assert len(runtime.exports) == 1
            assert "Couldn't export transcript" in window.status.get()
            assert "Synthetic destination" not in window.status.get()
            assert "Synthetic destination" in window.feedback.details
        else:
            assert runtime.exports == []


def test_unknown_file_state_is_rejected_before_touching_window():
    with capture_auxiliary.blocked_runtime() as runtime:
        with pytest.raises(ValueError, match="unknown"):
            capture_auxiliary.stage_file(object(), runtime, "unknown")
        assert runtime.threads == runtime.exports == runtime.violations == []


@pytest.mark.parametrize("selection", [None, {"path": "synthetic-tools/ffmpeg.exe"},
                                       RuntimeError("Synthetic stale selection")])
def test_decoder_constructor_uses_only_staged_selection(selection, working_tk_display):
    with capture_auxiliary.blocked_runtime() as runtime, capture_auxiliary.owned_root() as (root, errors):
        runtime.decoder = selection
        dialog = capture_auxiliary.file_decoder_ui.DecoderDialog(root)
        labels = "\n".join(str(widget.cget("text")) for widget in descendants(dialog.root)
                           if "text" in widget.keys())
        if isinstance(selection, dict):
            assert "ffmpeg.exe" in labels
            assert "synthetic-tools" not in labels
        elif isinstance(selection, Exception):
            assert "Couldn't read file-format setup" in labels
            assert str(selection) not in labels
            assert str(selection) in dialog.feedback.details
        assert not runtime.violations and not runtime.threads and not errors
        dialog.root.destroy()


def test_decoder_actions_cannot_select_forget_or_open_browser(working_tk_display):
    with capture_auxiliary.blocked_runtime() as runtime, capture_auxiliary.owned_root() as (root, errors):
        runtime.decoder = {"path": "synthetic-tools/ffmpeg.exe"}
        runtime.open_path = "synthetic-tools/ffmpeg.exe"
        runtime.confirm = True
        dialog = capture_auxiliary.file_decoder_ui.DecoderDialog(root)
        for action, boundary in (
            (dialog.choose, "utterleaf.file_decoder_ui.select_decoder"),
            (dialog.forget, "utterleaf.file_decoder_ui.forget_decoder"),
            (dialog.download_page, "webbrowser.open"),
        ):
            before = len(runtime.violations)
            try:
                action()
            except AssertionError:
                pass  # Some production actions report exceptions in a dialog instead.
            assert runtime.violations[before:] == [boundary]
        assert not runtime.threads and not runtime.exports and not errors
        dialog.root.destroy()


@pytest.mark.parametrize("allow_insert,action", [(True, None), (False, None),
                                                 (True, "Insert"), (True, "Copy"),
                                                 (False, "Copy"), (False, "Discard")])
def test_review_renders_real_widgets_and_emits_only_protocol_tokens(allow_insert, action, working_tk_display):
    with capture_auxiliary.blocked_runtime() as runtime, capture_auxiliary.owned_root() as (root, errors):
        def visit():
            widgets = list(descendants(root))
            previews = [widget for widget in widgets if isinstance(widget, tk.Text)]
            assert len(previews) == 1
            assert previews[0].get("1.0", "end").strip() == capture_auxiliary.SAMPLE_TEXT
            assert str(previews[0].cget("state")) == "disabled"
            buttons = {str(widget.cget("text")): widget for widget in widgets
                       if widget.winfo_class() == "TButton"}
            assert {"Insert", "Copy", "Discard"} <= buttons.keys()
            assert buttons["Insert"].instate(["disabled"]) == (not allow_insert)
            if not allow_insert:
                buttons["Insert"].invoke()  # Must not emit an action or close the window.
                assert root.winfo_exists()
            if action:
                buttons[action].invoke()

        response = capture_auxiliary.render_review(root, allow_insert, visit)
        expected = "ready\n" + (action.lower() + "\n" if action else "")
        assert response == expected
        assert capture_auxiliary.SAMPLE_TEXT not in response
        assert runtime.threads == ["utterleaf-review-control"]
        assert not runtime.violations and not runtime.exports and not errors


def test_owned_root_restores_scale_cancels_timers_and_records_callback_errors(working_tk_display, monkeypatch):
    with capture_auxiliary.owned_root() as (reference, _errors):
        baseline = float(reference.tk.call("tk", "scaling"))
    restored = []
    ran = []
    with capture_auxiliary.owned_root(2.0) as (root, errors):
        assert float(root.tk.call("tk", "scaling")) == pytest.approx(baseline * 2, abs=0.04)
        interpreter = root.tk
        root.after(60_000, lambda: ran.append(True))
        original_destroy = root.destroy

        def destroy():
            restored.append(float(root.tk.call("tk", "scaling")))
            original_destroy()

        monkeypatch.setattr(root, "destroy", destroy)
        root.after(0, lambda: (_ for _ in ()).throw(RuntimeError("Synthetic callback")))
        root.update()
        assert errors == ["RuntimeError: Synthetic callback"]
    assert restored == [pytest.approx(baseline, abs=0.02)]
    assert interpreter.call("after", "info") == ""
    assert ran == []


def test_capture_refuses_existing_or_outside_directory_without_deleting(tmp_path, monkeypatch):
    monkeypatch.setattr(capture_auxiliary, "ROOT", tmp_path)
    existing = tmp_path / "artifacts" / "keep"
    existing.mkdir(parents=True)
    sentinel = existing / "original.txt"
    sentinel.write_text("keep", encoding="utf-8")
    with pytest.raises(FileExistsError):
        capture_auxiliary.capture_all(existing)
    assert sentinel.read_text(encoding="utf-8") == "keep"
    assert list(existing.iterdir()) == [sentinel]
    outside = tmp_path / "outside"
    with pytest.raises(ValueError, match="artifacts"):
        capture_auxiliary.capture_all(outside)
    assert not outside.exists()


@pytest.mark.parametrize("fail_capture", [False, True])
def test_manifest_records_complete_inventory_or_explicit_failure(tmp_path, monkeypatch, fail_capture):
    monkeypatch.setattr(capture_auxiliary, "ROOT", tmp_path)
    source_dir = tmp_path / "utterleaf"
    source_dir.mkdir()
    source_names = ("file_ui.py", "file_decoder_ui.py", "review_ui.py", "theme.py", "ui_layout.py", "ui_feedback.py")
    for name in source_names:
        (source_dir / name).write_text("synthetic source", encoding="utf-8")

    @contextmanager
    def root_fixture(scale=1.0):
        root = SimpleNamespace(scale=scale, geometry=lambda *_: None, deiconify=lambda: None,
                               update=lambda: None, destroy=lambda: None,
                               report_callback_exception=lambda *_: None)
        yield root, []

    def fake_capture(root, errors, filename, size, output):
        if fail_capture:
            raise RuntimeError("Synthetic capture failure")
        return {"file": filename, "requested_size": list(size), "actual_size": list(size),
                "tk_scaling": root.scale, "synthetic": True}

    def fake_review(root, allow_insert, visit):
        visit()
        return "ready\n"

    monkeypatch.setattr(capture_auxiliary, "owned_root", root_fixture)
    monkeypatch.setattr(capture_auxiliary.file_ui, "FileWindow", lambda root, *_: SimpleNamespace(root=root))
    monkeypatch.setattr(capture_auxiliary.file_decoder_ui, "DecoderDialog",
                        lambda root: SimpleNamespace(root=root, choose=lambda: None))
    monkeypatch.setattr(capture_auxiliary, "settle", lambda *_: None)
    monkeypatch.setattr(capture_auxiliary, "stage_file", lambda *_: None)
    monkeypatch.setattr(capture_auxiliary, "render_review", fake_review)
    monkeypatch.setattr(capture_auxiliary, "capture", fake_capture)
    output = tmp_path / "artifacts" / "new-capture"
    if fail_capture:
        with pytest.raises(RuntimeError, match="Synthetic capture failure"):
            capture_auxiliary.capture_all(output)
    else:
        capture_auxiliary.capture_all(output)
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == ("incomplete" if fail_capture else "completed")
    assert "Synthetic" in manifest["scope"]
    assert set(manifest["sources"]) == set(source_names)
    assert all(len(digest) == 64 for digest in manifest["sources"].values())
    assert tuple(record["file"] for record in manifest["captures"]) == (() if fail_capture else capture_auxiliary.INVENTORY)
