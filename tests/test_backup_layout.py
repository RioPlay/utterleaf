"""Real-key and native-size backup review checks with synthetic data only."""
from contextlib import contextmanager

import pytest

import capture_backup
from test_capture_auxiliary import working_tk_display


@contextmanager
def dialog_fixture(state, scale=1.0):
    with capture_backup.blocked_runtime() as runtime, capture_backup.owned_root(scale) as (owner, errors):
        owner.geometry("1x1+5+5")
        owner.deiconify()
        owner.update()
        dialog = capture_backup.stage_dialog(owner, runtime, state)
        try:
            yield dialog, runtime
            assert not errors, errors
            assert not runtime.violations, runtime.violations
        finally:
            if dialog.root.winfo_exists():
                dialog.root.destroy()


def resize(dialog, size, *, minimum_height=None):
    dialog.root.geometry(f"{size[0]}x{size[1]}+70+50")
    dialog.root.deiconify()
    dialog.root.update()
    realized = (dialog.root.winfo_width(), dialog.root.winfo_height())
    assert realized[0] == size[0]
    if minimum_height is None:
        assert realized[1] == size[1]
    else:
        assert minimum_height <= realized[1] <= size[1]


def state(dialog):
    return ({key: variable.get() for key, variable in dialog.selected.items()},
            dialog.mode.get(), dialog.include_vocabulary.get(), dialog.review, dialog.payload,
            dialog.preview.get("1.0", "end-1c"))


def assert_bounds(widget, container):
    x, y = widget.winfo_rootx() - container.winfo_rootx(), widget.winfo_rooty() - container.winfo_rooty()
    width, height = widget.winfo_width(), widget.winfo_height()
    detail = (str(widget), widget.winfo_geometry(), (x, y), container.winfo_geometry())
    assert widget.winfo_ismapped(), detail
    assert 0 <= x and x + width <= container.winfo_width(), detail
    assert 0 <= y and y + height <= container.winfo_height(), detail
    assert width >= widget.winfo_reqwidth(), detail
    assert height >= widget.winfo_reqheight(), detail


@pytest.mark.parametrize("kind", ["export", "import", "error"])
@pytest.mark.parametrize("scale", [1.0, 1.5, 2.0])
def test_backup_compact_wide_compact_keeps_whole_controls_and_review(kind, scale, working_tk_display):
    with dialog_fixture(kind, scale) as (dialog, _runtime):
        resize(dialog, (480, 460))
        original = state(dialog)
        dialog.preview.tag_add("sel", "1.0", "1.6")
        selection = tuple(map(str, dialog.preview.tag_ranges("sel")))
        widgets = tuple(capture_backup.descendants(dialog.root))
        actions = [widget for widget in dialog.confirm.master.winfo_children()
                   if widget.winfo_class() == "TButton"]
        choices = [widget for widget in capture_backup.descendants(dialog.options_body)
                   if widget.winfo_class() in {"TCheckbutton", "TCombobox"}]
        assert len(actions) == 2
        details = dialog.feedback.details_button
        assert bool(details.winfo_ismapped()) is (kind == "error")
        assert len(choices) >= 11
        if kind == "export":
            vocabulary_choice = next(widget for widget in choices
                                     if str(widget.cget("variable")) == str(dialog.include_vocabulary))
            assert "comments excluded" in vocabulary_choice.cget("text").lower()
        compact_rows = None
        for size in ((480, 460), (1000, 700), (480, 460)):
            resize(dialog, size, minimum_height=620 if size == (1000, 700) else None)
            for action in actions:
                assert_bounds(action, dialog.root)
            if kind == "error":
                assert_bounds(details, dialog.root)
            assert dialog.options_canvas.winfo_height() >= 64
            assert dialog.preview.winfo_height() >= 64
            assert dialog.preview.winfo_width() >= 64
            preview_geometry = dialog.preview.winfo_geometry()
            action_geometry = [action.winfo_geometry() for action in actions]
            # Start traversal from a mapped control. Tk 9 may unmap canvas
            # descendants that remain fully above the viewport after resize.
            dialog.options_canvas.yview_moveto(0)
            dialog.root.update_idletasks()
            for choice in choices:
                choice.focus_force()
                dialog.root.update()
                assert dialog.root.focus_get() == choice, (
                    size, str(choice), choice.state(), choice.winfo_ismapped(), choice.winfo_geometry()
                )
                assert_bounds(choice, dialog.options_canvas)
                assert dialog.preview.winfo_geometry() == preview_geometry
                assert [action.winfo_geometry() for action in actions] == action_geometry
            assert state(dialog) == original
            assert tuple(map(str, dialog.preview.tag_ranges("sel"))) == selection
            assert str(dialog.preview.cget("state")) == "disabled"
            assert tuple(capture_backup.descendants(dialog.root)) == widgets
            rows = tuple(action.winfo_rooty() - actions[0].winfo_rooty() for action in actions)
            if size == (480, 460):
                if compact_rows is None:
                    compact_rows = rows
                else:
                    assert rows == compact_rows


