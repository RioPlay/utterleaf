"""Real Tk checks for the inert OBS session view; no OBS, model or audio access."""

from enum import Enum
import gc
from types import SimpleNamespace
import tkinter as tk
from tkinter import ttk

import pytest

from utterleaf import obs_session_ui as ui


class RecognitionState(Enum):
    WAITING = "waiting"
    RUNNING = "running"
    COMPLETE = "complete"
    INCOMPLETE = "incomplete"
    FAILED = "failed"
    CANCELLED = "cancelled"
    EMPTY = "empty"


def session(state="disabled", message="OBS transcription is off.", *, degraded=False,
            primary=None, buses=(), seconds=0.0):
    return SimpleNamespace(state=state, message=message, control_degraded=degraded,
                           primary_bus=primary, buses=buses, captured_seconds=seconds)


def recognition(state=RecognitionState.WAITING, message="Waiting for OBS audio.", *,
                preview="", tracks=0, completed=0, incomplete=False):
    return SimpleNamespace(state=state, message=message, preview=preview,
                           track_count=tracks, completed_tracks=completed,
                           incomplete=incomplete)


class Source:
    def __init__(self, value):
        self.value = value
        self.calls = 0

    def snapshot(self):
        self.calls += 1
        return self.value


class Actions:
    def __init__(self):
        self.calls = []
        self.connect_result = True
        self.failure = None

    def _call(self, name, *args):
        self.calls.append((name, *args))
        if self.failure == name:
            raise RuntimeError("PRIVATE CALLBACK DETAIL")

    def connect(self, host, port, password, expected_executable):
        self._call("connect", host, port, password, expected_executable)
        return self.connect_result

    def arm(self, additional_mix_mask):
        self._call("arm", additional_mix_mask)

    def disarm(self):
        self._call("disarm")

    def cancel(self):
        self._call("cancel")

    def pair(self):
        self._call("pair")

    def export(self, bus, format_name):
        self._call("export", bus, format_name)

    def close(self):
        self._call("close")


@pytest.fixture(scope="module")
def tk_root():
    try:
        root = tk.Tk()
    except tk.TclError as error:
        pytest.skip(f"Tk display unavailable: {error}")
    root.withdraw()
    yield root
    root.destroy()
    gc.collect()


@pytest.fixture
def opened(tk_root):
    windows = []
    tk_root.deiconify()

    def make(session_value=None, recognition_value=None):
        controller = Source(session_value or session())
        coordinator = Source(recognition_value or recognition())
        actions = Actions()
        window = ui.ObsSessionWindow(tk_root, controller, coordinator, actions,
                                     poll_ms=10_000)
        windows.append(window)
        tk_root.update()
        return window, controller, coordinator, actions

    yield make
    for window in windows:
        window.close()
    tk_root.update()
    tk_root.withdraw()
    windows.clear()
    gc.collect()


def state(widget) -> str:
    return str(widget.cget("state"))


def test_construction_and_refresh_only_read_snapshots(opened):
    window, controller, coordinator, actions = opened()
    assert actions.calls == []
    assert controller.calls >= 1 and coordinator.calls >= 1
    assert state(window.connect_button) == "normal"
    assert state(window.arm_button) == state(window.stop_button) == "disabled"
    assert window.password_entry.cget("show") and "password" not in repr(window).lower()
    assert not bool(int(window.preview.cget("exportselection")))


@pytest.mark.parametrize("host,port,password,path,focus", [
    ("localhost", "4455", "pw", r"C:\\OBS\\obs64.exe", "host"),
    ("127.0.0.1", "0", "pw", r"C:\\OBS\\obs64.exe", "port"),
    ("127.0.0.1", "4455", "", r"C:\\OBS\\obs64.exe", "password"),
    ("127.0.0.1", "4455", "pw", "obs64.exe", "executable"),
])
def test_connect_validation_is_local_and_password_is_cleared(opened, tk_root,
                                                              host, port, password, path, focus):
    window, _controller, _coordinator, actions = opened()
    window.host_var.set(host)
    window.port_var.set(port)
    window.password_var.set(password)
    window.executable_var.set(path)
    window.close_button.focus_force()
    tk_root.update()
    window.connect_button.invoke()
    tk_root.update()
    assert actions.calls == []
    assert window.password_var.get() == ""
    assert window.connection_error.get()
    target = getattr(window, focus + "_entry")
    assert window.root.focus_get() is target


