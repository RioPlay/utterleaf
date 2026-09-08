from utterleaf.indicator import appearance, decode_pill, encode_pill


def test_hide_has_no_appearance() -> None:
    assert appearance("hide") is None
    assert appearance("idle") is None


def test_listening_is_red() -> None:
    look = appearance("listening")
    assert look is not None
    assert look[0] == "Listening"
    assert look[2].lower() == "#e46962"


def test_transcribing_and_loading_are_visible() -> None:
    assert appearance("transcribing")[0] == "Transcribing"
    assert appearance("loading")[0] == "Loading"
    assert appearance("pasted")[0] == "Pasted"
    assert appearance("missed")[0] == "Didn't hear"
    assert appearance("too_short")[0] == "Too short"
    assert appearance("clipboard")[0] == "On clipboard"


def test_live_caption_does_not_change_kind() -> None:
    look = appearance("listening")
    assert look is not None
    assert look[0] == "Listening"


def test_pill_wire_protocol_round_trips() -> None:
    assert decode_pill(encode_pill("listening", "hello")) == ("listening", "hello")
    assert decode_pill("quit\n") == "quit"
    assert decode_pill(encode_pill("missed", "a\tb\nc")) == ("missed", "a b c")


def test_win32_colorref_keeps_listening_red() -> None:
    from utterleaf.indicator import _hex_bgr

    color = _hex_bgr(appearance("listening")[2])
    assert color & 0xFF == 0xE4
    assert (color >> 8) & 0xFF == 0x69
    assert (color >> 16) & 0xFF == 0x62


def test_tk_long_caption_stays_inside_window(monkeypatch):
    import queue
    import time
    import tkinter as tk
    import pytest
    from utterleaf import indicator

    try:
        root = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"Tk needs a working display: {exc}")
    monkeypatch.setattr(tk, "Tk", lambda: root)
    events = queue.Queue()
    events.put(("listening", "W" * 160))
    bounds = []
    deadline = time.monotonic() + 5

    def inspect():
        retrying = False
        try:
            canvas = next(
                (child for child in root.winfo_children() if isinstance(child, tk.Canvas)), None
            )
            texts = [item for item in canvas.find_all() if canvas.type(item) == "text"] if canvas else []
            # The caption paint and the window resize land asynchronously on
            # slow CI; wait until both are visible or the deadline passes.
            ready = canvas is not None and len(texts) >= 2 and canvas.winfo_width() >= 460
            if not ready and time.monotonic() < deadline:
                root.after(25, inspect)
                retrying = True
                return
            bounds.append(
                (canvas.bbox(texts[-1]) if texts else None, canvas.winfo_width(), canvas.winfo_height())
            )
        finally:
            # A retry must keep the mainloop alive; only a finished inspection quits.
            if not retrying:
                events.put("quit")

    root.after(150, inspect)
    root.after(6000, lambda: events.put("quit"))
    indicator._run_tk(events)
    assert len(bounds) == 1, "caption never rendered within the deadline"
    box, width, height = bounds[0]
    assert box is not None, "caption text item is missing"
    left, top, right, bottom = box
    assert 0 <= left < right <= width
    assert 0 <= top < bottom <= height - 8


def test_close_waits_for_worker_and_restart_uses_fresh_queue(monkeypatch):
    import threading
    from utterleaf import indicator

    stopped = threading.Event()
    queues = []

    def renderer(events):
        queues.append(events)
        while events.get() != "quit":
            pass
        stopped.set()

    monkeypatch.setattr(indicator, "pill_backend", lambda: renderer)
    pill = indicator.Indicator()
    pill.start()
    worker = pill._thread
    pill.close()
    assert stopped.is_set()
    assert not worker.is_alive()
    pill._q.put("quit")  # stale queued data must not stop the next renderer
    stopped.clear()
    pill.enabled = True
    pill.start()
    pill.close()
    assert stopped.is_set()
    assert len(queues) == 2 and queues[0] is not queues[1]


def test_close_terminates_only_its_unresponsive_child(monkeypatch):
    import io
    import subprocess
    from utterleaf import indicator

    calls = []

    class Child:
        stdin = io.StringIO()

        def wait(self, timeout):
            calls.append("wait")
            if calls == ["wait"]:
                raise subprocess.TimeoutExpired("pill", timeout)
            return 0

        def terminate(self):
            calls.append("terminate")

    pill = indicator.Indicator()
    pill._proc = Child()
    pill.close()
    assert calls == ["wait", "terminate", "wait"]
    assert pill._proc is None
    assert not pill.enabled
