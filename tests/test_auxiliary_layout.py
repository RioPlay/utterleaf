"""Native auxiliary layout/keyboard checks using synthetic, guarded workflows."""

from dataclasses import asdict
import importlib.util
from itertools import combinations
from pathlib import Path
from types import SimpleNamespace
import tkinter as tk
from unittest.mock import patch

import pytest

from test_capture_auxiliary import working_tk_display
from utterleaf.ui_layout import ActionRow, ScrollableContent


SOURCE = Path(__file__).with_name("capture_auxiliary.py")
SPEC = importlib.util.spec_from_file_location("utterleaf_auxiliary_layout_capture", SOURCE)
assert SPEC is not None and SPEC.loader is not None
capture_auxiliary = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(capture_auxiliary)

MINIMUM = {"file": (760, 560), "decoder": (560, 500), "review": (480, 320)}
LONG_TEXT = "\n".join(f"Line {number:02}: sample." for number in range(1, 81))


def descendants(widget):
    for child in widget.winfo_children():
        yield child
        yield from descendants(child)


def surface(root, state):
    widgets = tuple(descendants(root))
    content, = (widget for widget in widgets if isinstance(widget, ScrollableContent))
    rows = [widget for widget in widgets if isinstance(widget, ActionRow)
            and not str(widget).startswith(str(content.body) + ".")]
    assert rows, "Actions must remain outside the scrolling body"
    controls = tuple(control for row in rows for control in row.controls)
    buttons = tuple(widget for widget in widgets if widget.winfo_class() == "TButton"
                    and any(str(widget).startswith(str(row) + ".") for row in rows))
    previews = [widget for widget in widgets if isinstance(widget, tk.Text)]
    return SimpleNamespace(root=root, content=content, controls=controls,
                           buttons=buttons, preview=previews[0] if previews else None,
                           widgets=widgets, state=state)


def visit_surface(kind, scale, visit, *, long_preview=False):
    text = LONG_TEXT if long_preview else capture_auxiliary.SAMPLE_TEXT
    result = capture_auxiliary.Transcript((capture_auxiliary.Segment(0, 4, text),), "en")
    with patch.object(capture_auxiliary, "SAMPLE_TEXT", text), \
            patch.object(capture_auxiliary, "SAMPLE_RESULT", result), \
            capture_auxiliary.blocked_runtime() as runtime, \
            capture_auxiliary.owned_root(scale) as (owner, errors):
        if kind == "file":
            window = capture_auxiliary.file_ui.FileWindow(owner, capture_auxiliary.Config())
            window.audio_track.set("4")
            window.format.set("SRT")
            capture_auxiliary.stage_file(window, runtime, "result")

            def state():
                return (asdict(window.cfg), window.audio_track.get(), window.format.get(),
                        window.result, window.filename.get(), window.busy,
                        window.preview.get("1.0", "end-1c"))

            view = surface(owner, state)
            view.window = window
            visit(view)
            assert runtime.threads == ["utterleaf-file"]
        elif kind == "decoder":
            owner.deiconify()
            owner.update()
            runtime.decoder = {"path": "synthetic-tools/ffmpeg.exe"}
            dialog = capture_auxiliary.file_decoder_ui.DecoderDialog(owner)
            try:
                visit(surface(dialog.root, lambda: (dialog.status.get(), dict(runtime.decoder))))
            finally:
                dialog.root.destroy()
            assert runtime.threads == []
        else:
            def review_visit():
                view = surface(owner, lambda: tuple(
                    (str(widget.cget("text")), str(widget.cget("state")))
                    for widget in descendants(owner) if widget.winfo_class() == "TButton"))
                visit(view)

            response = capture_auxiliary.render_review(owner, False, review_visit)
            assert response == "ready\n", "Layout or navigation must not emit a review action"
            assert runtime.threads == ["utterleaf-review-control"]
        assert not runtime.exports and not runtime.violations
        assert not errors, errors


def resize(root, size):
    root.geometry(f"{size[0]}x{size[1]}+50+40")
    if not root.winfo_ismapped():
        root.deiconify()
    root.update()
    assert (root.winfo_width(), root.winfo_height()) == size


def rectangle(widget):
    x, y = widget.winfo_rootx(), widget.winfo_rooty()
    return x, y, x + widget.winfo_width(), y + widget.winfo_height()


def assert_fixed_actions_fit(view):
    left, top, right, bottom = rectangle(view.root)
    assert view.content.canvas.winfo_height() > 1, "Actions must leave a readable viewport"
    assert view.content.body.winfo_height() == max(
        view.content.canvas.winfo_height(), view.content.body.winfo_reqheight())
    assert view.content._resize_id is None, "Local layout must settle instead of scheduling forever"
    for control in (*view.controls, *view.buttons):
        assert control.winfo_ismapped()
        x0, y0, x1, y1 = rectangle(control)
        assert left <= x0 < x1 <= right, (control, "horizontal bounds", (x0, x1), (left, right))
        assert top <= y0 < y1 <= bottom, (control, "vertical bounds", (y0, y1), (top, bottom))
        assert control.winfo_width() >= control.winfo_reqwidth()
        assert control.winfo_height() >= control.winfo_reqheight()
    for first, second in combinations(view.controls, 2):
        a, b = rectangle(first), rectangle(second)
        assert a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1], \
            ("Footer controls overlap", first, second)


