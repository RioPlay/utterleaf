from __future__ import annotations

from contextlib import contextmanager
import logging
import socket
import sys
import threading
import time

import pytest
from websockets.sync.server import serve

from utterleaf import obs_websocket


REAL_OPEN_EXPECTED_EXECUTABLE = (
    obs_websocket.windows_peer_identity.open_expected_executable
)
EXPECTED_EXECUTABLE = "C:/Program Files/obs-studio/bin/64bit/obs64.exe"


class FakePeer:
    def __init__(
        self,
        events: list[str],
        *,
        revalidate_error: BaseException | None = None,
    ) -> None:
        self.events = events
        self.revalidate_error = revalidate_error
        self.revalidate_calls: list[tuple[object, float]] = []
        self.retain_calls: list[tuple[object, float]] = []
        self.retain_error: BaseException | None = None
        self.process_lease = FakeRetainedProcess()
        self.close_calls = 0

    def revalidate(self, *, cancelled, deadline: float) -> None:
        self.events.append("revalidate")
        self.revalidate_calls.append((cancelled, deadline))
        if self.revalidate_error is not None:
            raise self.revalidate_error

    def close(self) -> None:
        self.events.append("peer.close")
        self.close_calls += 1

    def retain_process(self, *, cancelled, deadline: float):
        self.events.append("retain_process")
        self.retain_calls.append((cancelled, deadline))
        if self.retain_error is not None:
            raise self.retain_error
        return self.process_lease


class FakeRetainedProcess:
    def __init__(self) -> None:
        self.close_calls = 0

    def close(self) -> None:
        self.close_calls += 1


class FakeExpected:
    def __init__(
        self,
        events: list[str],
        *,
        verify_error: BaseException | None = None,
    ) -> None:
        self.events = events
        self.verify_error = verify_error
        self.peer = FakePeer(events)
        self.verify_calls: list[tuple[object, object, float]] = []
        self.close_calls = 0

    def verify(self, sock, *, cancelled, deadline: float) -> FakePeer:
        self.events.append("verify")
        self.verify_calls.append((sock, cancelled, deadline))
        if self.verify_error is not None:
            raise self.verify_error
        return self.peer

    def close(self) -> None:
        self.events.append("expected.close")
        self.close_calls += 1


class FakeIdentityFactory:
    def __init__(self) -> None:
        self.events: list[str] = []
        self.opened_paths: list[str] = []
        self.expected: list[FakeExpected] = []
        self.verify_error: BaseException | None = None

    def open(self, path: str) -> FakeExpected:
        self.events.append("open")
        self.opened_paths.append(path)
        expected = FakeExpected(self.events, verify_error=self.verify_error)
        self.expected.append(expected)
        return expected


@pytest.fixture(autouse=True)
def fake_peer_identity(monkeypatch) -> FakeIdentityFactory:
    factory = FakeIdentityFactory()
    monkeypatch.setattr(
        obs_websocket.windows_peer_identity,
        "open_expected_executable",
        factory.open,
    )
    return factory


def connect_transport(host: str, port: int, *, cancelled):
    return obs_websocket.connect(
        host,
        port,
        expected_executable=EXPECTED_EXECUTABLE,
        cancelled=cancelled,
    )


def make_transport(connection, cancelled):
    events: list[str] = []
    expected = FakeExpected(events)
    return obs_websocket.ObsWebSocketTransport(
        connection,
        cancelled,
        expected=expected,
        peer=expected.peer,
    )


class FakeConnection:
    def __init__(self) -> None:
        self.subprotocol = obs_websocket.OBS_SUBPROTOCOL
        self.sent: list[str] = []
        self.responses: list[object] = []
        self.close_calls = 0
        self.close_socket_calls = 0

    def send(self, text: str) -> None:
        self.sent.append(text)

    def recv(self, *, timeout: float) -> object:
        if self.responses:
            return self.responses.pop(0)
        raise TimeoutError

    def close(self) -> None:
        self.close_calls += 1

    def close_socket(self) -> None:
        self.close_socket_calls += 1


