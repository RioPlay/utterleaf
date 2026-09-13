"""Ephemeral review window for an automatically stopped desktop take.

The parent sends transcript text on stdin and receives one fixed action token on
stdout. Text is never placed in argv, a file, a log, or the action response.
"""
from __future__ import annotations

import json
import queue
import subprocess
import sys
import threading
from dataclasses import dataclass, field
from typing import Callable, TextIO

from utterleaf.host import ui_font

MAX_REVIEW_CHARACTERS = 100_000
ACTIONS = frozenset({"copy", "insert", "discard", "dismiss"})


@dataclass
class ReviewHandle:
    process: subprocess.Popen
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    _closed: threading.Event = field(default_factory=threading.Event, repr=False)
    _reaped: threading.Event = field(default_factory=threading.Event, repr=False)

    def close(self) -> None:
        """Close only the child created for this review."""
        with self._lock:
            if self._closed.is_set():
                return
            self._closed.set()
            live = self.process.poll() is None
        if live:
            try:
                # Never write to a pipe that may be blocked behind an unhealthy
                # child. Termination is scoped to this one review process.
                self.process.terminate()
            except OSError:
                pass
        self.reap()

    def reap(self) -> None:
        """Bound and collect this child exactly once, including its pipes."""
        with self._lock:
            if self._reaped.is_set():
                return
            self._reaped.set()
        try:
            self.process.wait(timeout=1.0)
        except subprocess.TimeoutExpired:
            try:
                self.process.kill()
            except OSError:
                pass
            try:
                self.process.wait(timeout=1.0)
            except (OSError, subprocess.TimeoutExpired):
                pass
        for stream in (self.process.stdin, self.process.stdout):
            try:
                if stream is not None:
                    stream.close()
            except (OSError, ValueError):
                pass


def _child_command() -> list[str]:
    if getattr(sys, "frozen", False):
        return [sys.executable, "--speech-review"]
    return [sys.executable, "-m", "utterleaf", "--speech-review"]


def launch_review(text: str, on_action: Callable[[str], None],
                  on_failure: Callable[[], None] | None = None, *,
                  allow_insert: bool = True) -> ReviewHandle | None:
    """Show bounded in-memory text and report only a validated user action."""
    if not isinstance(text, str) or not text or len(text) > MAX_REVIEW_CHARACTERS:
        return None
    kwargs: dict = {
        "stdin": subprocess.PIPE,
        "stdout": subprocess.PIPE,
        "stderr": subprocess.DEVNULL,
        "text": True,
        "encoding": "utf-8",
    }
    if sys.platform == "win32":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        process = subprocess.Popen(_child_command(), **kwargs)
    except Exception:
        return None

    handle = ReviewHandle(process)
    ready = threading.Event()
    failure_lock = threading.Lock()
    failure_reported = False

    def report_failure() -> None:
        nonlocal failure_reported
        with failure_lock:
            if failure_reported or handle._closed.is_set():
                return
            failure_reported = True
        if on_failure is not None:
            on_failure()

    def read_action() -> None:
        try:
            if handle._closed.is_set():
                return
            assert process.stdin is not None
            process.stdin.write(json.dumps(
                {"text": text, "allow_insert": bool(allow_insert)}, ensure_ascii=False) + "\n")
            process.stdin.flush()
            assert process.stdout is not None
            if process.stdout.readline(32).strip() != "ready":
                report_failure()
                return
            ready.set()
            action = process.stdout.readline(32).strip()
            if action in ACTIONS:
                on_action(action)
            elif not handle._closed.is_set():
                report_failure()
        except Exception:
            report_failure()
        finally:
            handle.reap()

    try:
        reader = threading.Thread(target=read_action, daemon=True,
                                  name="utterleaf-review-action")
        reader.start()
    except Exception:
        report_failure()
        handle.close()
        return None

    def startup_watchdog() -> None:
        if not ready.wait(5.0) and not handle._closed.is_set():
            report_failure()
            handle.close()

    try:
        watchdog = threading.Thread(target=startup_watchdog, daemon=True,
                                    name="utterleaf-review-startup")
        watchdog.start()
    except Exception:
        report_failure()
        handle.close()
        return None
    return handle