@pytest.mark.parametrize("kind", ["file", "decoder", "review"])
@pytest.mark.parametrize("scale", [1.0, 1.5, 2.0])
def test_auxiliary_minimum_wide_minimum_keeps_actions_and_state(kind, scale, working_tk_display):
    def visit(view):
        resize(view.root, MINIMUM[kind])
        initial = view.state()
        preview_text = None
        if view.preview is not None:
            preview_text = view.preview.get("1.0", "end-1c")
            view.preview.tag_add("sel", "1.0", "1.6")
        focused = next(button for button in view.buttons if not button.instate(["disabled"]))
        focused.focus_force()
        view.root.update()
        assert view.root.focus_get() == focused
        compact_rows = None
        for size in (MINIMUM[kind], (1000, 620), MINIMUM[kind]):
            resize(view.root, size)
            assert_fixed_actions_fit(view)
            assert tuple(descendants(view.root)) == view.widgets
            assert view.root.focus_get() == focused
            for button in (widget for widget in view.widgets
                           if widget.winfo_class() == "TButton"
                           and str(widget).startswith(str(view.content.body) + ".")
                           and not widget.instate(["disabled"])):
                button.focus_force()
                view.root.update()
                x0, y0, x1, y1 = rectangle(button)
                left, top, right, bottom = rectangle(view.content.canvas)
                assert left <= x0 < x1 <= right and top <= y0 < y1 <= bottom
                assert view.root.focus_get() == button
            focused.focus_force()
            view.root.update()
            assert view.state() == initial
            if preview_text is not None:
                assert view.preview.get("1.0", "end-1c") == preview_text
                assert tuple(map(str, view.preview.tag_ranges("sel"))) == ("1.0", "1.6")
                assert str(view.preview.cget("state")) == "disabled"
            rows = tuple(control.winfo_rooty() - view.controls[0].winfo_rooty()
                         for control in view.controls)
            if size == MINIMUM[kind]:
                if compact_rows is None:
                    compact_rows = rows
                else:
                    assert rows == compact_rows, "Narrowing must restore the original action layout"
        canvas = view.content.canvas
        canvas.yview_moveto(0)
        view.root.update()
        if scale == 2.0:
            assert canvas.yview()[1] < 1, "Large-text fixture must exercise body scrolling"
        if canvas.yview()[1] < 1:
            focused.event_generate("<Next>")
            view.root.update()
            assert canvas.yview()[0] > 0, "Page Down from a fixed action must scroll the body"
            focused.event_generate("<Home>")
            view.root.update()
            assert canvas.yview()[0] == pytest.approx(0)
        assert view.root.focus_get() == focused
        assert view.state() == initial

    visit_surface(kind, scale, visit)


def assert_insert_visible(view):
    line = view.preview.dlineinfo("insert")
    assert line is not None, "Insertion line is outside the native preview"
    line_top = view.preview.winfo_rooty() + line[1]
    viewport_top = view.content.canvas.winfo_rooty()
    assert line_top >= viewport_top
    assert line_top + line[3] <= viewport_top + view.content.canvas.winfo_height()


@pytest.mark.parametrize("kind", ["file", "review"])
@pytest.mark.parametrize("scale", [1.0, 1.5, 2.0])
def test_auxiliary_preview_tab_and_held_keys_keep_read_only_line_visible(kind, scale, working_tk_display):
    def visit(view):
        preview = view.preview
        preview.configure(height=32)
        resize(view.root, MINIMUM[kind])
        assert preview.winfo_height() > view.content.canvas.winfo_height()
        original = preview.get("1.0", "end-1c")
        preview.mark_set("insert", "1.0")
        before = preview.tk_focusPrev()
        assert before is not None and before != preview
        before.focus_force()
        view.root.update()
        before.event_generate("<Tab>")
        view.root.update()
        assert view.root.focus_get() == preview
        assert_insert_visible(view)
        after = preview.tk_focusNext()
        preview.event_generate("<Tab>")
        view.root.update()
        assert view.root.focus_get() == after
        after.event_generate("<Shift-Tab>")
        view.root.update()
        assert view.root.focus_get() == preview
        for _ in range(35):
            preview.event_generate("<KeyPress-Down>")
            view.root.update()
            assert_insert_visible(view)
        preview.event_generate("<KeyRelease-Down>")
        assert preview.index("insert") == "36.0"
        # More-specific page bindings must still follow native Text movement.
        for sequence, expected in (("<Control-End>", "end-1c"), ("<Control-Home>", "1.0")):
            preview.event_generate(sequence)
            view.root.update()
            assert preview.index("insert") == preview.index(expected)
            assert_insert_visible(view)
        preview.event_generate("<KeyPress-x>")
        preview.event_generate("<KeyRelease-x>")
        view.root.update()
        assert preview.get("1.0", "end-1c") == original
        assert str(preview.cget("state")) == "disabled"

    visit_surface(kind, scale, visit, long_preview=True)


