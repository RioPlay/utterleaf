"""One Settings window per config directory, with local activation requests."""

from __future__ import annotations

import errno
import json
import secrets
import socket
import sys
import threading
import time

from utterleaf.config import data_dir


def activate() -> bool:
    try:
        endpoint = json.loads((data_dir() / "settings-instance.json").read_text(encoding="utf-8"))
        with socket.create_connection(("127.0.0.1", int(endpoint["port"])), timeout=0.3) as client:
            client.sendall((endpoint["token"] + "\n").encode("ascii"))
            return client.recv(16) == b"ok\n"
    except (OSError, ValueError, KeyError, TypeError):
        return False


class SettingsInstance:
    """OS-owned lock survives races and is automatically released after a crash.

    The listener only enqueues activation; callers perform Tk work on its main
    thread. Endpoint files are discovery data, never evidence of a live owner.
    """

    def __init__(self):
        self.lock = None
        self.server = None
        self.stopped = threading.Event()
        self.endpoint = data_dir() / "settings-instance.json"

    def acquire(self, on_activate) -> bool:
        data_dir().mkdir(parents=True, exist_ok=True)
        handle = (data_dir() / "settings.lock").open("a+b")
        handle.seek(0, 2)
        if not handle.tell():
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        try:
            if sys.platform == "win32":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            handle.close()
            if exc.errno not in (errno.EACCES, errno.EAGAIN):
                raise
            # The winner may still be publishing its endpoint. Never create
            # another window just because activation is temporarily unavailable.
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                if activate():
                    return False
                time.sleep(0.1)
            raise RuntimeError("Settings is already opening or not responding. Try again shortly.")
        self.lock = handle
        try:
            self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server.bind(("127.0.0.1", 0))
            self.server.listen(8)
            self.server.settimeout(0.2)
            token = secrets.token_hex(32)
            self.endpoint.write_text(json.dumps({"port": self.server.getsockname()[1], "token": token}), encoding="utf-8")

            def listen():
                while not self.stopped.is_set():
                    try:
                        client, _ = self.server.accept()
                        with client:
                            client.settimeout(0.3)
                            request = bytearray()
                            while len(request) <= 65 and not request.endswith(b"\n"):
                                part = client.recv(66 - len(request))
                                if not part:
                                    break
                                request.extend(part)
                            if request == (token + "\n").encode("ascii"):
                                on_activate()
                                client.sendall(b"ok\n")
                    except OSError:
                        continue

            self.thread = threading.Thread(target=listen, daemon=True)
            self.thread.start()
        except Exception:
            self.close()
            raise
        return True

    def close(self):
        self.stopped.set()
        if self.server is not None:
            self.server.close()
        if hasattr(self, "thread"):
            self.thread.join(timeout=1)
        if self.lock is not None:
            try:
                self.endpoint.unlink(missing_ok=True)
            finally:
                # Do not unlink the lock file: another process may already
                # have opened that inode while waiting for us to exit.
                self.lock.close()
                self.lock = None