def test_connect_forwards_exact_intent_then_clears_and_collapses_inputs(opened):
    window, _controller, _coordinator, actions = opened()
    window.port_var.set("4455")
    window.password_var.set("do-not-retain")
    window.executable_var.set(r"C:\Program Files\obs-studio\bin\64bit\obs64.exe")
    window.connect_button.invoke()
    assert actions.calls == [
        ("connect", "127.0.0.1", 4455, "do-not-retain",
         r"C:\Program Files\obs-studio\bin\64bit\obs64.exe")
    ]
    assert window.password_var.get() == ""
    window.root.update_idletasks()
    assert not window.connection_card.winfo_ismapped()
    assert window.connection_summary.winfo_ismapped()
    assert "do-not-retain" not in repr(window)


def test_connected_transition_clears_password_and_moves_hidden_focus(opened, tk_root):
    window, controller, _coordinator, _actions = opened()
    window.password_var.set("not-submitted")
    window.password_entry.focus_force()
    tk_root.update()
    controller.value = session("ready", "Authenticated and idle.")
    window.refresh()
    tk_root.update()
    assert window.password_var.get() == ""
    assert window.root.focus_get() is window.arm_button
    assert window.connection_summary_title.get() == "Local OBS connection"


def test_connection_latch_does_not_keep_summary_during_capture_or_result(opened, tk_root):
    window, controller, coordinator, _actions = opened()
    window.password_var.set("submitted")
    window.executable_var.set(r"C:\OBS\obs64.exe")
    window.connect_button.invoke()
    for value in (
        session("ready"), session("armed"),
        session("active", primary=0, buses=(0,), seconds=4),
        session("incomplete", primary=0, buses=(0,), seconds=5),
    ):
        controller.value = value
        coordinator.value = recognition(
            RecognitionState.INCOMPLETE if value.state == "incomplete" else RecognitionState.RUNNING,
            preview="Words", tracks=1, completed=int(value.state == "incomplete"),
            incomplete=value.state == "incomplete",
        )
        window.refresh()
        tk_root.update()
        assert bool(window.connection_summary.winfo_ismapped()) is (
            value.state in {"ready", "armed"}
        )
    assert window.preview.winfo_height() >= 140


@pytest.mark.parametrize("controller_state,recognition_state,tracks,connect,arm,stop,cancel,pair,export", [
    ("disabled", RecognitionState.WAITING, 0, True, False, False, False, True, False),
    ("connecting", RecognitionState.WAITING, 0, False, False, False, True, False, False),
    ("busy", RecognitionState.WAITING, 0, False, False, False, False, True, False),
    ("ready", RecognitionState.WAITING, 0, False, True, False, False, True, False),
    ("preparing", RecognitionState.WAITING, 0, False, False, False, True, False, False),
    ("armed", RecognitionState.WAITING, 0, False, False, True, True, False, False),
    ("active", RecognitionState.RUNNING, 1, False, False, True, True, False, False),
    ("stopping", RecognitionState.RUNNING, 1, False, False, True, True, False, False),
    ("finalizing", RecognitionState.RUNNING, 1, False, False, False, True, False, False),
    ("complete", RecognitionState.COMPLETE, 1, False, False, False, True, True, True),
    ("incomplete", RecognitionState.INCOMPLETE, 1, False, False, False, True, True, True),
    ("error", RecognitionState.FAILED, 1, False, False, False, True, True, True),
    ("empty", RecognitionState.EMPTY, 0, False, False, False, False, True, False),
    ("cancelled", RecognitionState.CANCELLED, 0, False, False, False, False, True, False),
])
def test_state_matrix_controls_only_valid_intents(opened, controller_state, recognition_state,
                                                   tracks, connect, arm, stop, cancel, pair, export):
    window, _controller, _coordinator, _actions = opened(
        session(controller_state, primary=0 if tracks else None, buses=(0,) if tracks else ()),
        recognition(recognition_state, tracks=tracks,
                    preview="Retained words" if export else ""),
    )
    expected = {
        window.connect_button: connect,
        window.arm_button: arm,
        window.stop_button: stop,
        window.cancel_button: cancel,
        window.pair_button: pair,
        window.export_button: export,
    }
    for widget, enabled in expected.items():
        assert (state(widget) != "disabled") is enabled


