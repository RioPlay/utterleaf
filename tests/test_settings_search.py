"""Settings discovery through real Tk widgets, without private or runtime inputs."""

import sys
import tkinter as tk
from tkinter import font as tkfont
from types import SimpleNamespace

import pytest

from test_settings_ui import tk_root, window  # Guarded, no-background fixtures.
from utterleaf.config import Config
from utterleaf.settings_ui import SettingsWindow


@pytest.fixture(autouse=True)
def isolated_environment(tmp_path, monkeypatch):
    monkeypatch.setattr("utterleaf.models.models_dir", lambda: tmp_path)
    monkeypatch.setattr("utterleaf.settings_ui.is_wayland", lambda: False)


def _show(window, page="Dictation"):
    window.root.deiconify()
    window.root.geometry("760x560")
    window.navigate(page)
    window.root.update()


def _search(window, query):
    window.open_search()
    window.search_query.set(query)
    window.root.update()
    return {target.key for target in window.search_matches}


def _select(window, key):
    position = next(i for i, target in enumerate(window.search_matches) if target.key == key)
    window.search_results.selection_clear(0, "end")
    window.search_results.selection_set(position)
    window.search_results.activate(position)
    window.search_results.see(position)
    window.search_results.event_generate("<<ListboxSelect>>")
    window.root.update()


def _activate(window, key):
    _select(window, key)
    window._activate_search_result()
    window.root.update()


def _assert_in_view(window, widget):
    top = window.canvas.winfo_rooty()
    bottom = top + window.canvas.winfo_height()
    assert widget.winfo_ismapped()
    if isinstance(widget, tk.Text) and widget.winfo_height() > window.canvas.winfo_height():
        bounds = widget.bbox("insert")
        assert bounds is not None
        assert top <= widget.winfo_rooty() + bounds[1]
        assert widget.winfo_rooty() + bounds[1] + bounds[3] <= bottom
    else:
        assert top <= widget.winfo_rooty()
        assert widget.winfo_rooty() + widget.winfo_height() <= bottom


def test_index_covers_preferences_and_five_primary_destinations(window):
    expected = set(window.vars) | {"names"}
    assert expected <= set(window.search_targets)
    assert len(expected) == 21
    assert set(window.search_targets) == expected | {f"page:{name}" for name in window.nav}
    assert len(window.nav) == 5
    for key, target in window.search_targets.items():
        assert target.key == key
        assert target.label.strip()
        assert target.page in window.pages
        assert target.page_label.strip()
        assert target.widget.winfo_exists()
        assert isinstance(target.terms, str)
        if key in expected:
            assert target.section.strip()
        window.search_query.set(target.label)
        assert target in window.search_matches


@pytest.mark.parametrize("query,key", [
    ("  kEyBoArD   SHORTCUT  ", "hotkey"),
    ("privacy clipboard", "restore_clipboard"),
    ("recording feedback", "beep"),
    ("markdown", "output_format"),
    ("offline", "allow_network"),
    ("Tray icon only", "indicator"),
    ("tray icon", "indicator"),
])
def test_matching_uses_labels_pages_sections_and_curated_terms(window, query, key):
    _show(window)
    assert key in _search(window, query)
    first = [target.key for target in window.search_matches]
    result_word = "result" if len(first) == 1 else "results"
    assert window.search_status.get() == f"{len(first)} {result_word}"
    window.search_query.set(query.swapcase())
    window.root.update()
    assert [target.key for target in window.search_matches] == first


def test_empty_and_no_match_feedback_never_activates_a_setting(window):
    _show(window)
    original = window._snapshot()
    window.search_button.invoke()
    window.root.update()
    assert window.search_open
    assert _search(window, "  ") == set()
    assert window.search_results.size() == 0
    assert window.search_status.get().strip()
    window._activate_search_result()
    assert window.search_open
    assert _search(window, "zzunmatchedqueryzz") == set()
    assert window.search_results.size() == 0
    assert "no" in window.search_status.get().lower()
    window._activate_search_result()
    assert window.search_open
    assert window._snapshot() == original
    window.search_close_button.invoke()
    window.root.update()
    assert not window.search_open


