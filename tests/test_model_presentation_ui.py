"""Model presentation through real Tk controls, with no live model operations."""

from types import SimpleNamespace

import pytest

from test_settings_ui import tk_root, window  # Reuse the guarded, no-background fixtures.
from utterleaf.model_setup import ModelAvailability
from utterleaf.settings_ui import SettingsWindow


@pytest.fixture(autouse=True)
def isolated_model_cache(tmp_path, monkeypatch):
    monkeypatch.setattr("utterleaf.models.models_dir", lambda: tmp_path)


@pytest.mark.parametrize("identifier", [
    r"C:\Users\Private Person\private-speech-model",
    "/home/private-person/private-model",
    "private-org/private-model.en",
    "private-model\nready",
])
def test_custom_model_primary_copy_is_fixed_and_entry_remains_editable(window, monkeypatch, identifier):
    monkeypatch.setattr("utterleaf.model_setup.run_download", lambda *a, **k: pytest.fail("Must not download"))
    monkeypatch.setattr("utterleaf.settings.save", lambda *a, **k: pytest.fail("Must not save"))
    original_config = window.cfg.model
    baseline = dict(window.baseline)
    field = window.fields["model"]
    assert str(field.cget("state")) == "normal"
    field.delete(0, "end")
    field.insert(0, identifier)
    assert window._snapshot()["model"] == identifier
    assert window.cfg.model == original_config
    assert window.baseline == baseline
    assert window.model_status.get().startswith(
        "Custom model\nCustom model; supported languages depend on its configuration.\n")
    assert window.model_summary.get() == "Custom model · Choose a supported model and device"
    for primary in (window.model_status.get(), window.model_summary.get(), window.model_action_status.get()):
        assert identifier not in primary
        assert "private" not in primary.lower()
        assert "ready" not in primary.lower()


@pytest.mark.parametrize("model,language,device,resolved,backend,display", [
    ("tiny", "en", "cpu", "tiny.en", "ctranslate2", "Tiny English"),
    ("base", "auto", "cpu", "base", "ctranslate2", "Base"),
    ("tiny", "en", "npu", "tiny.en", "openvino", "Tiny English"),
    ("base", "en", "auto", "base.en", "ctranslate2", "Base English"),
    ("private/custom", "en", "cpu", "private/custom", "ctranslate2", "Custom model"),
])
def test_model_details_are_explicit_cached_and_describe_the_draft(
        window, monkeypatch, model, language, device, resolved, backend, display):
    dialogs = []
    monkeypatch.setattr("utterleaf.settings_ui.messagebox.showinfo",
                        lambda *a, **k: dialogs.append((a, k)))
    window.vars["model"].set(model)
    window.vars["language"].set(language)
    window.vars["device"].set(device)
    cached = window.model_availability
    assert (cached.name, cached.backend) == (resolved, backend)
    assert cached.state == ("unsupported" if display == "Custom model" else "missing")
    assert dialogs == []  # Selection and refresh never open technical dialogs.
    snapshot = window._snapshot()
    baseline = dict(window.baseline)
    monkeypatch.setattr("utterleaf.model_setup.inspect_model", lambda *a, **k: pytest.fail("Details must not rescan"))
    monkeypatch.setattr("utterleaf.model_setup.run_download", lambda *a, **k: pytest.fail("Details must not download"))
    monkeypatch.setattr(window, "_worker", lambda *a, **k: pytest.fail("Details must not start workers"))
    monkeypatch.setattr(window, "save", lambda *a, **k: pytest.fail("Details must not save"))
    window.model_info_button.invoke()
    assert len(dialogs) == 1
    (title, message), kwargs = dialogs[0]
    assert title == "Selected speech model details"
    assert kwargs == {"parent": window.root}
    assert f"Model: {display}\n" in message
    assert f"Identifier: {resolved}\n" in message
    assert f"Backend: {backend}\n" in message
    assert f"File status: {cached.state}\n" in message
    expected_folder = str(cached.path) if cached.path is not None else "No managed location for this selection"
    assert f"Expected local folder: {expected_folder}\n" in message
    assert f"Missing or invalid required files: {', '.join(cached.missing) or 'None reported'}\n" in message
    assert "may be unsaved" in message
    assert "review before sharing" in message
    assert "not a successful model load" in message
    assert "separate NPU installation" in message
    assert window.model_availability is cached
    assert window._snapshot() == snapshot
    assert window.baseline == baseline