class BlockingConnection(FakeConnection):
    def __init__(self) -> None:
        super().__init__()
        self.released = threading.Event()

    def send(self, text: str) -> None:
        self.released.wait(2)
        raise OSError("peer supplied secret")

    def close(self) -> None:
        self.close_calls += 1
        self.released.wait(2)

    def close_socket(self) -> None:
        super().close_socket()
        self.released.set()


@contextmanager
def loopback_server(handler):
    server = serve(
        handler,
        "127.0.0.1",
        0,
        compression=None,
        subprotocols=[obs_websocket.OBS_SUBPROTOCOL],
        ping_interval=None,
        close_timeout=0.1,
        server_header=None,
    )
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    try:
        yield server.socket.getsockname()[1]
    finally:
        server.shutdown()
        thread.join(2)
        assert not thread.is_alive()


@pytest.mark.parametrize(
    "host",
    ["localhost", "0.0.0.0", "127.0.0.2", "127.0.0.1 ", "::1%1", "ws://127.0.0.1", 1],
)
def test_connect_rejects_any_endpoint_except_exact_numeric_loopback(
    monkeypatch, host
) -> None:
    called = False

    def unexpected_socket(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError

    monkeypatch.setattr(obs_websocket.socket, "socket", unexpected_socket)
    with pytest.raises(obs_websocket.ObsWebSocketError, match="endpoint is invalid"):
        connect_transport(host, 4455, cancelled=lambda: False)
    assert not called


@pytest.mark.parametrize("port", [True, 1.0, "4455", 0, 65536])
def test_connect_rejects_invalid_ports_before_io(monkeypatch, port) -> None:
    monkeypatch.setattr(
        obs_websocket.socket,
        "socket",
        lambda *args, **kwargs: pytest.fail("socket creation wasn't expected"),
    )
    with pytest.raises(obs_websocket.ObsWebSocketError, match="endpoint is invalid"):
        connect_transport("127.0.0.1", port, cancelled=lambda: False)


def test_connect_uses_identity_before_http_and_bounded_library_options(
    monkeypatch, fake_peer_identity: FakeIdentityFactory
) -> None:
    raw_socket = object()
    connection = FakeConnection()
    captured = {}

    def connect_socket(*args):
        fake_peer_identity.events.append("tcp")
        return raw_socket

    monkeypatch.setattr(obs_websocket, "_connect_socket", connect_socket)

    def fake_connect(uri, **kwargs):
        fake_peer_identity.events.append("http")
        captured["uri"] = uri
        captured.update(kwargs)
        return connection

    monkeypatch.setattr(obs_websocket, "_websocket_connect", fake_connect)
    transport = connect_transport("::1", 4455, cancelled=lambda: False)
    assert captured["uri"] == "ws://[::1]:4455/"
    assert captured["sock"] is raw_socket
    assert captured["proxy"] is None
    assert captured["subprotocols"] == [obs_websocket.OBS_SUBPROTOCOL]
    assert captured["compression"] is None
    assert captured["max_size"] == 65536
    assert captured["max_queue"] == 4
    assert 0 < captured["open_timeout"] <= obs_websocket.CONNECT_TIMEOUT_SECONDS
    assert captured["close_timeout"] == obs_websocket.CLOSE_TIMEOUT_SECONDS
    assert captured["ping_interval"] is None
    assert captured["user_agent_header"] is None
    logger = captured["logger"]
    assert isinstance(logger, logging.Logger)
    assert logger.disabled and not logger.propagate
    assert fake_peer_identity.opened_paths == [EXPECTED_EXECUTABLE]
    assert fake_peer_identity.events[:4] == ["open", "tcp", "verify", "http"]
    expected = fake_peer_identity.expected[0]
    assert expected.verify_calls[0][0] is raw_socket
    transport.close()
    assert fake_peer_identity.events[-2:] == ["peer.close", "expected.close"]
    assert expected.peer.close_calls == expected.close_calls == 1


def test_expected_executable_has_no_public_default() -> None:
    with pytest.raises(TypeError, match="expected_executable"):
        obs_websocket.connect(  # type: ignore[call-arg]
            "127.0.0.1", 4455, cancelled=lambda: False
        )


def test_cancelled_connect_performs_no_io(
    monkeypatch, fake_peer_identity: FakeIdentityFactory
) -> None:
    monkeypatch.setattr(
        obs_websocket.socket,
        "socket",
        lambda *args, **kwargs: pytest.fail("socket creation wasn't expected"),
    )
    with pytest.raises(obs_websocket.ObsWebSocketCancelled):
        connect_transport("127.0.0.1", 4455, cancelled=lambda: True)
    assert fake_peer_identity.opened_paths == []


def test_socket_failure_does_not_expose_system_error(
    monkeypatch, fake_peer_identity: FakeIdentityFactory
) -> None:
    def fail_socket(*args, **kwargs):
        raise OSError("peer path and secret")

    monkeypatch.setattr(obs_websocket.socket, "socket", fail_socket)
    with pytest.raises(obs_websocket.ObsWebSocketError) as caught:
        connect_transport("127.0.0.1", 4455, cancelled=lambda: False)
    assert str(caught.value) == "OBS control connection failed"
    assert caught.value.__cause__ is None
    assert fake_peer_identity.expected[0].close_calls == 1


def test_library_connect_failure_is_generic_and_is_not_retried(
    monkeypatch, fake_peer_identity: FakeIdentityFactory
) -> None:
    class RawSocket:
        def shutdown(self, how):
            pass

        def close(self):
            pass

    calls = 0
    monkeypatch.setattr(obs_websocket, "_connect_socket", lambda *args: RawSocket())

    def fail_connect(*args, **kwargs):
        nonlocal calls
        calls += 1
        raise OSError("127.0.0.1 private credential")

    monkeypatch.setattr(obs_websocket, "_websocket_connect", fail_connect)
    with pytest.raises(obs_websocket.ObsWebSocketError) as caught:
        connect_transport("127.0.0.1", 4455, cancelled=lambda: False)
    assert str(caught.value) == "OBS control transport failed"
    assert caught.value.__cause__ is None
    assert calls == 1
    expected = fake_peer_identity.expected[0]
    assert expected.peer.close_calls == expected.close_calls == 1


def test_initial_peer_failure_prevents_http_and_closes_handles(
    monkeypatch, fake_peer_identity: FakeIdentityFactory
) -> None:
    class RawSocket:
        def __init__(self) -> None:
            self.shutdown_calls = 0
            self.close_calls = 0

        def shutdown(self, how) -> None:
            self.shutdown_calls += 1

        def close(self) -> None:
            self.close_calls += 1

    raw_socket = RawSocket()
    fake_peer_identity.verify_error = RuntimeError("private process detail")
    monkeypatch.setattr(obs_websocket, "_connect_socket", lambda *args: raw_socket)
    monkeypatch.setattr(
        obs_websocket,
        "_websocket_connect",
        lambda *args, **kwargs: pytest.fail("HTTP must follow peer verification"),
    )

    with pytest.raises(obs_websocket.ObsWebSocketError) as caught:
        connect_transport("127.0.0.1", 4455, cancelled=lambda: False)

    assert str(caught.value) == "OBS peer identity could not be verified"
    assert caught.value.__cause__ is None
    assert raw_socket.shutdown_calls == raw_socket.close_calls == 1
    expected = fake_peer_identity.expected[0]
    assert expected.close_calls == 1
    assert expected.peer.close_calls == 0


@pytest.mark.skipif(sys.platform != "win32", reason="Windows peer identity integration")
def test_wrong_existing_executable_is_rejected_before_any_http(
    monkeypatch,
) -> None:
    expected_path = sys.executable
    actual_path = getattr(sys, "_base_executable", sys.executable)
    if expected_path.casefold() == actual_path.casefold():
        pytest.skip("venv executable is the current process image")
    monkeypatch.setattr(
        obs_websocket.windows_peer_identity,
        "open_expected_executable",
        REAL_OPEN_EXPECTED_EXECUTABLE,
    )
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    received: list[bytes] = []
    finished = threading.Event()

    def raw_peer() -> None:
        connection = None
        try:
            connection, _ = listener.accept()
            connection.settimeout(2)
            received.append(connection.recv(1))
        finally:
            if connection is not None:
                connection.close()
            finished.set()

    thread = threading.Thread(target=raw_peer, name="obs-identity-raw-peer")
    thread.start()
    try:
        port = listener.getsockname()[1]
        with pytest.raises(obs_websocket.ObsWebSocketError) as caught:
            obs_websocket.connect(
                "127.0.0.1",
                port,
                expected_executable=expected_path,
                cancelled=lambda: False,
            )
        assert str(caught.value) == "OBS peer identity could not be verified"
        assert caught.value.__cause__ is None
        assert finished.wait(2)
        assert received == [b""]
    finally:
        listener.close()
        thread.join(2)
        assert not thread.is_alive()


def test_missing_obs_subprotocol_closes_connection(monkeypatch) -> None:
    connection = FakeConnection()
    connection.subprotocol = None
    monkeypatch.setattr(obs_websocket, "_connect_socket", lambda *args: object())
    monkeypatch.setattr(
        obs_websocket, "_websocket_connect", lambda *args, **kwargs: connection
    )
    with pytest.raises(obs_websocket.ObsWebSocketError, match="handshake failed"):
        connect_transport("127.0.0.1", 4455, cancelled=lambda: False)
    assert connection.close_calls == 1
    assert connection.close_socket_calls >= 1


def test_send_checks_exact_text_and_utf8_byte_bound_before_io() -> None:
    connection = FakeConnection()
    transport = make_transport(connection, lambda: False)
    transport.send("x" * obs_websocket.MAX_MESSAGE_BYTES)
    assert connection.sent == ["x" * obs_websocket.MAX_MESSAGE_BYTES]
    for invalid in (b"text", "\N{GRINNING FACE}" * 16385, "\ud800"):
        with pytest.raises(obs_websocket.ObsWebSocketError, match="message is invalid"):
            transport.send(invalid)  # type: ignore[arg-type]
    assert len(connection.sent) == 1


def test_transport_revalidates_identity_before_each_normal_io() -> None:
    events: list[str] = []
    expected = FakeExpected(events)

    class OrderedConnection(FakeConnection):
        def send(self, text: str) -> None:
            events.append("send")
            super().send(text)

        def recv(self, *, timeout: float) -> object:
            events.append("receive")
            return super().recv(timeout=timeout)

    connection = OrderedConnection()
    connection.responses.append("response")
    transport = obs_websocket.ObsWebSocketTransport(
        connection,
        lambda: False,
        expected=expected,
        peer=expected.peer,
    )

    transport.send("request")
    assert transport.receive(0.1) == "response"

    assert events[:4] == ["revalidate", "send", "revalidate", "receive"]
    transport.close()
    assert events[-2:] == ["peer.close", "expected.close"]


def test_failed_recheck_sends_no_proof_and_closes_both_identity_handles() -> None:
    events: list[str] = []
    expected = FakeExpected(events)
    expected.peer.revalidate_error = RuntimeError("private process detail")
    connection = FakeConnection()
    transport = obs_websocket.ObsWebSocketTransport(
        connection,
        lambda: False,
        expected=expected,
        peer=expected.peer,
    )

    with pytest.raises(obs_websocket.ObsWebSocketError) as caught:
        transport.send("authentication proof")

    assert str(caught.value) == "OBS peer identity could not be verified"
    assert caught.value.__cause__ is None
    assert connection.sent == []
    assert connection.close_socket_calls == 1
    assert events == ["revalidate", "peer.close", "expected.close"]
    assert expected.peer.close_calls == expected.close_calls == 1


def test_retain_process_returns_independent_caller_owned_lease(
    monkeypatch,
) -> None:
    events: list[str] = []
    expected = FakeExpected(events)
    cancelled = lambda: False
    transport = obs_websocket.ObsWebSocketTransport(
        FakeConnection(),
        cancelled,
        expected=expected,
        peer=expected.peer,
    )
    monkeypatch.setattr(obs_websocket.time, "monotonic", lambda: 40.0)

    lease = transport.retain_peer_process()

    assert lease is expected.peer.process_lease
    assert expected.peer.retain_calls == [(cancelled, 40.5)]
    transport.close()
    assert expected.peer.close_calls == expected.close_calls == 1
    assert lease.close_calls == 0
    lease.close()
    assert lease.close_calls == 1


def test_closed_transport_cannot_retain_process() -> None:
    events: list[str] = []
    expected = FakeExpected(events)
    transport = obs_websocket.ObsWebSocketTransport(
        FakeConnection(),
        lambda: False,
        expected=expected,
        peer=expected.peer,
    )
    transport.close()

    with pytest.raises(obs_websocket.ObsWebSocketError, match="could not be retained"):
        transport.retain_peer_process()

    assert expected.peer.retain_calls == []
    assert expected.peer.close_calls == expected.close_calls == 1


@pytest.mark.parametrize("cancelled", [False, True], ids=["failure", "cancelled"])
def test_retain_failure_aborts_transport_and_closes_identity(
    cancelled: bool,
) -> None:
    events: list[str] = []
    expected = FakeExpected(events)
    error_type = (
        obs_websocket.windows_peer_identity.PeerIdentityCancelled
        if cancelled
        else obs_websocket.windows_peer_identity.PeerIdentityError
    )
    expected.peer.retain_error = error_type("private process detail")
    connection = FakeConnection()
    transport = obs_websocket.ObsWebSocketTransport(
        connection,
        lambda: cancelled,
        expected=expected,
        peer=expected.peer,
    )

    expected_error = (
        obs_websocket.ObsWebSocketCancelled
        if cancelled
        else obs_websocket.ObsWebSocketError
    )
    with pytest.raises(expected_error) as raised:
        transport.retain_peer_process()

    assert "private process detail" not in str(raised.value)
    assert raised.value.__cause__ is None
    assert connection.close_socket_calls == 1
    assert expected.peer.close_calls == expected.close_calls == 1


def test_close_waits_for_retain_handoff_without_closing_returned_lease() -> None:
    events: list[str] = []
    expected = FakeExpected(events)
    entered = threading.Event()
    release = threading.Event()

    def retain_process(*, cancelled, deadline: float):
        entered.set()
        assert release.wait(2)
        return expected.peer.process_lease

    expected.peer.retain_process = retain_process  # type: ignore[method-assign]
    transport = obs_websocket.ObsWebSocketTransport(
        FakeConnection(),
        lambda: False,
        expected=expected,
        peer=expected.peer,
    )
    retained: list[FakeRetainedProcess] = []
    retain_done = threading.Event()
    close_done = threading.Event()

    def retain() -> None:
        retained.append(transport.retain_peer_process())
        retain_done.set()

    retain_thread = threading.Thread(target=retain, name="obs-retain-test")
    def close_transport() -> None:
        transport.close()
        close_done.set()

    close_thread = threading.Thread(
        target=close_transport,
        name="obs-retain-close-test",
    )
    retain_thread.start()
    assert entered.wait(1)
    close_thread.start()
    assert not close_done.wait(0.05)
    release.set()
    assert retain_done.wait(1)
    assert close_done.wait(1)
    retain_thread.join(1)
    close_thread.join(1)

    assert not retain_thread.is_alive()
    assert not close_thread.is_alive()
    assert retained == [expected.peer.process_lease]
    assert retained[0].close_calls == 0
    assert expected.peer.close_calls == expected.close_calls == 1


def test_receive_timeout_preserves_connection() -> None:
    connection = FakeConnection()
    transport = make_transport(connection, lambda: False)
    with pytest.raises(obs_websocket.ObsWebSocketTimeout):
        transport.receive(0.02)
    connection.responses.append("ready")
    assert transport.receive(0.1) == "ready"
    assert connection.close_socket_calls == 0


@pytest.mark.parametrize("timeout", [True, "1", 0, -1, float("nan"), float("inf")])
def test_receive_rejects_invalid_timeouts(timeout) -> None:
    transport = make_transport(FakeConnection(), lambda: False)
    with pytest.raises(obs_websocket.ObsWebSocketError, match="timeout is invalid"):
        transport.receive(timeout)  # type: ignore[arg-type]


def test_receive_cancellation_is_polled_and_closes_connection() -> None:
    connection = FakeConnection()
    events: list[str] = []
    expected = FakeExpected(events)
    checks = 0

    def cancelled() -> bool:
        nonlocal checks
        checks += 1
        return checks > 1

    transport = obs_websocket.ObsWebSocketTransport(
        connection,
        cancelled,
        expected=expected,
        peer=expected.peer,
    )
    with pytest.raises(obs_websocket.ObsWebSocketCancelled):
        transport.receive(1)
    assert connection.close_socket_calls == 1


def test_receive_cancellation_failure_is_generic_and_closes_connection() -> None:
    connection = FakeConnection()

    def failed_check() -> bool:
        raise RuntimeError("private callback data")

    transport = make_transport(connection, failed_check)
    with pytest.raises(obs_websocket.ObsWebSocketError) as caught:
        transport.receive(1)
    assert str(caught.value) == "OBS control transport failed"
    assert caught.value.__cause__ is None
    assert connection.close_socket_calls == 1


@pytest.mark.parametrize(
    "message", [b"binary", "x" * 65537], ids=["binary", "oversized"]
)
def test_receive_rejects_non_text_or_oversized_message_and_closes(message) -> None:
    connection = FakeConnection()
    connection.responses.append(message)
    transport = make_transport(connection, lambda: False)
    with pytest.raises(obs_websocket.ObsWebSocketError, match="message is invalid"):
        transport.receive(0.1)
    assert connection.close_socket_calls == 1
    with pytest.raises(obs_websocket.ObsWebSocketError, match="is closed"):
        transport.receive(0.1)


def test_blocked_send_is_cancelled_by_owned_socket_close() -> None:
    connection = BlockingConnection()
    checks = 0

    def cancelled() -> bool:
        nonlocal checks
        checks += 1
        return checks > 1

    transport = make_transport(connection, cancelled)
    with pytest.raises(obs_websocket.ObsWebSocketCancelled) as caught:
        transport.send("request")
    assert caught.value.__cause__ is None
    assert connection.close_socket_calls == 1
    assert not any(t.name == "utterleaf-obs-io-watchdog" for t in threading.enumerate())


def test_blocked_send_times_out_without_orphaning_a_worker(monkeypatch) -> None:
    connection = BlockingConnection()
    events: list[str] = []
    expected = FakeExpected(events)
    transport = obs_websocket.ObsWebSocketTransport(
        connection,
        lambda: False,
        expected=expected,
        peer=expected.peer,
    )
    monkeypatch.setattr(obs_websocket, "SEND_TIMEOUT_SECONDS", 0.02)
    with pytest.raises(obs_websocket.ObsWebSocketTimeout):
        transport.send("request")
    assert connection.close_socket_calls == 1
    assert expected.peer.close_calls == expected.close_calls == 1
    assert events[-2:] == ["peer.close", "expected.close"]
    assert expected.peer.close_calls == expected.close_calls == 1
    assert events[-2:] == ["peer.close", "expected.close"]
    assert not any(t.name == "utterleaf-obs-io-watchdog" for t in threading.enumerate())


def test_watchdog_start_failure_closes_connection(monkeypatch) -> None:
    connection = FakeConnection()
    transport = make_transport(connection, lambda: False)
    monkeypatch.setattr(
        obs_websocket.threading.Thread,
        "start",
        lambda self: (_ for _ in ()).throw(RuntimeError("thread data")),
    )
    with pytest.raises(obs_websocket.ObsWebSocketError) as caught:
        transport.send("request")
    assert str(caught.value) == "OBS control transport failed"
    assert caught.value.__cause__ is None
    assert connection.close_socket_calls == 1


def test_base_exception_from_send_propagates_after_connection_closes() -> None:
    connection = FakeConnection()

    def interrupt(text) -> None:
        raise KeyboardInterrupt

    connection.send = interrupt  # type: ignore[method-assign]
    transport = make_transport(connection, lambda: False)
    with pytest.raises(KeyboardInterrupt):
        transport.send("request")
    assert connection.close_socket_calls == 1


def test_blocked_handshake_is_cancelled_without_orphaning_worker(
    monkeypatch, fake_peer_identity: FakeIdentityFactory
) -> None:
    class RawSocket:
        def __init__(self) -> None:
            self.released = threading.Event()

        def shutdown(self, how) -> None:
            self.released.set()

        def close(self) -> None:
            self.released.set()

    raw_socket = RawSocket()
    checks = 0

    def cancelled() -> bool:
        nonlocal checks
        checks += 1
        return checks > 2

    def blocked_connect(*args, **kwargs):
        raw_socket.released.wait(2)
        raise OSError("hidden handshake data")

    monkeypatch.setattr(obs_websocket, "_connect_socket", lambda *args: raw_socket)
    monkeypatch.setattr(obs_websocket, "_websocket_connect", blocked_connect)
    with pytest.raises(obs_websocket.ObsWebSocketCancelled):
        connect_transport("127.0.0.1", 4455, cancelled=cancelled)
    assert raw_socket.released.is_set()
    expected = fake_peer_identity.expected[0]
    assert expected.peer.close_calls == expected.close_calls == 1
    assert not any(t.name == "utterleaf-obs-io-watchdog" for t in threading.enumerate())


def test_close_is_bounded_and_idempotent(monkeypatch) -> None:
    connection = BlockingConnection()
    transport = make_transport(connection, lambda: False)
    monkeypatch.setattr(obs_websocket, "CLOSE_TIMEOUT_SECONDS", 0.02)
    started = time.monotonic()
    transport.close()
    transport.close()
    assert time.monotonic() - started < 0.5
    assert connection.close_calls == 1
    assert connection.close_socket_calls >= 1
    assert not any(t.name == "utterleaf-obs-io-watchdog" for t in threading.enumerate())


def test_real_loopback_transport_handles_fragmented_text_without_dns(monkeypatch) -> None:
    def handler(connection) -> None:
        connection.send(["frag", "mented"])
        connection.send(connection.recv())

    with loopback_server(handler) as port:
        monkeypatch.setattr(
            socket,
            "getaddrinfo",
            lambda *args, **kwargs: pytest.fail("DNS resolution wasn't expected"),
        )
        with connect_transport(
            "127.0.0.1", port, cancelled=lambda: False
        ) as transport:
            assert transport.receive(1) == "fragmented"
            transport.send("request")
            assert transport.receive(1) == "request"


def test_real_loopback_transport_rejects_binary_frame() -> None:
    with loopback_server(lambda connection: connection.send(b"binary")) as port:
        with connect_transport(
            "127.0.0.1", port, cancelled=lambda: False
        ) as transport:
            with pytest.raises(obs_websocket.ObsWebSocketError, match="message is invalid"):
                transport.receive(1)


def test_real_loopback_transport_rejects_oversized_frame() -> None:
    oversized = "x" * (obs_websocket.MAX_MESSAGE_BYTES + 1)
    with loopback_server(lambda connection: connection.send(oversized)) as port:
        with connect_transport(
            "127.0.0.1", port, cancelled=lambda: False
        ) as transport:
            with pytest.raises(obs_websocket.ObsWebSocketError) as caught:
                transport.receive(1)
            assert str(caught.value) == "OBS control transport failed"
            assert caught.value.__cause__ is None


def test_real_loopback_backpressure_timeout_joins_client_reader(monkeypatch) -> None:
    release_server = threading.Event()
    server = serve(
        lambda connection: release_server.wait(3),
        "127.0.0.1",
        0,
        subprotocols=[obs_websocket.OBS_SUBPROTOCOL],
        compression=None,
        ping_interval=None,
        close_timeout=0.1,
        max_queue=1,
        server_header=None,
    )
    server_thread = threading.Thread(target=server.serve_forever)
    server_thread.start()
    transport = None
    try:
        port = server.socket.getsockname()[1]
        transport = connect_transport(
            "127.0.0.1", port, cancelled=lambda: False
        )
        transport._connection.socket.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 1024)
        monkeypatch.setattr(obs_websocket, "SEND_TIMEOUT_SECONDS", 0.05)
        payload = "x" * obs_websocket.MAX_MESSAGE_BYTES
        for _ in range(512):
            try:
                transport.send(payload)
            except obs_websocket.ObsWebSocketTimeout:
                break
        else:
            pytest.fail("loopback backpressure didn't reach the bounded send timeout")
        assert not transport._connection.recv_events_thread.is_alive()
        assert not any(
            thread.name == "utterleaf-obs-io-watchdog"
            for thread in threading.enumerate()
        )
    finally:
        if transport is not None:
            transport.close()
        release_server.set()
        server.shutdown()
        server_thread.join(2)
        assert not server_thread.is_alive()