def test_index_and_results_never_include_private_draft_or_runtime_values(window, monkeypatch):
    markers = ["privatevocabularytoken", "privatemicrophonetoken", "privatemodeltoken",
               "privatepreviewtoken", "privatereporttoken", "privateexceptiontoken"]
    window.names.insert("end", "\n" + markers[0] + " = Private replacement")
    window.vars["microphone"].set(markers[1])
    window.mic_box.configure(values=[markers[1]])
    window.vars["model"].set("C:/Private/" + markers[2])
    window.sample.insert("end", markers[3])
    window.report = markers[4]
    window._set_error_details(window.mic_details_button, RuntimeError(markers[5]))
    _show(window)
    before = window._snapshot()
    baseline = dict(window.baseline)

    def unexpected(*args, **kwargs):
        pytest.fail("Search must not perform runtime, persistence, or clipboard work")

    for name in ("_worker", "save", "test_mic", "refresh_mics", "refresh_model_status"):
        monkeypatch.setattr(window, name, unexpected)
    monkeypatch.setattr("utterleaf.settings_ui.apply_form", unexpected)
    monkeypatch.setattr("utterleaf.model_setup.run_download", unexpected)
    monkeypatch.setattr(window.root, "clipboard_get", unexpected)
    monkeypatch.setattr(window.root, "clipboard_append", unexpected)
    metadata = " ".join(
        " ".join((target.key, target.label, target.page_label, target.section, target.terms))
        for target in window.search_targets.values()
    ).lower()
    for marker in markers:
        assert marker not in metadata
        assert _search(window, marker) == set()
        assert marker not in window.search_status.get().lower()
    assert "restore_clipboard" in _search(window, "clipboard")
    _activate(window, "restore_clipboard")
    window.close_search()
    assert window._snapshot() == before
    assert window.baseline == baseline


def test_query_is_ephemeral_and_preserves_unsaved_form_and_preview(window):
    _show(window, "Vocabulary")
    window.vars["hotkey"].set("f8")
    window.names.insert("end", "\nlocal term = Local Term")
    window.sample.insert("end", " local term")
    window.preview()
    before = window._snapshot()
    baseline = dict(window.baseline)
    preview = window.preview_result.get()
    _search(window, "noise")
    _activate(window, "denoise")
    assert window._snapshot() == before
    assert window.baseline == baseline
    assert window.preview_result.get() == preview
    assert all(var is not window.search_query for var in window.vars.values())
    assert "search" not in window._snapshot()
    assert str(window.save_button.cget("state")) == "normal"


@pytest.mark.parametrize("editor", ["entry", "text"])
def test_find_shortcut_precedes_native_editor_caret_binding(window, editor):
    _show(window, "Engine" if editor == "entry" else "Vocabulary")
    control = window.fields["model"] if editor == "entry" else window.names
    control.focus_force()
    window.root.update()
    if editor == "entry":
        control.icursor(1)
    else:
        control.mark_set("insert", "1.1")
    original = control.index("insert")
    shortcut = "Command" if sys.platform == "darwin" else "Control"
    control.event_generate(f"<{shortcut}-f>")
    window.root.update()
    assert window.search_open
    assert window.root.focus_get() == window.search_entry
    assert control.index("insert") == original
    window.search_entry.event_generate("<Escape>")
    window.root.update()
    assert not window.search_open
    assert window.root.focus_get() == control
    assert control.index("insert") == original


def test_refocusing_open_search_selects_existing_query_and_dismissal_clears_it(window):
    _show(window)
    _search(window, "clipboard")
    window.open_search()
    window.root.update()
    assert window.search_entry.selection_present()
    assert window.search_entry.index("sel.first") == 0
    assert window.search_entry.index("sel.last") == len(window.search_query.get())
    window.close_search()
    assert window.search_query.get() == ""
    assert not window.search_matches


@pytest.mark.parametrize("query,key,page", [
    ("clipboard", "restore_clipboard", "Engine"),
    ("personal vocabulary", "names", "Vocabulary"),
])
def test_activation_reveals_target_after_pending_page_scroll_reset(window, query, key, page):
    _show(window)
    assert key in _search(window, query)
    _activate(window, key)
    target = window.search_targets[key].widget
    assert not window.search_open
    assert window.pages[page].grid_info()
    assert window.root.focus_get() == target
    assert window._page_reset is None
    _assert_in_view(window, target)
    before = window.canvas.yview()
    window.root.update()
    assert window.canvas.yview() == pytest.approx(before)


@pytest.mark.parametrize("page", ["Voice commands", "Help & diagnostics"])
def test_reference_results_focus_existing_primary_destination(window, page):
    _show(window)
    key = f"page:{page}"
    assert key in _search(window, window.search_targets[key].label)
    _activate(window, key)
    assert window.pages[page].grid_info()
    assert window.root.focus_get() == window.nav[page]