@pytest.mark.parametrize("kind", ["export", "import"])
def test_backup_first_mouse_press_keeps_visible_checkbox_at_original_position(kind, working_tk_display):
    with dialog_fixture(kind, 2.0) as (dialog, runtime):
        resize(dialog, (480, 460))
        checkbox = next(widget for widget in capture_backup.descendants(dialog.options_body)
                        if widget.winfo_class() == "TCheckbutton")
        key = next(key for key, variable in dialog.selected.items()
                   if str(variable) == str(checkbox.cget("variable")))
        dialog.preview.focus_force()
        dialog.root.update()
        canvas = dialog.options_canvas
        canvas.yview_moveto(0)
        dialog.root.update()
        region = canvas.bbox("all")
        content_y = checkbox.winfo_rooty() - canvas.winfo_rooty()
        canvas.yview_moveto((content_y - 40) / (region[3] - region[1]))
        dialog.root.update()
        assert dialog.root.focus_get() == dialog.preview
        assert checkbox.winfo_rooty() - canvas.winfo_rooty() == pytest.approx(40, abs=1)
        assert_bounds(checkbox, canvas)
        before_view = canvas.yview()
        before_position = (checkbox.winfo_rootx(), checkbox.winfo_rooty())
        before_choices = {name: variable.get() for name, variable in dialog.selected.items()}
        before_mode = dialog.mode.get()
        before_vocabulary = dialog.include_vocabulary.get()
        changes = []
        dialog.selected[key].trace_add("write", lambda *_: changes.append(dialog.selected[key].get()))
        screen_x = checkbox.winfo_rootx() + 10
        screen_y = checkbox.winfo_rooty() + checkbox.winfo_height() // 2
        checkbox.event_generate("<ButtonPress-1>", x=10, y=checkbox.winfo_height() // 2,
                                rootx=screen_x, rooty=screen_y)
        dialog.root.update()
        assert canvas.yview() == before_view
        assert (checkbox.winfo_rootx(), checkbox.winfo_rooty()) == before_position
        checkbox.event_generate("<ButtonRelease-1>", x=screen_x - checkbox.winfo_rootx(),
                                y=screen_y - checkbox.winfo_rooty(), rootx=screen_x, rooty=screen_y)
        dialog.root.update()
        assert changes == [not before_choices[key]]
        assert {name: variable.get() for name, variable in dialog.selected.items()} == {
            **before_choices, key: not before_choices[key],
        }
        assert dialog.mode.get() == before_mode
        assert dialog.include_vocabulary.get() == before_vocabulary
        assert not runtime.violations
        assert not any(path.exists() for path in runtime.paths)


@pytest.mark.parametrize("kind", ["export", "import", "error"])
@pytest.mark.parametrize("sequence,direction", [("<Tab>", "next"), ("<Shift-Tab>", "previous")])
def test_backup_preview_native_tab_leaves_readonly_text(kind, sequence, direction, working_tk_display):
    with dialog_fixture(kind) as (dialog, _runtime):
        resize(dialog, (480, 460))
        preview = dialog.preview
        preview.focus_force()
        dialog.root.update()
        before = state(dialog)
        expected = preview.tk_focusNext() if direction == "next" else preview.tk_focusPrev()
        assert expected != preview
        preview.event_generate(sequence)
        dialog.root.update()
        assert dialog.root.focus_get() == expected
        assert state(dialog) == before
        preview.focus_force()
        dialog.root.update()
        preview.event_generate("<KeyPress-x>")
        preview.event_generate("<KeyRelease-x>")
        dialog.root.update()
        assert state(dialog) == before
        assert str(preview.cget("state")) == "disabled"


@pytest.mark.parametrize("kind", ["export", "import"])
def test_backup_cancel_remains_no_write_after_resize_and_preview_traversal(kind, working_tk_display):
    with dialog_fixture(kind, 2.0) as (dialog, runtime):
        for size in ((480, 460), (1000, 700), (480, 460)):
            resize(dialog, size, minimum_height=620 if size == (1000, 700) else None)
        cancel = next(widget for widget in capture_backup.descendants(dialog.root)
                      if widget.winfo_class() == "TButton" and widget.cget("text") == "Cancel")
        cancel.focus_force()
        dialog.root.update()
        cancel.event_generate("<KeyPress-space>")
        if cancel.winfo_exists():
            cancel.event_generate("<KeyRelease-space>")
        dialog.root.update()
        assert not dialog.root.winfo_exists()
        assert not runtime.violations
        assert not any(path.exists() for path in runtime.paths)