def _read_request(stream: TextIO) -> tuple[str, bool] | None:
    line = stream.readline(MAX_REVIEW_CHARACTERS * 6 + 256)
    if not line or len(line) > MAX_REVIEW_CHARACTERS * 6 + 128:
        return None
    try:
        value = json.loads(line)
    except (TypeError, ValueError):
        return None
    if not isinstance(value, dict) or set(value) != {"text", "allow_insert"}:
        return None
    text, allow_insert = value.get("text"), value.get("allow_insert")
    if (not isinstance(text, str) or not 0 < len(text) <= MAX_REVIEW_CHARACTERS
            or type(allow_insert) is not bool):
        return None
    return text, allow_insert


def run_review() -> int:
    """Hidden ``--speech-review`` child entrypoint."""
    request = _read_request(sys.stdin)
    if request is None:
        return 2
    text, allow_insert = request
    try:
        import tkinter as tk
        from tkinter import ttk
        from utterleaf import theme
    except Exception:
        return 1

    commands: queue.Queue[str] = queue.Queue()

    def control_reader() -> None:
        try:
            for line in sys.stdin:
                if line.strip() == "close":
                    commands.put("close")
                    return
        except Exception:
            pass
        commands.put("close")

    threading.Thread(target=control_reader, daemon=True, name="utterleaf-review-control").start()
    root = tk.Tk()
    theme.apply(root)
    root.title("Review automatic dictation · Utterleaf")
    root.geometry("680x480")
    root.minsize(480, 320)
    root.columnconfigure(0, weight=1)
    root.rowconfigure(2, weight=1)
    ttk.Label(root, text="Review dictation", style="Title.TLabel").grid(
        row=0, column=0, sticky="w", padx=20, pady=(18, 6)
    )
    instruction = ttk.Label(
        root,
        text=("Nothing has been inserted. Insert is available only while the original field remains unchanged; "
              "use Copy otherwise. This preview clears after two minutes; copy to keep the text."
              if allow_insert else
              "Nothing has been inserted. This field cannot be verified for safe insertion; use Copy instead. "
              "This preview clears after two minutes; copy to keep the text."),
        style="Subtitle.TLabel",
        wraplength=440,
    )
    instruction.grid(row=1, column=0, sticky="ew", padx=20, pady=(0, 10))
    root.bind("<Configure>", lambda event: instruction.configure(
        wraplength=max(300, event.width - 40)) if event.widget is root else None, add="+")
    frame = ttk.Frame(root)
    frame.grid(row=2, column=0, sticky="nsew", padx=20)
    frame.columnconfigure(0, weight=1)
    frame.rowconfigure(0, weight=1)
    preview = tk.Text(frame, wrap="word", font=(ui_font(), 11), padx=10, pady=10, undo=False)
    preview.configure(
        bg=theme.SURFACE_LOW,
        fg=theme.ON_SURFACE,
        insertbackground=theme.PRIMARY,
        selectbackground=theme.PRIMARY_CONTAINER,
        selectforeground=theme.ON_SURFACE,
        relief="flat",
    )
    preview.grid(row=0, column=0, sticky="nsew")
    scroll = ttk.Scrollbar(frame, command=preview.yview)
    scroll.grid(row=0, column=1, sticky="ns")
    preview.configure(yscrollcommand=scroll.set)
    preview.insert("1.0", text)
    preview.configure(state="disabled")
    actions = ttk.Frame(root)
    actions.grid(row=3, column=0, sticky="e", padx=20, pady=18)
    sent = False

    def choose(action: str) -> None:
        nonlocal sent
        if sent:
            return
        sent = True
        try:
            sys.stdout.write(action + "\n")
            sys.stdout.flush()
        finally:
            root.destroy()

    ttk.Button(actions, text="Discard", command=lambda: choose("discard")).pack(side="left", padx=6)
    ttk.Button(actions, text="Copy", command=lambda: choose("copy")).pack(side="left", padx=6)
    insert = ttk.Button(actions, text="Insert", style="Primary.TButton",
                        command=lambda: choose("insert"))
    insert.pack(side="left", padx=6)
    if not allow_insert:
        insert.configure(state="disabled")
    root.protocol("WM_DELETE_WINDOW", lambda: choose("dismiss"))
    root.bind("<Escape>", lambda _event: choose("dismiss"))

    try:
        sys.stdout.write("ready\n")
        sys.stdout.flush()
    except (OSError, ValueError):
        root.destroy()
        return 1

    def poll() -> None:
        try:
            if commands.get_nowait() == "close":
                root.destroy()
                return
        except queue.Empty:
            pass
        root.after(50, poll)

    root.after(50, poll)
    root.mainloop()
    return 0
