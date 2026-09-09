"""Talk to a running Utterleaf process so Wayland / extra hotkeys can toggle it."""

from __future__ import annotations

import json
import os
import secrets
import socket
import tempfile
from pathlib import Path

from utterleaf.config import data_dir

HOST = "127.0.0.1"
_server_token = ""


def port_file() -> Path:
    return data_dir() / "instance.json"


def advertise(port: int) -> None:
    path = port_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
        try:
            os.chmod(temporary, 0o600)
            json.dump({"port": port, "token": _server_token}, stream)
        except Exception:
            stream.close()
            temporary.unlink(missing_ok=True)
            raise
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


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
    try:
        endpoint = json.loads(port_file().read_text(encoding="utf-8"))
        port = int(endpoint["port"])
        if not 0 < port < 65536:
            return None
        token = endpoint.get("token")
        if not isinstance(token, str) or not token:
            # Only probe legacy instances for duplicate-start protection.
            # Never downgrade recording, clipboard, or configuration commands.
            if command != "ping":
                return "restart-required"
            request = "ping\n"
        else:
            request = json.dumps({"token": token, "command": command}) + "\n"
        with socket.create_connection((HOST, port), timeout=timeout) as sock:
            sock.sendall(request.encode("utf-8"))
            return sock.makefile().readline(1024).strip()
    except (OSError, ValueError, KeyError, TypeError):
        return None


def authenticated_command(line: bytes) -> str | None:
    if not _server_token or len(line) > 1024:
        return None
    try:
        request = json.loads(line)
        token, command = request["token"], request["command"]
        if not isinstance(token, str) or not isinstance(command, str):
            return None
        if not secrets.compare_digest(token.encode("utf-8"), _server_token.encode("ascii")):
            return None
        return command
    except (ValueError, KeyError, TypeError):
        return None


def bind() -> socket.socket:
    global _server_token
    _server_token = secrets.token_hex(32)
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((HOST, 0))
    sock.listen(4)
    sock.settimeout(0.5)
    try:
        advertise(sock.getsockname()[1])
    except Exception:
        sock.close()
        raise
    return sock