@pytest.mark.parametrize("state,missing", [("installed", ()), ("incomplete", ("tokenizer.json",))])
def test_model_details_report_file_state_without_claiming_load_success(window, monkeypatch, tmp_path, state, missing):
    cached = ModelAvailability("tiny.en", "ctranslate2", state, tmp_path / "tiny-model", missing)
    monkeypatch.setattr("utterleaf.model_setup.inspect_model", lambda *a: cached)
    window.vars["model"].set("tiny")
    dialogs = []
    monkeypatch.setattr("utterleaf.settings_ui.messagebox.showinfo", lambda *a, **k: dialogs.append(a))
    window.model_info_button.invoke()
    assert f"File status: {state}\n" in dialogs[0][1]
    assert f"Missing or invalid required files: {', '.join(missing) or 'None reported'}\n" in dialogs[0][1]
    assert "ready" not in window.model_status.get().lower()
    assert "ready" not in window.model_summary.get().lower()
    assert "not a successful model load" in dialogs[0][1]


def test_selection_replaces_cached_model_details_without_mixing_download_error(window, monkeypatch):
    dialogs = []
    monkeypatch.setattr("utterleaf.settings_ui.messagebox.showinfo", lambda *a, **k: dialogs.append(a))
    window.vars["model"].set("tiny")
    window.model_info_button.invoke()
    assert "Identifier: tiny.en\n" in dialogs[-1][1]
    window._set_error_details(window.model_details_button, RuntimeError("prior download failure"))
    window.vars["model"].set("base")
    window.vars["device"].set("npu")
    window.model_info_button.invoke()
    assert "Identifier: base.en\n" in dialogs[-1][1]
    assert "Backend: openvino\n" in dialogs[-1][1]
    assert "tiny.en" not in dialogs[-1][1]
    assert "prior download failure" not in dialogs[-1][1]
    window.model_details_button.invoke()
    assert dialogs[-1][0] == "Model download details"
    assert "prior download failure" in dialogs[-1][1]
    assert window.model_info_button.cget("text") != window.model_details_button.cget("text")


def test_model_details_sanitize_and_bound_each_technical_field(window, monkeypatch):
    control_text = "\x00\x1b\r\n\tInjected:"
    window.model_availability = SimpleNamespace(
        name="private" + control_text + "n" * 1000,
        backend="backend" + control_text + "b" * 500,
        state="state" + control_text + "s" * 500,
        path="private-path" + control_text + "p" * 5000,
        missing=("required" + control_text + "m" * 2000,),
    )
    dialogs = []
    monkeypatch.setattr("utterleaf.settings_ui.messagebox.showinfo", lambda *a, **k: dialogs.append(a))
    window.model_info_button.invoke()
    message = dialogs[0][1]
    assert len(message) < 3000
    assert "[shortened]" in message
    assert "Model: Custom model\n" in message
    assert "\nInjected:" not in message
    assert all(character.isprintable() or character == "\n" for character in message)


def test_closed_model_details_returns_without_accessing_tk_or_cached_state(monkeypatch):
    closed = object.__new__(SettingsWindow)
    closed.closed = True
    monkeypatch.setattr("utterleaf.settings_ui.messagebox.showinfo", lambda *a, **k: pytest.fail("Closed dialog"))
    closed.show_model_details()


@pytest.mark.parametrize("failure", [False, True])
def test_download_messages_keep_the_attempted_human_name_after_selection_changes(window, monkeypatch, failure):
    confirmations, pending, downloads = [], [], []
    window.vars["model"].set("tiny")
    window.vars["device"].set("cpu")
    window.vars["allow_network"].set(False)
    monkeypatch.setattr("utterleaf.settings_ui.messagebox.askyesno",
                        lambda *a, **k: confirmations.append(a) or True)
    monkeypatch.setattr(window, "_worker", lambda action, done, **k: pending.append((action, done)))
    monkeypatch.setattr("utterleaf.model_setup.run_download", lambda *a, **k: downloads.append(a))
    window.download_model()
    assert "Download Tiny English for CPU / NVIDIA" in confirmations[0][1]
    assert "tiny.en" not in confirmations[0][1]
    assert window.model_action_status.get().startswith("Downloading Tiny English…")
    window.vars["model"].set("base")
    pending[0][0]()
    pending[0][1](RuntimeError("private failure") if failure else None)
    assert downloads == [("tiny.en", "ctranslate2")]
    assert window.model_availability.name == "base.en"
    assert window.model_status.get().startswith("Base English\n")
    assert "Tiny English" in window.model_action_status.get()
    assert "Base English" not in window.model_action_status.get()
    assert "tiny.en" not in window.model_action_status.get()
    assert "private failure" not in window.model_action_status.get()
    assert window._snapshot()["model"] == "base"
    assert not window.vars["allow_network"].get()


