from __future__ import annotations

from contextlib import contextmanager
import threading

import pytest
from websockets.exceptions import ConnectionClosedError, ConnectionClosedOK
from websockets.frames import Close
from websockets.sync.client import connect as websocket_connect
from websockets.sync.server import serve

from utterleaf import obs_websocket


SECRET = "peer supplied private detail"


class Peer:
    def __init__(self) -> None:
        self.revalidate_calls = 0
        self.fail_on_call: int | None = None
        self.close_calls = 0

    def revalidate(self, *, cancelled, deadline) -> None:
        del cancelled, deadline
        self.revalidate_calls += 1
        if self.revalidate_calls == self.fail_on_call:
            raise obs_websocket.windows_peer_identity.PeerIdentityError(SECRET)

    def close(self) -> None:
        self.close_calls += 1


class Expected:
    def __init__(self) -> None:
        self.close_calls = 0

    def close(self) -> None:
        self.close_calls += 1


class FailingConnection:
    subprotocol = obs_websocket.OBS_SUBPROTOCOL

    def __init__(self, error: Exception) -> None:
        self.error = error
        self.close_socket_calls = 0

    def send(self, text: str) -> None:
        del text
        raise self.error

    def recv(self, *, timeout: float):
        del timeout
        raise self.error

    def close(self) -> None:
        pass

    def close_socket(self) -> None:
        self.close_socket_calls += 1


def transport_for(error: Exception, *, fail_identity_on: int | None = None):
    connection = FailingConnection(error)
    peer = Peer()
    peer.fail_on_call = fail_identity_on
    expected = Expected()
    transport = obs_websocket.ObsWebSocketTransport(
        connection, lambda: False, expected=expected, peer=peer
    )
    return transport, connection, peer, expected


def clean_close() -> ConnectionClosedOK:
    return ConnectionClosedOK(Close(1000, ""), Close(1000, ""), True)


def socket_eof() -> ConnectionClosedError:
    return ConnectionClosedError(None, None, None)


def protocol_close() -> ConnectionClosedError:
    close = Close(1002, SECRET)
    return ConnectionClosedError(close, close, True)


def fail(operation: str, transport: obs_websocket.ObsWebSocketTransport) -> None:
    if operation == "send":
        transport.send("request without credentials")
    else:
        transport.receive(0.1)


@contextmanager
def closing_loopback_server():
    server = serve(
        lambda connection: None,
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


@pytest.mark.parametrize("operation", ["send", "receive"])
@pytest.mark.parametrize("failure", [clean_close, socket_eof], ids=["clean", "eof"])
def test_live_verified_peer_connection_loss_is_narrowly_typed(
    operation: str, failure
) -> None:
    transport, connection, peer, expected = transport_for(failure())

    with pytest.raises(obs_websocket.ObsWebSocketDisconnected) as caught:
        fail(operation, transport)

    assert type(caught.value) is obs_websocket.ObsWebSocketDisconnected
    assert str(caught.value) == "OBS control disconnected"
    assert caught.value.__cause__ is None
    assert peer.revalidate_calls == 2
    assert connection.close_socket_calls == 1
    assert peer.close_calls == expected.close_calls == 1


def test_real_clean_websocket_close_is_narrowly_typed() -> None:
    with closing_loopback_server() as port:
        connection = websocket_connect(
            f"ws://127.0.0.1:{port}/",
            subprotocols=[obs_websocket.OBS_SUBPROTOCOL],
            compression=None,
            proxy=None,
            open_timeout=1,
            close_timeout=0.1,
            ping_interval=None,
            user_agent_header=None,
        )
        peer, expected = Peer(), Expected()
        transport = obs_websocket.ObsWebSocketTransport(
            connection, lambda: False, expected=expected, peer=peer
        )

        with pytest.raises(obs_websocket.ObsWebSocketDisconnected):
            transport.receive(1)

        assert peer.revalidate_calls == 2
        assert peer.close_calls == expected.close_calls == 1


@pytest.mark.parametrize("operation", ["send", "receive"])
def test_protocol_close_is_generic_and_does_not_expose_close_reason(
    operation: str,
) -> None:
    transport, connection, peer, expected = transport_for(protocol_close())

    with pytest.raises(obs_websocket.ObsWebSocketError) as caught:
        fail(operation, transport)

    assert not isinstance(caught.value, obs_websocket.ObsWebSocketDisconnected)
    assert str(caught.value) == "OBS control transport failed"
    assert SECRET not in str(caught.value)
    assert caught.value.__cause__ is None
    assert peer.revalidate_calls == 1
    assert connection.close_socket_calls == 1
    assert peer.close_calls == expected.close_calls == 1


@pytest.mark.parametrize("operation", ["send", "receive"])
@pytest.mark.parametrize("failure", [clean_close, socket_eof], ids=["clean", "eof"])
def test_identity_loss_overrides_connection_loss_without_exposing_identity(
    operation: str, failure
) -> None:
    transport, connection, peer, expected = transport_for(
        failure(), fail_identity_on=2
    )

    with pytest.raises(obs_websocket.ObsWebSocketError) as caught:
        fail(operation, transport)

    assert not isinstance(caught.value, obs_websocket.ObsWebSocketDisconnected)
    assert str(caught.value) == "OBS peer identity could not be verified"
    assert SECRET not in str(caught.value)
    assert caught.value.__cause__ is None
    assert peer.revalidate_calls == 2
    assert connection.close_socket_calls == 1
    assert peer.close_calls == expected.close_calls == 1


def test_closed_transport_is_not_reported_as_a_new_disconnect() -> None:
    transport, _, _, _ = transport_for(clean_close())
    transport.close()

    with pytest.raises(obs_websocket.ObsWebSocketError) as caught:
        transport.receive(0.1)

    assert not isinstance(caught.value, obs_websocket.ObsWebSocketDisconnected)
    assert str(caught.value) == "OBS control transport is closed"
