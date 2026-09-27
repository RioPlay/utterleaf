"""Authenticated transient loopback and exact-frame checks; no running user app."""

from contextlib import contextmanager
import json
import socket
import threading

import pytest

from utterleaf import app as app_module, ipc
from utterleaf.app import Utterleaf
from utterleaf.app_status import snapshot_message
from utterleaf.config import Config
from utterleaf.model_presentation import model_token


@contextmanager
def reply_server(tmp_path, monkeypatch, payload):
    """Return one controlled wire frame from an owned loopback connection."""
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind((ipc.HOST, 0))
    server.listen(1)
    server.settimeout(2)
    token = "synthetic-snapshot-test-token"
    endpoint = tmp_path / "snapshot-endpoint.json"
    endpoint.write_text(json.dumps({"port": server.getsockname()[1], "token": token}), encoding="utf-8")
    monkeypatch.setattr(ipc, "port_file", lambda: endpoint)
    requests, errors = [], []

    def serve():
        try:
            connection, _ = server.accept()
            with connection:
                connection.settimeout(2)
                with connection.makefile("rb") as reader:
                    request = json.loads(reader.readline(1025))
                requests.append(request)
                assert request == {"token": token, "command": "status-detail"}
                connection.sendall(payload)
        except Exception as exc:
            errors.append(exc)

    worker = threading.Thread(target=serve, daemon=True)
    worker.start()
    try:
        yield requests
    finally:
        server.close()
        worker.join(3)
        assert not worker.is_alive()
        assert errors == []


@pytest.mark.parametrize("payload", [
    b"status-v2:ready:tiny\r\n", b"status-v2:ready:tiny\r",
])
def test_exact_transport_does_not_normalize_carriage_returns_to_valid_frames(tmp_path, monkeypatch, payload):
    with reply_server(tmp_path, monkeypatch, payload) as requests:
        reply = ipc.send("status-detail", timeout=2, exact_reply=True)
    assert len(requests) == 1
    assert snapshot_message(reply) is None


@pytest.mark.parametrize("payload, expected", [
    (b"status-v2:ready:tiny.en\n", "status-v2:ready:tiny.en"),
    (b"status-v2:ready:custom\n", "status-v2:ready:custom"),
    (b"status-v2:listening:unconfirmed\n", "status-v2:listening:unconfirmed"),
    (b"unknown\n", "unknown"),
    (b"unknown\r\n", "unknown\r"),
    (b"unknown\r", ""),
    (b"unknown\rjunk\n", "unknown\rjunk"),
    (b" unknown\n", " unknown"),
    (b"unknown \n", "unknown "),
    (b" status-v2:ready:tiny\n", " status-v2:ready:tiny"),
    (b"status-v2:ready:tiny \n", "status-v2:ready:tiny "),
    (b"status-v2:ready:tiny\t\n", "status-v2:ready:tiny\t"),
    (b"status-v2:ready:tiny\x00\n", "status-v2:ready:tiny\x00"),
    (b"status-v2:ready:\xff\n", None),
    ("status-v2:ready:tіny\n".encode("utf-8"), "status-v2:ready:tіny"),
    (b"status-v2:ready:private-sentinel\n", "status-v2:ready:private-sentinel"),
    (b"status-v2:ready:tiny:private-sentinel\n", "status-v2:ready:tiny:private-sentinel"),
    (b"status-v2:ready:tiny", ""),
    (b"", ""),
    pytest.param(b"status-v2:ready:tiny" + b" " * 1024 + b"\n", "", id="oversized-frame"),
])
def test_exact_transport_preserves_payload_or_rejects_truncated_frames(tmp_path, monkeypatch, payload, expected):
    with reply_server(tmp_path, monkeypatch, payload) as requests:
        reply = ipc.send("status-detail", timeout=2, exact_reply=True)
    assert requests and reply == expected
    if payload in (b"status-v2:ready:tiny.en\n", b"status-v2:ready:custom\n", b"status-v2:listening:unconfirmed\n"):
        assert snapshot_message(reply) is not None
    else:
        assert snapshot_message(reply) is None