def test_mix_arm_degraded_stop_and_cancel_forward_only_user_intent(opened):
    window, controller, coordinator, actions = opened(session("ready"))
    window.mix_vars[0].set(True)
    window.mix_vars[5].set(True)
    window.arm_button.invoke()
    window.root.update_idletasks()
    assert actions.calls == [("arm", 33)]

    controller.value = session("active", "Transcribing locally.", degraded=True,
                               primary=3, buses=(0, 3, 5), seconds=125.8)
    coordinator.value = recognition(RecognitionState.RUNNING, preview="Bus 4: hello",
                                    tracks=3)
    window.refresh()
    assert "Controls disconnected" in window.degraded_text.get()
    assert "Primary: Mix 4" in window.capture_meta.get() and "2:05" in window.capture_meta.get()
    assert state(window.stop_button) == "normal"
    window.stop_button.invoke()
    window.cancel_button.invoke()
    assert actions.calls[-2:] == [("disarm",), ("cancel",)]


def test_export_requires_retained_output_and_uses_actual_bus(opened):
    window, _controller, _coordinator, actions = opened(
        session("incomplete", primary=2, buses=(0, 2)),
        recognition(RecognitionState.INCOMPLETE, preview="Recovered words", tracks=2,
                    completed=2, incomplete=True),
    )
    assert window.export_bus_var.get() == "Mix 3 · primary"
    window.export_format_var.set("JSON (.json)")
    window.export_button.invoke()
    assert actions.calls == [("export", 2, "json")]


def test_export_ignores_invalid_snapshot_bus_without_mispairing(opened):
    window, _controller, _coordinator, actions = opened(
        session("incomplete", primary=2, buses=(99, 2)),
        recognition(RecognitionState.INCOMPLETE, preview="Recovered words", tracks=1,
                    completed=1, incomplete=True),
    )
    assert window.export_bus_var.get() == "Mix 3 · primary"
    window.export_button.invoke()
    assert actions.calls == [("export", 2, "txt")]


@pytest.mark.parametrize("recognition_state", [
    RecognitionState.COMPLETE,
    RecognitionState.INCOMPLETE,
    RecognitionState.FAILED,
])
def test_terminal_tracks_without_readable_preview_cannot_export(opened, recognition_state):
    window, _controller, _coordinator, actions = opened(
        session("error", primary=0, buses=(0,)),
        recognition(recognition_state, "Cleanup failed after the result was discarded.",
                    preview="   ", tracks=1, completed=1, incomplete=True),
    )
    assert state(window.export_button) == "disabled"
    assert state(window.export_bus) == "disabled"
    window.export_button.invoke()
    assert actions.calls == []


def test_callback_failure_is_sanitized_in_visible_status(opened, tk_root):
    window, _controller, _coordinator, actions = opened(session("ready"))
    actions.failure = "arm"
    window.arm_button.invoke()
    tk_root.update_idletasks()
    assert "PRIVATE CALLBACK DETAIL" not in window.action_error.get()
    assert window.action_error.get() and window.action_error_label.winfo_ismapped()


def test_keyboard_focus_escape_close_and_no_stale_poll(opened, tk_root):
    window, controller, coordinator, actions = opened()
    window.root.deiconify()
    window.host_entry.focus_force()
    tk_root.update()
    assert window.root.focus_get() is window.host_entry
    assert window.host_entry.tk_focusNext() is not None
    before = (controller.calls, coordinator.calls)
    window.root.event_generate("<Escape>")
    tk_root.update()
    assert window.closed and actions.calls == [("close",)]
    window.refresh()
    tk_root.update()
    assert (controller.calls, coordinator.calls) == before
    window.close()
    assert actions.calls == [("close",)]