@pytest.mark.parametrize("key,prerequisite", [
    ("speech_end_pause_seconds", "speech_end_enabled"),
    ("speech_end_insert", "speech_end_enabled"),
    ("live_preview", "indicator"),
])
def test_disabled_result_explains_and_focuses_prerequisite_without_changing_it(
        window, key, prerequisite):
    window.vars[prerequisite].set(False)
    _show(window, "Vocabulary")
    before = window._snapshot()
    assert key in _search(window, window.search_targets[key].label)
    _select(window, key)
    assert window.search_targets[key].label in window.search_detail.get()
    assert ("speech" if prerequisite == "speech_end_enabled" else "indicator") in window.search_detail.get().lower()
    _activate(window, key)
    target = window.search_targets[prerequisite].widget
    assert window.root.focus_get() == target
    _assert_in_view(window, target)
    assert window._snapshot() == before
    assert not window.vars[prerequisite].get()
    hint = window.status.get().lower()
    assert ("speech" if prerequisite == "speech_end_enabled" else "indicator") in hint


def test_escape_dismisses_search_before_existing_discard_confirmation(window, monkeypatch):
    _show(window)
    window.vars["hotkey"].set("f8")
    dialogs = []
    monkeypatch.setattr("utterleaf.settings_ui.messagebox.askyesno",
                        lambda *args, **kwargs: dialogs.append(args) or False)
    window.nav["Dictation"].focus_force()
    window.root.update()
    _search(window, "clipboard")
    window.search_entry.event_generate("<Escape>")
    window.root.update()
    assert not window.search_open
    assert not window.closed
    assert not dialogs
    assert window.root.focus_get() == window.nav["Dictation"]
    window.nav["Dictation"].event_generate("<Escape>")
    window.root.update()
    assert len(dialogs) == 1
    assert not window.closed
    assert window.vars["hotkey"].get() == "f8"


def test_search_dismissal_has_valid_focus_when_original_control_is_destroyed(window):
    _show(window)
    temporary = tk.Entry(window.root)
    temporary.place(x=10, y=10, width=120, height=24)
    temporary.focus_force()
    window.root.update()
    window.open_search()
    temporary.destroy()
    window.close_search()
    window.root.update()
    focused = window.root.focus_get()
    assert focused is not None
    assert focused.winfo_exists()
    assert focused.winfo_ismapped()
    assert focused.winfo_toplevel() == window.root


def test_result_arrow_keys_and_enter_activate_selection(window):
    _show(window)
    _search(window, "dictation")
    assert len(window.search_matches) > 2
    window.search_entry.focus_force()
    window.root.update()
    window.search_entry.event_generate("<Down>")
    window.root.update()
    selected = window.search_results.curselection()[0]
    focused = window.root.focus_get()
    focused.event_generate("<Down>")
    window.root.update()
    assert window.search_results.curselection() == (selected + 1,)
    window.root.focus_get().event_generate("<Up>")
    window.root.update()
    assert window.search_results.curselection() == (selected,)
    target = window.search_matches[selected]
    assert target.label in window.search_detail.get()
    assert target.page_label in window.search_detail.get()
    window.root.focus_get().event_generate("<Return>")
    window.root.update()
    assert not window.search_open
    assert window.pages[target.page].grid_info()


def test_search_list_wheel_and_navigation_do_not_scroll_settings_page(window):
    _show(window, "Voice commands")
    _search(window, "dictation")
    window.canvas.yview_moveto(0.4)
    window.root.update()
    before = window.canvas.yview()
    window.search_results.focus_force()
    window.root.update()
    for sequence in ("<Next>", "<Prior>", "<Home>", "<End>"):
        window.search_results.event_generate(sequence)
        window.root.update()
        assert window.canvas.yview() == pytest.approx(before)
    window.search_results.event_generate("<MouseWheel>", delta=-120)
    window.root.update()
    assert window.canvas.yview() == pytest.approx(before)


def test_find_binding_is_local_to_settings_window(window):
    _show(window)
    other = tk.Toplevel(window.root)
    editor = tk.Entry(other)
    editor.pack()
    editor.insert(0, "other window")
    try:
        editor.focus_force()
        window.root.update()
        shortcut = "Command" if sys.platform == "darwin" else "Control"
        editor.event_generate(f"<{shortcut}-f>")
        window.root.update()
        assert not window.search_open
        assert window.root.focus_get() == editor
        assert window.open_search(SimpleNamespace(widget=editor)) is None
        assert not window.search_open
    finally:
        other.destroy()