@pytest.mark.parametrize("scale", [1.0, 1.5, 2.0])
def test_compact_model_controls_fit_and_reveal_at_larger_text_scales(tk_root, monkeypatch, scale):
    import tkinter as tk
    from utterleaf.config import Config

    monkeypatch.setattr("utterleaf.settings_ui.startup_enabled", lambda: False)
    monkeypatch.setattr("utterleaf.settings_ui.dictionary_text", lambda: "utter leaf = Utterleaf")
    baseline = float(tk_root.tk.call("tk", "scaling"))
    root = tk.Toplevel(tk_root)
    root.tk.call("tk", "scaling", baseline * scale)
    app = SettingsWindow(root, Config(), background=False)
    try:
        root.geometry("760x560")
        app.vars["model"].set("base")
        app.vars["language"].set("auto")
        app.vars["device"].set("cpu")
        app.vars["hotkey"].set("f8")
        app._set_error_details(app.model_details_button, RuntimeError("Synthetic model download failure"))
        # Measure the full action row without initiating a real download.
        app.model_cancel_button.configure(state="normal")
        app.show_page("Engine")
        root.update()
        snapshot = app._snapshot()
        controls = [
            ("model picker", app.fields["model"]),
            ("language picker", app.fields["language"]),
            ("download", app.model_download_button),
            ("cancel download", app.model_cancel_button),
            ("model details", app.model_info_button),
            ("download error details", app.model_details_button),
            ("processing device", app.fields["device"]),
            ("noise reduction", app.fields["denoise"]),
        ]
        # Observe row relationships instead of coupling the regression to grid
        # coordinates or the implementation's breakpoint arithmetic.
        pairs = []
        for key in ("model", "language", "device", "denoise"):
            picker = app.fields[key]
            caption = next(child for child in picker.master.winfo_children()
                           if child.winfo_class() == "TLabel")
            pairs.append((caption, picker))
        pairs.append((app.model_download_button, app.model_cancel_button))

        def stacked_rows():
            return tuple(second.winfo_rooty() >= first.winfo_rooty() + first.winfo_height()
                         for first, second in pairs)

        focused = app.fields["language"]
        focused.focus_force()
        root.update()
        assert root.focus_get() == focused
        compact_rows = stacked_rows()
        problems = []

        def check_controls(phase):
            for label, control in controls:
                control.event_generate("<FocusIn>")
                root.update()
                left, top = app.canvas.winfo_rootx(), app.canvas.winfo_rooty()
                right, bottom = left + app.canvas.winfo_width(), top + app.canvas.winfo_height()
                x, y = control.winfo_rootx(), control.winfo_rooty()
                width, height = control.winfo_width(), control.winfo_height()
                if x < left or x + width > right or width < control.winfo_reqwidth():
                    problems.append(f"{phase} {label}: horizontal bounds {x}:{x + width}, viewport {left}:{right}, "
                                    f"width {width}, requested {control.winfo_reqwidth()}")
                if y < top or y + height > bottom:
                    problems.append(f"{phase} {label}: focused vertical bounds {y}:{y + height}, viewport {top}:{bottom}")
                assert app.close_button.winfo_rooty() >= bottom
            assert app._snapshot() == snapshot
            assert root.focus_get() == focused

        check_controls("compact")
        root.geometry("1600x900")
        root.update()
        assert root.focus_get() == focused
        wide_rows = stacked_rows()
        wide_realized = root.winfo_width() >= 1500 and root.winfo_height() >= 850
        if wide_realized:
            assert not any(wide_rows), "Wide layout should have room for inline labels and actions"
            if any(compact_rows):
                assert wide_rows != compact_rows, "Widening must release stacked rows"
        check_controls("wide")
        root.geometry("760x560")
        root.update()
        assert root.focus_get() == focused
        assert stacked_rows() == compact_rows, "Narrowing must restore the original responsive layout"
        check_controls("compact again")
        assert not problems, "\n".join(problems)
    finally:
        app.closed = True
        root.after_cancel(app.poll_id)
        if app._page_reset is not None:
            root.after_cancel(app._page_reset)
        root.destroy()
        tk_root.tk.call("tk", "scaling", baseline)
