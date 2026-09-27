"""Inventory selections use the ordinary local Settings draft and Save contract."""

from dataclasses import replace
import tkinter as tk

import pytest

from test_settings_ui import tk_root, window
from utterleaf.model_inventory import ModelInstallation
from utterleaf.config import Config
from utterleaf.settings_ui import SettingsWindow


@pytest.fixture(autouse=True)
def isolated_models(tmp_path, monkeypatch):
    monkeypatch.setattr("utterleaf.models.models_dir", lambda: tmp_path)
    def blocked(*_args, **_kwargs):
        pytest.fail("Selection must not scan, download, load, or save")
    for target in ("utterleaf.model_inventory.inventory_models",
                   "utterleaf.model_setup.run_download", "utterleaf.models.ensure_ct2",
                   "utterleaf.models.ensure_ov", "utterleaf.settings.save"):
        monkeypatch.setattr(target, blocked)


def entry(name="base.en", backend="ctranslate2", state="installed"):
    return ModelInstallation(name, backend, state, 100)


@pytest.mark.parametrize("name,language,device,backend", [
    ("base.en", "en", "cpu", "ctranslate2"),
    ("base.en", "english", "gpu", "ctranslate2"),
    ("base.en", "auto", "auto", "ctranslate2"),
    ("base", "auto", "cpu", "ctranslate2"),
    ("base", "fr", "gpu", "ctranslate2"),
    ("large-v3", "en", "auto", "ctranslate2"),
    ("tiny.en", "en", "npu", "openvino"),
    ("tiny", "auto", "npu", "openvino"),
])
def test_compatible_inventory_entry_stages_only_model(window, name, language, device, backend):
    window.vars["language"].set(language)
    window.vars["device"].set(device)
    window.vars["model"].set("custom/previous")
    before = window._snapshot()
    baseline, cfg = dict(window.baseline), window.cfg
    row = entry(name, backend)
    assert window._inventory_selection_reason(row) is None
    window._use_inventory_model(row)
    assert window._snapshot() == {**before, "model": name}
    assert window._selected_model() == (name, backend)
    assert window.cfg is cfg and window.baseline == baseline
    assert window.save_button.instate(["!disabled"])


@pytest.mark.parametrize("row,language,device,reason", [
    (entry("base"), "en", "cpu", "Language"),
    (entry("base"), "english", "cpu", "Language"),
    (entry("base"), " en ", "cpu", "Language"),
    (entry("base"), "", "cpu", "Language"),
    (entry("base.en"), "fr", "cpu", "Language"),
    (entry("base.en", "openvino"), "en", "cpu", "NPU"),
    (entry("base.en", "openvino"), "en", "auto", "NPU"),
    (entry("base.en"), "en", "npu", "Processing device"),
    (entry(state="error"), "en", "cpu", "Refresh"),
])
def test_incompatible_inventory_selection_does_not_mutate_draft(window, row, language, device, reason):
    window.vars["language"].set(language)
    window.vars["device"].set(device)
    before, baseline = window._snapshot(), dict(window.baseline)
    assert reason in window._inventory_selection_reason(row)
    window._use_inventory_model(row)
    assert window._snapshot() == before and window.baseline == baseline


def test_incomplete_installation_can_be_staged_for_explicit_repair(window):
    window.vars["device"].set("cpu")
    row = entry(state="incomplete")
    assert window._inventory_selection_reason(row) is None
    window._use_inventory_model(row)
    assert window.vars["model"].get() == "base.en"
    assert window.model_download_button.instate(["!disabled"])
    assert "ready" not in window.model_summary.get().lower()


def test_closed_inventory_selection_is_ignored(window):
    before = window._snapshot()
    window.closed = True
    try:
        window._use_inventory_model(entry())
        assert window._snapshot() == before
    finally:
        window.closed = False


def test_inventory_selection_cancel_retains_draft_then_discard_does_not_save(window, monkeypatch):
    window._use_inventory_model(entry())
    baseline, cfg = dict(window.baseline), window.cfg
    monkeypatch.setattr("utterleaf.settings_ui.messagebox.askyesno", lambda *a, **k: False)
    window.close()
    assert not window.closed and window.vars["model"].get() == "base.en"
    assert window.baseline == baseline and window.cfg is cfg
    monkeypatch.setattr("utterleaf.settings_ui.messagebox.askyesno", lambda *a, **k: True)
    window.close()
    assert window.closed and window.cfg is cfg


