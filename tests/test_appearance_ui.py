"""Artwork keyboard, compact-layout and recovery checks without real exports."""
from contextlib import contextmanager
import tkinter as tk
from tkinter import ttk

import pytest

import capture_appearance
from test_capture_auxiliary import working_tk_display


@contextmanager
def guide_fixture(scale=1.0):
    with capture_appearance.blocked_runtime() as runtime, capture_appearance.owned_root(scale) as (owner, errors):
        owner.geometry("1x1+5+5")
        owner.deiconify()
        owner.update()
        guide = capture_appearance.AppearanceGuide(owner)
        try:
            yield guide, runtime
            assert not errors, errors
            assert not runtime.violations, runtime.violations
        finally:
            if guide.root.winfo_exists():
                guide.close()


def resize(guide, size):
    guide.root.geometry(f"{size[0]}x{size[1]}+70+50")
    guide.root.deiconify()
    guide.root.update()
    assert (guide.root.winfo_width(), guide.root.winfo_height()) == size


def assert_bounds(widget, root):
    assert widget.winfo_ismapped(), str(widget)
    x, y = widget.winfo_rootx() - root.winfo_rootx(), widget.winfo_rooty() - root.winfo_rooty()
    width, height = widget.winfo_width(), widget.winfo_height()
    detail = (str(widget), (x, y, width, height), root.winfo_geometry())
    assert 0 <= x and x + width <= root.winfo_width(), detail
    assert 0 <= y and y + height <= root.winfo_height(), detail
    assert width >= widget.winfo_reqwidth(), detail
    assert height >= widget.winfo_reqheight(), detail


@pytest.mark.parametrize("scale", [1.0, 1.5, 2.0])
def test_artwork_all_tabs_actions_and_content_survive_compact_roundtrip(scale, working_tk_display):
    with guide_fixture(scale) as (guide, runtime):
        entries = dict(guide.entries)
        photos = tuple(guide.photos)
        for size in ((720, 540), (1000, 700), (720, 540)):
            resize(guide, size)
            assert len(guide.tabs.tabs()) == 5
            for name in capture_appearance.TABS:
                capture_appearance.select_tab(guide, name)
                guide.root.update()
                assert all(row["fits_text"] for row in capture_appearance.tab_bounds(guide))
                assert all(row["fits_horizontal"] for row in capture_appearance.content_bounds(guide, name))
                assert guide.canvases[name].winfo_height() >= 64
                for button in capture_appearance.descendants(guide.root):
                    if button.winfo_class() == "TButton" and str(button.cget("text")) != "Details…":
                        assert_bounds(button, guide.root)
            assert guide.entries == entries
            assert tuple(guide.photos) == photos
        assert not runtime.workers and not runtime.exports and not runtime.dialogs


@pytest.mark.parametrize("scale", [1.0, 1.5, 2.0])
def test_artwork_actual_page_keys_scroll_full_reference_without_moving_focus(scale, working_tk_display):
    with guide_fixture(scale) as (guide, runtime):
        resize(guide, (720, 540))
        capture_appearance.select_tab(guide, "Tray states")
        guide.root.update()
        guide.export_button.focus_force()
        guide.root.update()
        canvas = guide.canvases["Tray states"]
        assert canvas.yview()[1] < 1
        canvas.yview_moveto(0)
        for sequence, position in (("<Next>", "middle"), ("<Prior>", "top"),
                                   ("<End>", "bottom"), ("<Home>", "top")):
            guide.export_button.event_generate(sequence)
            guide.root.update()
            view = canvas.yview()
            if position == "middle":
                assert view[0] > 0
            elif position == "top":
                assert view[0] == pytest.approx(0)
            else:
                assert view[1] == pytest.approx(1)
            assert guide.root.focus_get() == guide.export_button
        assert not runtime.workers and not runtime.dialogs


