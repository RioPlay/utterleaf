import json
import socket
import threading

from utterleaf import ipc
from utterleaf.app import Utterleaf


def test_control_socket_rejects_unauthenticated_clients_and_survives_timeout(tmp_path, monkeypatch):
    monkeypatch.setattr(ipc, "data_dir", lambda: tmp_path)
    server = ipc.bind()
    app = object.__new__(Utterleaf)
    app._server = server
    app._stop = threading.Event()
    commands = []
    app._handle_ipc = lambda command: commands.append(command) or "ok"
    worker = threading.Thread(target=app._ipc_loop, daemon=True)
    worker.start()
    port = server.getsockname()[1]
    try:
        for request in (b"toggle\n", b'{"token":"wrong","command":"toggle"}\n', b"x" * 1025):
            with socket.create_connection((ipc.HOST, port), timeout=4) as client:
                client.sendall(request)
                assert client.recv(128).strip() == b"unauthorized"
        assert commands == []
        # An incomplete request must time out without killing the listener.
        with socket.create_connection((ipc.HOST, port), timeout=4) as client:
            client.sendall(b"{")
            assert client.recv(128) == b""
        assert ipc.send("toggle", timeout=4) == "ok"
        assert commands == ["toggle"]
    finally:
        app._stop.set()
        server.close()
        worker.join(3)
        ipc.clear()
    assert not worker.is_alive()


def test_legacy_endpoint_never_receives_control_commands(tmp_path, monkeypatch):
    monkeypatch.setattr(ipc, "data_dir", lambda: tmp_path)
    ipc.port_file().write_text(json.dumps({"port": 12345}))
    monkeypatch.setattr(ipc.socket, "create_connection", lambda *a, **k: (_ for _ in ()).throw(AssertionError("Downgraded authentication")))
    assert ipc.send("toggle") == "restart-required"
    assert ipc.send("copy-last") == "restart-required"


def test_endpoint_token_and_private_permissions(tmp_path, monkeypatch):
    import os
    import stat
    monkeypatch.setattr(ipc, "data_dir", lambda: tmp_path)
    server = ipc.bind()
    try:
        endpoint = json.loads(ipc.port_file().read_text())
        assert len(endpoint["token"]) == 64
        assert endpoint["port"] == server.getsockname()[1]
        if os.name != "nt":
            assert stat.S_IMODE(ipc.port_file().stat().st_mode) == 0o600
    finally:
        server.close()
        ipc.clear()