def test_close_clears_unsubmitted_password(opened):
    window, _controller, _coordinator, actions = opened()
    window.password_var.set("typed-but-not-submitted")
    window.close()
    assert window.password_var.get() == ""
    assert actions.calls == [("close",)]


def test_compact_layout_and_long_copy_keep_primary_controls_visible(opened, tk_root):
    long_message = "A clear local status remains readable. " * 18
    long_preview = ("Bus 1: locally recognized words stay in the bounded preview.\n" * 30).strip()
    window, _controller, _coordinator, _actions = opened(
        session("active", long_message, primary=0, buses=(0, 1), seconds=3723),
        recognition(RecognitionState.RUNNING, long_message, preview=long_preview, tracks=2),
    )
    window.root.deiconify()
    window.root.geometry("560x520+40+40")
    tk_root.update()
    left, top = window.root.winfo_rootx(), window.root.winfo_rooty()
    right, bottom = left + window.root.winfo_width(), top + window.root.winfo_height()
    for button in (window.stop_button, window.cancel_button, window.close_button):
        assert left <= button.winfo_rootx() < right
        assert top <= button.winfo_rooty() and button.winfo_rooty() + button.winfo_height() <= bottom
    assert window.preview.winfo_height() >= 100
    assert int(window.message_label.cget("wraplength")) <= 440
    assert window.preview.get("1.0", "end-1c") == long_preview


@pytest.mark.parametrize("controller_value,recognition_value", [
    (
        session("active", primary=0, buses=(0, 1), seconds=25),
        recognition(RecognitionState.RUNNING, preview="Active transcript", tracks=2),
    ),
    (
        session("active", degraded=True, primary=0, buses=(0, 1), seconds=25),
        recognition(RecognitionState.RUNNING, preview="Degraded transcript", tracks=2),
    ),
    (
        session("incomplete", primary=0, buses=(0, 1), seconds=25),
        recognition(RecognitionState.INCOMPLETE, preview="Recovered transcript", tracks=2,
                    completed=1, incomplete=True),
    ),
])
def test_normal_capture_states_keep_transcript_readable(opened, tk_root,
                                                        controller_value,
                                                        recognition_value):
    window, _controller, _coordinator, _actions = opened(
        controller_value, recognition_value,
    )
    window.root.geometry("840x720+40+40")
    tk_root.update()
    assert window.preview.winfo_height() >= 140


def test_disabled_connection_form_fits_supported_compact_size(opened, tk_root):
    window, _controller, _coordinator, _actions = opened()
    window.root.geometry("560x520+40+40")
    tk_root.update()
    left, top = window.root.winfo_rootx(), window.root.winfo_rooty()
    right, bottom = left + window.root.winfo_width(), top + window.root.winfo_height()
    assert window.connection_card.winfo_ismapped()
    assert not window.capture_card.winfo_ismapped()
    assert not window.transcript_card.winfo_ismapped()
    assert int(window.connection_hint.cget("wraplength")) <= 440
    assert window.connection_hint.winfo_height() == window.connection_hint.winfo_reqheight()
    for widget in (
        window.host_entry, window.port_entry, window.password_entry,
        window.executable_entry, window.browse_button, window.connect_button,
        window.close_button,
    ):
        assert left <= widget.winfo_rootx()
        assert widget.winfo_rootx() + widget.winfo_width() <= right
        assert top <= widget.winfo_rooty()
        assert widget.winfo_rooty() + widget.winfo_height() <= bottom


def test_browse_is_explicit_and_render_never_opens_picker(opened, monkeypatch):
    calls = []
    monkeypatch.setattr(ui.filedialog, "askopenfilename",
                        lambda **kwargs: calls.append(kwargs) or r"C:\OBS\obs64.exe")
    window, _controller, _coordinator, _actions = opened()
    assert calls == []
    window.browse_button.invoke()
    assert len(calls) == 1 and window.executable_var.get() == r"C:\OBS\obs64.exe"