def test_search_does_not_take_native_editing_or_existing_shortcuts(window, monkeypatch):
    _show(window, "Engine")
    control = window.fields["model"]
    control.focus_force()
    window.root.update()
    control.icursor(1)
    control.event_generate("<End>")
    window.root.update()
    assert control.index("insert") == len(control.get())
    control.event_generate("<Home>")
    window.root.update()
    assert control.index("insert") == 0
    calls = []
    monkeypatch.setattr(window, "save", lambda: calls.append("save"))
    _search(window, "clipboard")
    shortcut = "Command" if sys.platform == "darwin" else "Control"
    window.search_entry.event_generate(f"<{shortcut}-s>")
    window.root.update()
    assert calls == ["save"]
    window.root.focus_get().event_generate("<F1>")
    window.root.update()
    assert window.pages["Help & diagnostics"].grid_info()
    modifier = "Command" if sys.platform == "darwin" else "Alt"
    for index, page in enumerate(window.nav, 1):
        window.root.focus_get().event_generate(f"<{modifier}-Key-{index}>")
        window.root.update()
        assert window.pages[page].grid_info()


def _destroy(window):
    window.closed = True
    window.root.after_cancel(window.poll_id)
    if window._page_reset is not None:
        window.root.after_cancel(window._page_reset)
    window.root.destroy()


@pytest.mark.parametrize("key", ["hotkey", "mode"])
def test_wayland_disabled_shortcut_result_explains_desktop_configuration(tk_root, monkeypatch, key):
    monkeypatch.setattr("utterleaf.settings_ui.is_wayland", lambda: True)
    monkeypatch.setattr("utterleaf.settings_ui.startup_enabled", lambda: False)
    monkeypatch.setattr("utterleaf.settings_ui.dictionary_text", lambda: "")
    app = SettingsWindow(tk.Toplevel(tk_root), Config(), background=False)
    try:
        _show(app, "Vocabulary")
        before = app._snapshot()
        assert key in _search(app, app.search_targets[key].label)
        _activate(app, key)
        assert app.pages["Dictation"].grid_info()
        assert app.root.focus_get() == app.nav["Dictation"]
        assert "desktop" in app.status.get().lower()
        assert "shortcut" in app.status.get().lower()
        assert app._snapshot() == before
    finally:
        _destroy(app)


@pytest.mark.parametrize("scale", [1.0, 1.5, 2.0])
def test_search_results_and_actions_fit_compact_large_text(tk_root, monkeypatch, scale):
    monkeypatch.setattr("utterleaf.settings_ui.startup_enabled", lambda: False)
    monkeypatch.setattr("utterleaf.settings_ui.dictionary_text", lambda: "utter leaf = Utterleaf")
    baseline = float(tk_root.tk.call("tk", "scaling"))
    root = tk.Toplevel(tk_root)
    root.tk.call("tk", "scaling", baseline * scale)
    app = SettingsWindow(root, Config(), background=False)
    try:
        _show(app)
        left, top = root.winfo_rootx(), root.winfo_rooty()
        right, bottom = left + root.winfo_width(), top + root.winfo_height()
        row_height = tkfont.Font(root=root, font=app.search_results.cget("font")).metrics("linespace")
        for target in app.search_targets.values():
            _search(app, target.label)
            _select(app, target.key)
            for widget in (app.search_entry, app.search_results, app.search_detail_label,
                           app.search_open_button, app.search_close_button,
                           app.save_button, app.close_button):
                geometry = (scale, target.key, str(widget), widget.winfo_geometry())
                assert widget.winfo_ismapped(), geometry
                assert left <= widget.winfo_rootx(), geometry
                assert widget.winfo_rootx() + widget.winfo_width() <= right, geometry
                assert top <= widget.winfo_rooty(), geometry
                assert widget.winfo_rooty() + widget.winfo_height() <= bottom, geometry
            assert app.search_results.winfo_height() >= row_height + 2, (scale, target.key)
            assert app.search_detail_label.winfo_height() >= app.search_detail_label.winfo_reqheight(), (
                scale, target.key, app.search_detail_label.winfo_geometry(),
                app.search_detail_label.winfo_reqheight(),
            )
            assert target.label in app.search_detail.get()
            assert target.page_label in app.search_detail.get()
        app.search_entry.focus_force()
        root.update()
        app.search_entry.event_generate("<Escape>")
        root.update()
        assert not app.search_open
        _search(app, "clipboard")
        _select(app, "restore_clipboard")
        app.search_open_button.invoke()
        root.update()
        _assert_in_view(app, app.search_targets["restore_clipboard"].widget)
    finally:
        _destroy(app)
        tk_root.tk.call("tk", "scaling", baseline)