@pytest.mark.parametrize("payload", [b" status-v2:ready:tiny \n", b"status-v2:ready:tiny\r\n", b"status-v2:ready:tiny"])
def test_default_transport_keeps_legacy_whitespace_and_eof_behavior(tmp_path, monkeypatch, payload):
    with reply_server(tmp_path, monkeypatch, payload):
        assert ipc.send("status-detail", timeout=2) == "status-v2:ready:tiny"


@pytest.fixture
def authenticated_app(tmp_path, monkeypatch):
    monkeypatch.setattr(ipc, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(ipc, "_server_token", "")
    server = ipc.bind()
    app = object.__new__(Utterleaf)
    app._server = server
    app._stop = threading.Event()
    app.cfg = Config(model="tiny.en", language="en", microphone="private-sentinel microphone")
    app._model_generation = 1
    app._model_phase = "ready"
    app._reported_status = "status-v1:listening"
    app.last_text = "private-sentinel transcript"
    app.last_app = "private-sentinel window title"
    sampled = []
    monkeypatch.setattr(app_module, "loaded_model_token",
                        lambda cfg: sampled.append(cfg) or model_token(cfg.model))
    def forbidden(*_args, **_kwargs):
        pytest.fail("Read-only status crossed a device/model/configuration boundary")
    monkeypatch.setattr(app_module, "load_model", forbidden)
    monkeypatch.setattr(app_module, "Recorder", forbidden)
    monkeypatch.setattr(app_module, "pick", forbidden)
    monkeypatch.setattr("utterleaf.config.save", forbidden)
    worker = threading.Thread(target=app._ipc_loop, daemon=True)
    worker.start()
    try:
        yield app, server.getsockname()[1], sampled
    finally:
        app._stop.set()
        server.close()
        worker.join(3)
        ipc.clear()
        assert not worker.is_alive()
        assert not ipc.port_file().exists()


def test_status_detail_requires_authentication_before_sampling_runtime(authenticated_app):
    _, port, sampled = authenticated_app
    for request in (b"status-detail\n", b'{"command":"status-detail"}\n',
                    b'{"token":"wrong","command":"status-detail"}\n'):
        with socket.create_connection((ipc.HOST, port), timeout=2) as client:
            client.sendall(request)
            with client.makefile("rb") as reader:
                assert reader.readline(1024) == b"unauthorized\n"
    assert sampled == []
    assert ipc.send("status-detail", exact_reply=True) == "status-v2:listening:tiny.en"
    assert len(sampled) == 1


@pytest.mark.parametrize("name, expected", [
    ("tiny.en", "tiny.en"), ("distil-small.en", "distil-small.en"),
    ("C:/private-sentinel/model", "custom"), ("org/private-sentinel", "custom"),
])
def test_authenticated_snapshot_uses_only_public_tokens_and_legacy_status_is_unchanged(authenticated_app, name, expected):
    app, _, sampled = authenticated_app
    app.cfg.model = name
    reply = ipc.send("status-detail", exact_reply=True)
    assert reply == f"status-v2:listening:{expected}"
    assert "private-sentinel" not in reply
    assert snapshot_message(reply) is not None
    assert len(sampled) == 1 and sampled[0] is not app.cfg
    assert ipc.send("status") == "status-v1:listening"
    assert len(sampled) == 1
    assert app._reported_status == "status-v1:listening"
    assert app.cfg.model == name


@pytest.mark.parametrize("token", [None, "", 123])
def test_legacy_endpoint_never_receives_new_status_detail_command(tmp_path, monkeypatch, token):
    endpoint = tmp_path / "legacy-endpoint.json"
    value = {"port": 12345}
    if token is not None:
        value["token"] = token
    endpoint.write_text(json.dumps(value), encoding="utf-8")
    monkeypatch.setattr(ipc, "port_file", lambda: endpoint)
    def forbidden(*_args, **_kwargs):
        pytest.fail("New status command attempted an unauthenticated connection")
    monkeypatch.setattr(ipc.socket, "create_connection", forbidden)
    assert ipc.send("status-detail", exact_reply=True) == "restart-required"
    assert ipc.send("status-detail") == "restart-required"
    assert ipc.send("status") == "restart-required"
