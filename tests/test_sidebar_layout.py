"""Sidebar navigation stays usable when optional copy cannot fit vertically."""

import tkinter as tk

import pytest

from test_settings_ui import tk_root
from utterleaf.config import Config
from utterleaf.model_setup import ModelAvailability
from utterleaf.settings_ui import SettingsWindow


@pytest.mark.parametrize("scale", [1.0, 1.5, 2.0])
def test_sidebar_preserves_navigation_and_only_shows_complete_tagline(tk_root, monkeypatch, scale):
    monkeypatch.setattr("utterleaf.settings_ui.startup_enabled", lambda: False)
    monkeypatch.setattr("utterleaf.settings_ui.dictionary_text", lambda: "utter leaf = Utterleaf")
    monkeypatch.setattr("utterleaf.model_setup.inspect_model",
                        lambda name, backend: ModelAvailability(name, backend, "missing", None))
    monkeypatch.setattr("utterleaf.model_setup.run_download", lambda *a, **k: pytest.fail("No downloads"))
    monkeypatch.setattr("utterleaf.settings.save", lambda *a, **k: pytest.fail("No preferences saved"))
    baseline = float(tk_root.tk.call("tk", "scaling"))
    root = tk.Toplevel(tk_root)
    app = None
    try:
        root.tk.call("tk", "scaling", baseline * scale)
        app = SettingsWindow(root, Config(), background=False)
        root.geometry("760x560")
        app.vars["hotkey"].set("f8")
        app.vars["model"].set("base")
        app.navigate("Engine")
        root.update()
        focused = app.nav["Engine"]
        focused.focus_force()
        root.update()
        snapshot = app._snapshot()
        navigation = tuple(app.nav.items())
        assert tuple(app.nav) == ("Dictation", "Vocabulary", "Voice commands", "Engine", "Help & diagnostics")
        label = app.privacy_label
        sidebar = label.master

        for geometry, require_tagline in (("760x560", False), ("760x950", True), ("760x560", False)):
            root.geometry(geometry)
            root.update()
            assert root.focus_get() == focused
            assert app._snapshot() == snapshot
            assert tuple(app.nav.items()) == navigation
            left, top = sidebar.winfo_rootx(), sidebar.winfo_rooty()
            right, bottom = left + sidebar.winfo_width(), top + sidebar.winfo_height()
            last_bottom = top
            for name, button in navigation:
                assert button.winfo_ismapped(), f"{geometry}: {name} was hidden"
                x, y = button.winfo_rootx(), button.winfo_rooty()
                width, height = button.winfo_width(), button.winfo_height()
                assert width >= button.winfo_reqwidth(), f"{geometry}: {name} width clipped"
                assert height >= button.winfo_reqheight(), f"{geometry}: {name} height clipped"
                assert left <= x and x + width <= right, f"{geometry}: {name} outside sidebar width"
                assert last_bottom <= y and y + height <= bottom, f"{geometry}: {name} outside sidebar height"
                last_bottom = y + height

            if label.winfo_manager():
                assert label.winfo_ismapped(), f"{geometry}: managed tagline is invisible"
                assert label.winfo_height() >= label.winfo_reqheight(), f"{geometry}: tagline partly clipped"
                assert label.winfo_width() >= label.winfo_reqwidth(), f"{geometry}: tagline width clipped"
                assert left <= label.winfo_rootx()
                assert label.winfo_rootx() + label.winfo_width() <= right
                assert label.winfo_rooty() >= last_bottom
                assert label.winfo_rooty() + label.winfo_height() <= bottom
            else:
                assert not label.winfo_ismapped()
                assert not require_tagline, "Tagline must reappear when the taller sidebar has space"
            if require_tagline:
                assert label.winfo_ismapped()
    finally:
        if app is not None:
            app.closed = True
            root.after_cancel(app.poll_id)
            if app._page_reset is not None:
                root.after_cancel(app._page_reset)
        root.destroy()
        tk_root.tk.call("tk", "scaling", baseline)