def test_inventory_selection_saved_through_existing_form(window, monkeypatch):
    from utterleaf.config import Config
    import utterleaf.ipc
    submitted = []
    window._use_inventory_model(entry())
    def apply(cfg, **values):
        submitted.append(values)
        return replace(cfg, model=values["model"])
    monkeypatch.setattr("utterleaf.settings_ui.apply_form", apply)
    monkeypatch.setattr("utterleaf.settings_ui.load", Config)
    monkeypatch.setattr(utterleaf.ipc, "send", lambda *_a, **_kw: None)
    monkeypatch.setattr(window, "_worker", lambda work, done, **_kw: done(work()))
    window.save()
    assert submitted[0]["model"] == "base.en"
    assert window.cfg.model == window.baseline["model"] == "base.en"
    assert window.vars["language"].get() == Config().language
    assert window.vars["device"].get() == Config().device


def test_default_reset_stays_staged_and_preserves_inventory_files(window, tmp_path, monkeypatch):
    from utterleaf.config import Config
    marker = tmp_path / "faster-whisper-base.en" / "model.bin"
    marker.parent.mkdir()
    marker.write_bytes(b"local model placeholder")
    window._use_inventory_model(entry())
    baseline, cfg = dict(window.baseline), window.cfg
    monkeypatch.setattr("utterleaf.settings_ui.messagebox.askyesno", lambda *a, **k: True)
    window.restore_defaults()
    assert window.vars["model"].get() == Config().model
    assert window.cfg is cfg and window.baseline == baseline
    assert marker.read_bytes() == b"local model placeholder"


@pytest.mark.parametrize("scale", [1, 1.5, 2])
def test_inventory_controls_use_real_settings_keyboard_reveal_after_resize(tk_root, monkeypatch, scale):
    baseline_scale = float(tk_root.tk.call("tk", "scaling"))
    tk_root.tk.call("tk", "scaling", baseline_scale * scale)
    root = tk.Toplevel(tk_root)
    root.withdraw()
    monkeypatch.setattr("utterleaf.settings_ui.startup_enabled", lambda: False)
    monkeypatch.setattr("utterleaf.settings_ui.dictionary_text", lambda: "")
    errors = []
    root.report_callback_exception = lambda *error: errors.append(error)
    app = None
    try:
        app = SettingsWindow(root, Config(), background=False)
        jobs = []
        monkeypatch.setattr(app, "_worker", lambda work, done: jobs.append((work, done)))
        panel = app.model_inventory
        panel.refresh()
        jobs[0][1]((entry(),))
        app.show_page("Engine")
        root.deiconify()
        for geometry in ("760x560", "1100x800", "760x560"):
            root.geometry(geometry)
            root.update()
            panel.refresh_button.focus_force()
            root.update()
            for previous, target in ((panel.refresh_button, panel.model_picker),
                                     (panel.model_picker, panel.use_button)):
                previous.event_generate("<Tab>")
                root.update()
                assert root.focus_get() is target
                assert target.winfo_width() >= target.winfo_reqwidth()
                x = target.winfo_rootx() - app.canvas.winfo_rootx()
                y = target.winfo_rooty() - app.canvas.winfo_rooty()
                assert 0 <= x and x + target.winfo_width() <= app.canvas.winfo_width()
                assert 0 <= y and y + target.winfo_height() <= app.canvas.winfo_height()
            panel.use_button.event_generate("<space>")
            root.update()
            assert app.vars["model"].get() == "base.en"
            assert app.vars["language"].get() == Config().language
            assert app.vars["device"].get() == Config().device
            assert len(jobs) == 1
            assert app.baseline["model"] == Config().model

        # At 2x the download error Details can be below the initial viewport.
        # Reach it through actual Tab keys, not a manually aligned screenshot.
        def fail_start(*_args, **_kwargs):
            raise RuntimeError("Synthetic worker start failure")
        monkeypatch.setattr(app, "_worker", fail_start)
        monkeypatch.setattr("utterleaf.settings_ui.messagebox.askyesno", lambda *a, **k: True)
        dialogs = []
        monkeypatch.setattr("utterleaf.settings_ui.messagebox.showinfo", lambda *a, **k: dialogs.append(a))
        snapshot = app._snapshot()
        app.download_model()
        app.model_download_button.focus_force()
        root.update()
        for _ in range(5):
            root.focus_get().event_generate("<Tab>")
            root.update()
            if root.focus_get() is app.model_details_button:
                break
        target = app.model_details_button
        assert root.focus_get() is target
        y = target.winfo_rooty() - app.canvas.winfo_rooty()
        assert 0 <= y and y + target.winfo_height() <= app.canvas.winfo_height()
        assert target.winfo_width() >= target.winfo_reqwidth()
        target.event_generate("<space>")
        root.update()
        assert len(dialogs) == 1 and dialogs[0][0] == "Model download details"
        assert "Synthetic worker start failure" in dialogs[0][1]
        assert app._snapshot() == snapshot
        assert errors == []
    finally:
        if app is not None:
            app.closed = True
            root.after_cancel(app.poll_id)
            if app._page_reset is not None:
                root.after_cancel(app._page_reset)
        root.destroy()
        tk_root.tk.call("tk", "scaling", baseline_scale)