def test_artwork_notebook_and_native_editor_keys_remain_native(working_tk_display):
    with guide_fixture() as (guide, _runtime):
        resize(guide, (720, 540))
        guide.tabs.focus_force()
        guide.root.update()
        before = guide.tabs.index(guide.tabs.select())
        guide.tabs.event_generate("<Control-Next>")
        guide.root.update()
        assert guide.tabs.index(guide.tabs.select()) == (before + 1) % 5
        guide.tabs.event_generate("<Control-Prior>")
        guide.root.update()
        assert guide.tabs.index(guide.tabs.select()) == before
        canvas = guide.canvases["Tray states"]
        canvas.yview_moveto(0.3)
        entry = ttk.Entry(guide.root)
        entry.place(x=30, y=30, width=160)
        entry.insert(0, "Synthetic input")
        entry.focus_force()
        guide.root.update()
        previous = canvas.yview()
        entry.event_generate("<End>")
        guide.root.update()
        assert entry.index("insert") == len(entry.get())
        entry.event_generate("<Home>")
        guide.root.update()
        assert entry.index("insert") == 0
        assert canvas.yview() == previous
        entry.destroy()


@pytest.mark.parametrize("scale", [1.0, 1.5, 2.0])
def test_artwork_export_failure_is_safe_inline_with_explicit_bounded_details(scale, working_tk_display):
    with guide_fixture(scale) as (guide, runtime):
        resize(guide, (720, 540))
        error = OSError("private-destination-token\x00\u202e" + "x" * 6000)
        capture_appearance.start_export(guide, runtime)
        assert str(guide.export_button.cget("state")) == "disabled"
        poll = guide.export_poll
        capture_appearance.start_export(guide, runtime)
        assert len(runtime.workers) == 1
        assert guide.export_poll == poll
        assert not runtime.exports
        capture_appearance.finish_export(guide, runtime, error)
        guide.root.update()
        assert not runtime.dialogs
        assert "private-destination-token" not in guide.status.get()
        assert "export" in guide.status.get().lower()
        assert str(guide.export_button.cget("state")) == "normal"
        assert guide.canvases["Tray states"].winfo_height() >= 100
        assert_bounds(guide.feedback.label, guide.root)
        for widget in capture_appearance.descendants(guide.root):
            if widget.winfo_class() == "TButton":
                assert_bounds(widget, guide.root)
        status, details = guide.status.get(), guide.feedback.details
        capture_appearance.start_export(guide, runtime, "")
        assert guide.status.get() == status
        assert guide.feedback.details == details
        assert not runtime.workers
        assert not runtime.dialogs
        guide.feedback.details_button.invoke()
        assert len(runtime.dialogs) == 1
        kind, args = runtime.dialogs[0]
        assert kind == "showinfo"
        assert "private-destination-token" in args[1]
        assert "\x00" not in args[1] and "\u202e" not in args[1]
        assert len(args[1]) < 2200
        capture_appearance.start_export(guide, runtime)
        assert guide.feedback.details == ""
        capture_appearance.finish_export(guide, runtime)
        guide.root.update()
        assert len(runtime.dialogs) == 1
        assert not guide.feedback.details
        assert str(guide.export_button.cget("state")) == "normal"


def test_artwork_cancelled_picker_does_not_start_export_and_close_cancels_ui_poll(working_tk_display):
    with guide_fixture() as (guide, runtime):
        resize(guide, (720, 540))
        capture_appearance.start_export(guide, runtime, "")
        assert not runtime.workers and not runtime.exports
        capture_appearance.start_export(guide, runtime)
        poll = guide.export_poll
        guide.close()
        guide.close()
        assert not guide.root.winfo_exists()
        assert poll not in guide.root.tk.call("after", "info")
        # Closing the reference does not revoke an already consented export.
        runtime.workers.pop(0)()
        guide._export_done()
        assert runtime.exports == ["synthetic-artwork.zip"]
        assert not runtime.dialogs


@pytest.mark.parametrize("boundary", ["picker", "worker"])
def test_artwork_export_start_failure_remains_retryable(boundary, working_tk_display, monkeypatch):
    with guide_fixture() as (guide, runtime):
        resize(guide, (720, 540))
        target = ("utterleaf.appearance.filedialog.asksaveasfilename" if boundary == "picker"
                  else "utterleaf.appearance.threading.Thread.start")
        with monkeypatch.context() as context:
            context.setattr(target, lambda *args, **kwargs: (_ for _ in ()).throw(OSError("private-start-token")))
            capture_appearance.start_export(guide, runtime)
        guide.root.update()
        assert not runtime.dialogs
        assert "private-start-token" not in guide.status.get()
        assert guide.feedback.details
        assert str(guide.export_button.cget("state")) == "normal"
        capture_appearance.start_export(guide, runtime)
        capture_appearance.finish_export(guide, runtime)
        assert str(guide.export_button.cget("state")) == "normal"
