"""Bounded subprocess transport for explicitly selected local media tools."""

from __future__ import annotations

from contextlib import closing
import math
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time
from typing import Callable, Iterable, Iterator

from utterleaf.transcript import TranscriptionCancelled


_BLOCK_BYTES = 64 * 1024
_QUEUE_BLOCKS = 4
_POLL_SECONDS = 0.05
_REAP_SECONDS = 5
_JOIN_SECONDS = 2
_EOF = object()


def _positive_timeout(value, field: str, *, optional: bool = False) -> float | None:
    if value is None and optional:
        return None
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not math.isfinite(value) or value <= 0):
        raise ValueError(f"{field} must be a positive number")
    return float(value)


def _event(value, field: str, *, writable: bool = False):
    if value is not None and not callable(getattr(value, "is_set", None)):
        raise TypeError(f"{field} must provide is_set()")
    if value is not None and writable and not callable(getattr(value, "set", None)):
        raise TypeError(f"{field} must provide set()")
    return value


def iter_tool_output(
    executable: Path,
    arguments: list[str],
    *,
    check_identity: Callable[[], None],
    cancel=None,
    abort: threading.Event | None = None,
    input_chunks: Iterable[bytes] | None = None,
    inactivity_timeout=120,
    wall_timeout=None,
    reject_stderr=False,
) -> Iterator[bytes]:
    """Yield bounded stdout chunks and own complete process/thread cleanup.

    Closing the iterator early abandons the operation. When supplied, ``abort``
    links sibling media processes; it is distinct from deliberate user cancel.
    """
    if not isinstance(executable, Path):
        raise TypeError("executable must be a Path")
    if type(arguments) is not list or any(type(item) is not str or "\0" in item
                                           for item in arguments):
        raise TypeError("arguments must be a list of strings")
    if not callable(check_identity):
        raise TypeError("check_identity is required")
    cancel = _event(cancel, "cancel")
    abort = _event(abort, "abort", writable=True)
    inactivity = _positive_timeout(inactivity_timeout, "inactivity_timeout")
    wall = _positive_timeout(wall_timeout, "wall_timeout", optional=True)
    if type(reject_stderr) is not bool:
        raise TypeError("reject_stderr must be bool")

    def user_cancelled() -> bool:
        return cancel is not None and cancel.is_set()

    def sibling_aborted() -> bool:
        return abort is not None and abort.is_set()

    if user_cancelled():
        raise TranscriptionCancelled("Media processing cancelled")
    if sibling_aborted():
        raise RuntimeError("Media processing stopped before completion")

    command = [str(executable), *arguments]
    environment = os.environ.copy()
    environment.pop("FFREPORT", None)
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0

    # Keep this callback adjacent to process creation. The caller owns the exact
    # executable identity policy; this helper never discovers a program.
    check_identity()
    try:
        process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE if input_chunks is not None else subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
            cwd=executable.parent,
            env=environment,
            creationflags=flags,
            bufsize=0,
        )
    except (OSError, ValueError):
        raise RuntimeError("Media process could not start") from None
    if process.stdout is None or process.stderr is None or (
            input_chunks is not None and process.stdin is None):
        try:
            process.kill()
            process.wait(timeout=_REAP_SECONDS)
        except (OSError, subprocess.TimeoutExpired):
            pass
        raise RuntimeError("Media process could not start safely")

    output: queue.Queue[bytes | object] = queue.Queue(maxsize=_QUEUE_BLOCKS)
    local_stop = threading.Event()
    stdout_done = threading.Event()
    stderr_done = threading.Event()
    writer_done = threading.Event()
    stdout_failed = threading.Event()
    stderr_failed = threading.Event()
    stderr_seen = threading.Event()
    writer_failed = threading.Event()

    def stopping() -> bool:
        return local_stop.is_set() or sibling_aborted()

    def put_output(value: bytes | object) -> None:
        while not stopping():
            try:
                output.put(value, timeout=_POLL_SECONDS)
                return
            except queue.Full:
                pass

    def read_stdout() -> None:
        try:
            while not stopping():
                block = process.stdout.read(_BLOCK_BYTES)
                if not block:
                    put_output(_EOF)
                    return
                put_output(block)
        except (OSError, ValueError):
            if not stopping():
                stdout_failed.set()
        finally:
            stdout_done.set()

    def read_stderr() -> None:
        try:
            while not stopping():
                block = process.stderr.read(_BLOCK_BYTES)
                if not block:
                    return
                stderr_seen.set()
        except (OSError, ValueError):
            if not stopping():
                stderr_failed.set()
        finally:
            stderr_done.set()

    def write_stdin() -> None:
        iterator = None
        try:
            assert process.stdin is not None
            iterator = iter(input_chunks)  # type: ignore[arg-type]
            for block in iterator:
                if stopping():
                    return
                if type(block) is not bytes or not 0 < len(block) <= _BLOCK_BYTES:
                    raise ValueError("invalid input chunk")
                offset = 0
                while offset < len(block):
                    if stopping():
                        return
                    written = process.stdin.write(block[offset:])
                    if written is None or written <= 0:
                        raise OSError("incomplete stdin write")
                    offset += written
        except BaseException:
            if not local_stop.is_set():
                writer_failed.set()
                if abort is not None:
                    abort.set()
        finally:
            closer = getattr(iterator, "close", None)
            if callable(closer):
                try:
                    closer()
                except BaseException:
                    if not local_stop.is_set():
                        writer_failed.set()
                        if abort is not None:
                            abort.set()
            try:
                assert process.stdin is not None
                process.stdin.close()
            except (OSError, ValueError):
                if not local_stop.is_set():
                    writer_failed.set()
                    if abort is not None:
                        abort.set()
            writer_done.set()

    threads = [
        threading.Thread(target=read_stdout, name="utterleaf-media-stdout", daemon=True),
        threading.Thread(target=read_stderr, name="utterleaf-media-stderr", daemon=True),
    ]
    if input_chunks is not None:
        threads.append(threading.Thread(target=write_stdin, name="utterleaf-media-stdin", daemon=True))
    else:
        writer_done.set()

    started: list[threading.Thread] = []
    complete = False
    cleanup_error = False
    failure: BaseException | None = None
    wall_deadline = time.monotonic() + wall if wall is not None else None
    inactivity_deadline = time.monotonic() + inactivity

    def check_failure() -> None:
        if user_cancelled():
            raise TranscriptionCancelled("Media processing cancelled")
        # Preserve this process's own writer failure before observing the abort
        # it propagated to siblings.
        if writer_failed.is_set():
            raise RuntimeError("Media process input could not be delivered")
        if stdout_failed.is_set() or stderr_failed.is_set():
            raise RuntimeError("Media process output could not be read")
        if reject_stderr and stderr_seen.is_set():
            raise RuntimeError("Media process returned unexpected diagnostics")
        if sibling_aborted():
            raise RuntimeError("Media processing stopped before completion")
        now = time.monotonic()
        if wall_deadline is not None and now >= wall_deadline:
            raise RuntimeError("Media processing took too long")
        if now >= inactivity_deadline:
            raise RuntimeError("Media processing made no progress for too long")

    try:
        try:
            for thread in threads:
                thread.start()
                started.append(thread)
        except Exception:
            raise RuntimeError("Media process workers could not start") from None
        saw_eof = False
        while not saw_eof:
            check_failure()
            try:
                item = output.get(timeout=_POLL_SECONDS)
            except queue.Empty:
                continue
            if item is _EOF:
                saw_eof = True
                break
            assert isinstance(item, bytes)
            yield item
            # Generator time spent in the caller is not subprocess inactivity.
            inactivity_deadline = time.monotonic() + inactivity

        while process.poll() is None or not writer_done.is_set() or not stderr_done.is_set():
            check_failure()
            try:
                process.wait(timeout=_POLL_SECONDS)
            except subprocess.TimeoutExpired:
                pass
            except OSError:
                raise RuntimeError("Media process status could not be read") from None
        check_failure()
        if process.returncode != 0:
            raise RuntimeError("Media process did not complete successfully")
        complete = True
    except GeneratorExit as exc:
        failure = exc
    except BaseException as exc:
        failure = exc
    finally:
        if not complete and abort is not None:
            abort.set()
        local_stop.set()
        if process.poll() is None:
            try:
                process.kill()
            except OSError:
                cleanup_error = True
        try:
            process.wait(timeout=_REAP_SECONDS)
        except (OSError, subprocess.TimeoutExpired):
            cleanup_error = True
        for thread in started:
            thread.join(timeout=_JOIN_SECONDS)
            if thread.is_alive():
                cleanup_error = True
        # Never close a pipe while its worker may hold the stream's read/write
        # lock. A live daemon owns that pipe until process teardown completes.
        streams = (
            (process.stdout, threads[0]),
            (process.stderr, threads[1]),
            (process.stdin, threads[2] if input_chunks is not None else None),
        )
        for stream, owner in streams:
            if stream is not None and (owner is None or not owner.is_alive()):
                try:
                    stream.close()
                except (OSError, ValueError):
                    cleanup_error = True

    if cleanup_error:
        raise RuntimeError("Media process could not be stopped safely")
    if failure is not None:
        raise failure


def collect_tool_output(
    executable: Path,
    arguments: list[str],
    *,
    check_identity: Callable[[], None],
    max_bytes: int,
    cancel=None,
    abort: threading.Event | None = None,
    input_chunks: Iterable[bytes] | None = None,
    inactivity_timeout=120,
    wall_timeout=10,
    reject_stderr=False,
) -> bytes:
    """Collect a deliberately small tool response without leaving a process."""
    if type(max_bytes) is not int or not 0 <= max_bytes:
        raise ValueError("max_bytes must be a nonnegative integer")
    result = bytearray()
    with closing(iter_tool_output(
        executable, arguments, check_identity=check_identity, cancel=cancel,
        abort=abort, input_chunks=input_chunks, inactivity_timeout=inactivity_timeout,
        wall_timeout=wall_timeout, reject_stderr=reject_stderr,
    )) as chunks:
        for block in chunks:
            if len(result) + len(block) > max_bytes:
                raise RuntimeError("Media process returned too much output")
            result.extend(block)
    return bytes(result)


__all__ = ["collect_tool_output", "iter_tool_output"]
