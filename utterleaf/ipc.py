"""Talk to a running Utterleaf process so Wayland / extra hotkeys can toggle it."""

from __future__ import annotations

import json
import socket
from pathlib import Path

from utterleaf.config import data_dir

HOST = "127.0.0.1"


def port_file() -> Path:
    return data_dir() / "instance.json"


def advertise(port: int) -> None:
    port_file().write_text(json.dumps({"port": port}), encoding="utf-8")


def clear() -> None:
    path = port_file()
    if path.exists():
        path.unlink()


def running_port() -> int | None:
    path = port_file()
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return int(data["port"])
    except (OSError, KeyError, ValueError, json.JSONDecodeError):
        return None


def send(command: str, timeout: float = 1.5) -> str | None:
    port = running_port()
    if port is None:
        return None
    try:
        with socket.create_connection((HOST, port), timeout=timeout) as sock:
            sock.sendall((command.strip() + "\n").encode("utf-8"))
            return sock.makefile().readline().strip()
    except OSError:
        return None


def bind() -> socket.socket:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((HOST, 0))
    sock.listen(4)
    sock.settimeout(0.5)
    advertise(sock.getsockname()[1])
    return sock
