import io
import json
import threading

from utterleaf import review_ui


def test_review_request_is_bounded_and_preserves_unicode():
    text = "First line\nCafé 🍃"
    payload = json.dumps({"text": text, "allow_insert": True}, ensure_ascii=False) + "\n"
    assert review_ui._read_request(io.StringIO(payload)) == (text, True)
    assert review_ui._read_request(io.StringIO('{"text":"","allow_insert":true}\n')) is None
    assert review_ui._read_request(io.StringIO('{"text":"ok","allow_insert":true,"extra":1}\n')) is None


def test_launch_keeps_transcript_off_argv_and_returns_only_action(monkeypatch):
    class Pipe(io.StringIO):
        def close(self):
            pass

    written = Pipe()
    action_ready = threading.Event()
    commands = []

    class Process:
        stdin = written
        stdout = Pipe("ready\ninsert\n")
        def poll(self):
            return None
        def terminate(self):
            pass
        def wait(self, timeout=None):
            return 0

    def popen(command, **kwargs):
        commands.append((command, kwargs))
        return Process()

    monkeypatch.setattr(review_ui.subprocess, "Popen", popen)
    handle = review_ui.launch_review("private dictated words", lambda action: action_ready.set())
    assert handle is not None
    assert action_ready.wait(1)
    assert "private dictated words" not in " ".join(commands[0][0])
    assert json.loads(written.getvalue().splitlines()[0]) == {
        "text": "private dictated words", "allow_insert": True}
    assert commands[0][1]["stderr"] is review_ui.subprocess.DEVNULL


def test_review_handle_closes_only_its_live_child():
    class Pipe(io.StringIO):
        def close(self):
            pass
    stdin = Pipe()
    terminated = []
    process = type("Process", (), {
        "stdin": stdin,
        "stdout": None,
        "poll": lambda self: None,
        "terminate": lambda self: terminated.append(True),
        "wait": lambda self, timeout=None: 0,
        "kill": lambda self: None,
    })()
    review_ui.ReviewHandle(process).close()
    assert stdin.getvalue() == ""
    assert terminated == [True]


def test_reader_thread_start_failure_closes_and_reaps_child(monkeypatch):
    failures, events = [], []

    class Process:
        stdin = io.StringIO()
        stdout = io.StringIO()
        def poll(self): return None
        def terminate(self): events.append("terminate")
        def wait(self, timeout=None): events.append("wait"); return 0
        def kill(self): events.append("kill")

    class BrokenThread:
        def __init__(self, **_kwargs): pass
        def start(self): raise RuntimeError("thread unavailable")

    monkeypatch.setattr(review_ui.subprocess, "Popen", lambda *_a, **_k: Process())
    monkeypatch.setattr(review_ui.threading, "Thread", BrokenThread)
    assert review_ui.launch_review("private", lambda _a: None,
                                   lambda: failures.append(True)) is None
    assert failures == [True]
    assert events == ["terminate", "wait"]


def test_watchdog_thread_start_failure_closes_and_reaps_child(monkeypatch):
    failures, events, count = [], [], 0

    class Process:
        stdin = io.StringIO()
        stdout = io.StringIO()
        def poll(self): return None
        def terminate(self): events.append("terminate")
        def wait(self, timeout=None): events.append("wait"); return 0
        def kill(self): events.append("kill")

    class Thread:
        def __init__(self, **_kwargs):
            nonlocal count
            count += 1
            self.number = count
        def start(self):
            if self.number == 2:
                raise RuntimeError("thread unavailable")

    monkeypatch.setattr(review_ui.subprocess, "Popen", lambda *_a, **_k: Process())
    monkeypatch.setattr(review_ui.threading, "Thread", Thread)
    assert review_ui.launch_review("private", lambda _a: None,
                                   lambda: failures.append(True)) is None
    assert failures == [True]
    assert events == ["terminate", "wait"]