def test_auxiliary_native_picker_keys_do_not_scroll_the_page(working_tk_display):
    def visit(view):
        resize(view.root, MINIMUM["file"])
        window = view.window
        window.audio_track_input.focus_force()
        view.root.update()
        window.audio_track_input.icursor(1)
        initial = view.content.canvas.yview()
        window.audio_track_input.event_generate("<Home>")
        view.root.update()
        assert window.audio_track_input.index("insert") == 0
        assert view.content.canvas.yview() == pytest.approx(initial)
        window.audio_track_input.event_generate("<End>")
        view.root.update()
        assert window.audio_track_input.index("insert") == len(window.audio_track.get())
        assert view.content.canvas.yview() == pytest.approx(initial)
        # A first click into a visible field must not move it under the pointer.
        footer = next(button for button in view.buttons if not button.instate(["disabled"]))
        footer.focus_force()
        view.root.update()
        initial = view.content.canvas.yview()
        spinbox = window.audio_track_input
        spinbox.event_generate("<ButtonPress-1>", x=10, y=spinbox.winfo_height() // 2)
        spinbox.event_generate("<ButtonRelease-1>", x=10, y=spinbox.winfo_height() // 2)
        view.root.update()
        assert view.root.focus_get() == spinbox
        assert view.content.canvas.yview() == pytest.approx(initial)
        picker, = (widget for widget in descendants(view.root) if widget.winfo_class() == "TCombobox")
        picker.focus_force()
        view.root.update()
        initial = view.content.canvas.yview()
        picker.event_generate("<Next>")
        view.root.update()
        assert view.content.canvas.yview() == pytest.approx(initial)
        assert window.audio_track.get() == "4"

    visit_surface("file", 2.0, visit)


def test_auxiliary_page_and_wheel_keys_allow_lock_keys_not_modified_shortcuts(working_tk_display):
    def visit(view):
        resize(view.root, MINIMUM["file"])
        canvas = view.content.canvas
        assert canvas.yview()[1] < 1
        footer = next(button for button in view.buttons if not button.instate(["disabled"]))
        footer.focus_force()
        view.root.update()
        aqua = view.root.tk.call("tk", "windowingsystem") == "aqua"
        for locks in ((0, 0x2) if aqua else (0, 0x2, 0x10, 0x12)):
            canvas.yview_moveto(0)
            footer.event_generate("<Next>", state=locks)
            view.root.update()
            assert canvas.yview()[0] > 0
            canvas.yview_moveto(0)
            canvas.event_generate("<MouseWheel>", delta=-120, state=locks)
            view.root.update()
            assert canvas.yview()[0] > 0
        for modifier in (0x1, 0x4, 0x8, 0x20, 0x40, 0x80, 0x20000):
            initial = canvas.yview()
            footer.event_generate("<Next>", state=modifier)
            canvas.event_generate("<MouseWheel>", delta=-120, state=modifier)
            view.root.update()
            assert canvas.yview() == pytest.approx(initial)
        assert view.root.focus_get() == footer

    visit_surface("file", 2.0, visit)


@pytest.mark.parametrize("kind", ["file", "review"])
def test_auxiliary_preview_scrollbar_wheel_does_not_also_scroll_outer_body(kind, working_tk_display):
    def visit(view):
        preview = view.preview
        preview.configure(height=32)
        resize(view.root, MINIMUM[kind])
        scrollbar, = (widget for widget in preview.master.winfo_children()
                      if widget.winfo_class() in {"Scrollbar", "TScrollbar"})
        preview.yview_moveto(0.2)
        view.content.canvas.yview_moveto(0.2)
        view.root.update()
        inner_before = preview.yview()
        outer_before = view.content.canvas.yview()
        assert 0 < inner_before[0] < inner_before[1] < 1
        assert 0 < outer_before[0] < outer_before[1] < 1
        original = preview.get("1.0", "end-1c")
        scrollbar.event_generate("<MouseWheel>", delta=-120, state=0)
        view.root.update()
        assert preview.yview()[0] > inner_before[0], "Native scrollbar must still scroll its preview"
        assert view.content.canvas.yview() == pytest.approx(outer_before)
        assert preview.get("1.0", "end-1c") == original
        assert str(preview.cget("state")) == "disabled"

    visit_surface(kind, 2.0, visit, long_preview=True)
