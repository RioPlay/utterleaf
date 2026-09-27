"""Bounded local error disclosure; ordinary status never opens a dialog."""

import tkinter as tk
from tkinter import ttk

import pytest

from test_capture_auxiliary import capture_auxiliary
from utterleaf.ui_feedback import RecoveryFeedback, technical_details


def test_technical_details_preserves_unicode_and_removes_display_controls():
    value = "Café 東京 — naïve 😀\nnext\tcolumn\x00\x1b\x7f\x85\u202e\u2066\ud800"
    assert technical_details(value) == "Café 東京 — naïve 😀\nnext    column"


@pytest.mark.parametrize("value", ["", " \n\t ", "\x00\x1b\u202e\ud800"])
def test_technical_details_has_a_readable_empty_fallback(value):
    assert technical_details(value) == "No further technical information is available."


@pytest.mark.parametrize("value", ["x" * 161, "\n".join(["line"] * 13), "x" * 4097])
def test_technical_details_bounds_lines_width_and_input(value):
    visible = technical_details(value).splitlines()
    assert visible[-1] == "[Further technical details omitted]"
    assert 1 <= len(visible[:-1]) <= 12
    assert all(len(line) <= 160 for line in visible[:-1])
    assert len("\n".join(visible)) <= 12 * 161 + len(visible[-1])


def test_technical_details_keeps_exact_boundary_without_omission():
    value = "\n".join(["é" * 160] * 12)
    assert technical_details(value) == value


def test_technical_details_converts_an_exception_to_text_once():
    class CountedError(Exception):
        calls = 0

        def __str__(self):
            self.calls += 1
            return "A stable diagnostic"

    error = CountedError()
    assert technical_details(error) == "A stable diagnostic"
    assert error.calls == 1


@pytest.fixture
def feedback():
    with capture_auxiliary.blocked_runtime() as runtime, \
            capture_auxiliary.owned_root() as (root, errors):
        status = tk.StringVar(root, value="Waiting for an explicit action.")
        view = RecoveryFeedback(root, status)
        view.pack(fill="x")
        after = ttk.Button(root, text="Next action")
        after.pack()
        root.deiconify()
        root.update()
        yield view, runtime, after
        assert not errors, errors
        assert not runtime.violations


def test_details_are_explicit_only_and_replaced_by_the_current_error(feedback):
    view, runtime, _ = feedback
    assert not view.details_button.winfo_ismapped()
    assert view.details_button.instate(["disabled"])
    view.show_details()
    assert runtime.dialogs == []

    view.error("Could not complete the action", "Your draft remains available.",
               "Retry when ready.", "private/path\x00\u202e: native error")
    view.update()
    assert runtime.dialogs == []
    assert view.details_button.winfo_ismapped()
    assert not view.details_button.instate(["disabled"])
    assert "private/path" not in view.status.get()
    assert view.details == "private/path: native error"
    view.details_button.invoke()
    assert runtime.dialogs == [("Could not complete the action — Details", view.details)]

    view.error("A newer problem", "No result is available.", "Try another file.", "new context")
    assert len(runtime.dialogs) == 1
    view.show_details()
    assert runtime.dialogs[-1] == ("A newer problem — Details", "new context")
    assert "private/path" not in view.details


def test_status_change_clears_details_disables_action_and_moves_hidden_focus(feedback):
    view, runtime, after = feedback
    view.error("Could not complete the action", "Your draft remains available.",
               "Retry when ready.", "obsolete diagnostic")
    view.update()
    view.details_button.focus_force()
    view.update()
    assert view.focus_get() == view.details_button

    view.status.set("Opening the selected file…")
    view.update()
    assert view.details == view.problem == ""
    assert not view.details_button.winfo_ismapped()
    assert view.details_button.instate(["disabled"])
    assert view.focus_get() == after
    view.details_button.invoke()
    view.show_details()
    assert runtime.dialogs == []


def test_destroy_clears_details_and_removes_only_its_status_trace(feedback):
    view, runtime, _ = feedback
    changes = []
    other_trace = view.status.trace_add("write", lambda *_: changes.append(view.status.get()))
    view.error("Could not complete the action", "Your draft remains available.",
               "Retry when ready.", "obsolete diagnostic")
    view.destroy()
    assert view.details == view.problem == ""
    traces = view.status.trace_info()
    assert len(traces) == 1 and traces[0][1] == other_trace
    view.status.set("Later status")
    assert changes[-1] == "Later status"
    view.show_details()
    assert runtime.dialogs == []
