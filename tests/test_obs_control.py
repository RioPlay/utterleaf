from __future__ import annotations

import json
import logging
import math
import re
import sys
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any

import pytest
from websockets.sync.server import serve

from utterleaf import obs_control
from utterleaf.obs_control import (
    ObsControl,
    ObsControlCancelled,
    ObsControlError,
    ObsVersion,
    StreamEvent,
    StreamSnapshot,
)
from utterleaf.obs_websocket import (
    ObsWebSocketCancelled,
    ObsWebSocketError,
    ObsWebSocketTimeout,
)


REAL_OPEN_EXPECTED_EXECUTABLE = (
    obs_control.obs_websocket.windows_peer_identity.open_expected_executable
)
PASSWORD = "correct horse battery staple"
EXPECTED_EXECUTABLE = "C:/Program Files/obs-studio/bin/64bit/obs64.exe"
SALT = "AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8="
CHALLENGE = "ICEiIyQlJicoKSorLC0uLzAxMjM0NTY3ODk6Ozw9Pj8="
EXPECTED_AUTH = "th5vywpVNtPJMLKfhB6OFIS35ehlZ1/CksCgFb28AUc="
UNICODE_PASSWORD = "päss🔒word"
EXPECTED_UNICODE_AUTH = "On8gggUwINBFJT+PIJcD5k3ujSciJDPdJDYfXyO/mwE="
VERSION_DATA = {
    "rpcVersion": 1,
    "availableRequests": ["GetVersion", "GetStreamStatus"],
    "obsVersion": "32.2.2",
    "obsWebSocketVersion": "5.7.4",
}


def wire(op: Any, data: Any) -> str:
    return json.dumps({"op": op, "d": data}, separators=(",", ":"))


def hello(*, rpc_version: Any = 1, authentication: Any = ...) -> str:
    data: dict[str, Any] = {"rpcVersion": rpc_version}
    data["authentication"] = (
        {"challenge": CHALLENGE, "salt": SALT}
        if authentication is ...
        else authentication
    )
    return wire(0, data)


def identified(*, rpc_version: Any = 1) -> str:
    return wire(2, {"negotiatedRpcVersion": rpc_version})


def stream_event(active: bool, state: str) -> str:
    return wire(
        5,
        {
            "eventIntent": 64,
            "eventType": "StreamStateChanged",
            "eventData": {"outputActive": active, "outputState": state},
        },
    )


def ignored_event(*, intent: int = 1, event_type: str = "CustomEvent") -> str:
    return wire(
        5,
        {
            "eventIntent": intent,
            "eventType": event_type,
            "eventData": {
                "eventData": {"private": "do-not-retain"},
                "outputPath": "C:/private/recording.mkv",
            },
        },
    )


def exit_started() -> str:
    return wire(
        5,
        {"eventIntent": 1, "eventType": "ExitStarted", "eventData": {}},
    )


class ScriptedTransport:
    def __init__(self, responses: list[Any]) -> None:
        self.responses = list(responses)
        self.sent: list[str] = []
        self.receive_timeouts: list[float] = []
        self.close_calls = 0
        self.verify_peer_calls = 0
        self.verify_peer_error: BaseException | None = None
        self.operations: list[str] = []
        self.retain_peer_process_calls = 0
        self.retain_peer_process_result: Any = None
        self.retain_peer_process_error: BaseException | None = None
        self.retain_peer_process_callback: Callable[[], None] | None = None

    def send(self, text: str) -> None:
        self.operations.append("send")
        self.sent.append(text)

    def receive(self, timeout: float) -> str:
        self.operations.append("receive")
        self.receive_timeouts.append(timeout)
        if not self.responses:
            raise ObsWebSocketTimeout("script exhausted")
        response = self.responses.pop(0)
        if callable(response):
            response = response(self)
        if isinstance(response, BaseException):
            raise response
        assert isinstance(response, str)
        return response

    def close(self) -> None:
        self.close_calls += 1

    def verify_peer(self) -> None:
        self.operations.append("verify_peer")
        self.verify_peer_calls += 1
        if self.verify_peer_error is not None:
            raise self.verify_peer_error

    def retain_peer_process(self) -> Any:
        self.operations.append("retain_peer_process")
        self.retain_peer_process_calls += 1
        if self.retain_peer_process_callback is not None:
            self.retain_peer_process_callback()
        if self.retain_peer_process_error is not None:
            raise self.retain_peer_process_error
        return self.retain_peer_process_result


class FakeProcessLease:
    def __init__(self) -> None:
        self.close_calls = 0

    def close(self) -> None:
        self.close_calls += 1


class FakeNativePeer:
    def revalidate(self, *, cancelled, deadline: float) -> None:
        return None

    def close(self) -> None:
        return None


class FakeNativeExpected:
    def __init__(self) -> None:
        self.peer = FakeNativePeer()

    def verify(self, sock, *, cancelled, deadline: float) -> FakeNativePeer:
        return self.peer

    def close(self) -> None:
        return None


def install_native_identity_stub(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        obs_control.obs_websocket.windows_peer_identity,
        "open_expected_executable",
        lambda _path: FakeNativeExpected(),
    )


def connect_control(
    host: str,
    port: int,
    password: str,
    *,
    cancelled: Callable[[], bool],
) -> ObsControl:
    return ObsControl.connect(
        host,
        port,
        password,
        expected_executable=EXPECTED_EXECUTABLE,
        cancelled=cancelled,
    )


def request_reply(
    request_type: str,
    response_data: Any,
    *,
    request_id: str | None = None,
    result: Any = True,
    code: Any = 100,
    response_type: str | None = None,
    op: Any = 7,
) -> Callable[[ScriptedTransport], str]:
    def reply(transport: ScriptedTransport) -> str:
        request = json.loads(transport.sent[-1])
        request_data = request["d"]
        return wire(
            op,
            {
                "requestType": response_type or request_type,
                "requestId": request_id or request_data["requestId"],
                "requestStatus": {"result": result, "code": code},
                "responseData": response_data,
            },
        )

    return reply


def version_reply(data: Any = VERSION_DATA, **kwargs: Any) -> Callable[[ScriptedTransport], str]:
    return request_reply("GetVersion", data, **kwargs)


def status_reply(
    *, active: Any = False, reconnecting: Any = False, **kwargs: Any
) -> Callable[[ScriptedTransport], str]:
    return request_reply(
        "GetStreamStatus",
        {"outputActive": active, "outputReconnecting": reconnecting},
        **kwargs,
    )


def install_stub(
    monkeypatch: pytest.MonkeyPatch, responses: list[Any]
) -> tuple[
    ScriptedTransport,
    list[tuple[str, int, str, Callable[[], bool]]],
]:
    transport = ScriptedTransport(responses)
    calls: list[tuple[str, int, str, Callable[[], bool]]] = []

    def connect(
        host: str,
        port: int,
        *,
        expected_executable: str,
        cancelled: Callable[[], bool],
    ) -> ScriptedTransport:
        calls.append((host, port, expected_executable, cancelled))
        return transport

    monkeypatch.setattr(obs_control.obs_websocket, "connect", connect)
    return transport, calls


def connected_stub(
    monkeypatch: pytest.MonkeyPatch,
    *,
    before_identified: list[Any] | None = None,
    cancelled: Callable[[], bool] = lambda: False,
) -> tuple[
    ObsControl,
    ScriptedTransport,
    list[tuple[str, int, str, Callable[[], bool]]],
]:
    transport, calls = install_stub(
        monkeypatch,
        [
            hello(),
            *(before_identified or []),
            identified(),
            version_reply(),
        ],
    )
    control = connect_control(
        "127.0.0.1", 4455, PASSWORD, cancelled=cancelled
    )
    return control, transport, calls


def sent_request(transport: ScriptedTransport, index: int) -> dict[str, Any]:
    return json.loads(transport.sent[index])


def test_connect_uses_independent_auth_vector_and_random_request_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    control, transport, calls = connected_stub(monkeypatch)

    assert calls == [
        ("127.0.0.1", 4455, EXPECTED_EXECUTABLE, calls[0][3])
    ]
    assert transport.operations[:3] == ["receive", "verify_peer", "send"]
    assert transport.verify_peer_calls == 1
    identify_message = sent_request(transport, 0)
    assert identify_message == {
        "op": 1,
        "d": {
            "rpcVersion": 1,
            "authentication": EXPECTED_AUTH,
            "eventSubscriptions": 65,
        },
    }
    version_request = sent_request(transport, 1)
    assert version_request["op"] == 6
    assert version_request["d"]["requestType"] == "GetVersion"
    assert set(version_request["d"]) == {"requestType", "requestId"}
    assert re.fullmatch(r"[0-9a-f]{32}-1", version_request["d"]["requestId"])
    assert control.version == ObsVersion(studio="32.2.2", websocket="5.7.4")
    assert PASSWORD not in repr(control)
    assert PASSWORD not in repr(control.__dict__)

    control.close()
    control.close()
    assert transport.close_calls == 1


def test_expected_executable_has_no_public_default() -> None:
    with pytest.raises(TypeError, match="expected_executable"):
        ObsControl.connect(  # type: ignore[call-arg]
            "127.0.0.1", 4455, PASSWORD, cancelled=lambda: False
        )


def test_failed_peer_recheck_sends_no_authentication_proof(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transport, _ = install_stub(monkeypatch, [hello()])
    transport.verify_peer_error = ObsWebSocketError("private identity detail")

    with pytest.raises(ObsControlError) as raised:
        connect_control("127.0.0.1", 4455, PASSWORD, cancelled=lambda: False)

    assert str(raised.value) == "Could not connect to authenticated local OBS"
    assert raised.value.__cause__ is None
    assert transport.sent == []
    assert transport.close_calls == 1


def test_connections_use_distinct_random_request_prefixes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first, first_transport, _ = connected_stub(monkeypatch)
    first_id = sent_request(first_transport, 1)["d"]["requestId"]
    first.close()
    second, second_transport, _ = connected_stub(monkeypatch)
    second_id = sent_request(second_transport, 1)["d"]["requestId"]
    second.close()

    assert first_id.split("-", 1)[0] != second_id.split("-", 1)[0]


def test_literal_unicode_password_matches_independent_auth_vector(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def accept_authentication(transport: ScriptedTransport) -> str:
        identify_message = json.loads(transport.sent[-1])
        assert identify_message["d"]["authentication"] == EXPECTED_UNICODE_AUTH
        return identified()

    transport, _ = install_stub(
        monkeypatch, [hello(), accept_authentication, version_reply()]
    )

    control = connect_control(
        "127.0.0.1", 4455, UNICODE_PASSWORD, cancelled=lambda: False
    )

    assert UNICODE_PASSWORD not in repr(control.__dict__)
    control.close()
    assert transport.close_calls == 1


@pytest.mark.parametrize(
    "password",
    [None, b"password", "", "x" * 1025, "\ud800"],
)
def test_password_is_required_and_validated_before_transport(
    monkeypatch: pytest.MonkeyPatch, password: Any
) -> None:
    def forbidden_connect(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("transport must not be opened")

    monkeypatch.setattr(obs_control.obs_websocket, "connect", forbidden_connect)

    with pytest.raises(ObsControlError) as raised:
        connect_control("127.0.0.1", 4455, password, cancelled=lambda: False)

    assert "x" * 100 not in str(raised.value)
    assert "surrogate" not in str(raised.value).lower()


def test_quarantined_and_live_stream_events_are_ordered_and_mark_status_stale(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    control, transport, _ = connected_stub(
        monkeypatch,
        before_identified=[stream_event(False, "OBS_WEBSOCKET_OUTPUT_STARTING")],
    )
    transport.responses.extend(
        [
            ignored_event(),
            ignored_event(intent=64, event_type="RecordStateChanged"),
            stream_event(False, "OBS_WEBSOCKET_OUTPUT_STOPPED"),
            status_reply(active=False, reconnecting=False),
        ]
    )

    assert control.stream_status() == StreamSnapshot(
        active=False, reconnecting=False, event_revision=2, events_pending=True
    )
    assert control.poll_event() == StreamEvent(
        active=False, state="OBS_WEBSOCKET_OUTPUT_STARTING", revision=1
    )
    assert control.poll_event() == StreamEvent(
        active=False, state="OBS_WEBSOCKET_OUTPUT_STOPPED", revision=2
    )
    assert "C:/private/recording.mkv" not in repr(control.__dict__)
    transport.responses.append(ObsWebSocketTimeout("nothing ready"))
    assert control.poll_event(timeout=0.01) is None
    assert not control.closed
    control.close()


def test_event_queue_accepts_limit_and_refuses_next_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events = [
        stream_event(bool(index % 2), "OBS_WEBSOCKET_OUTPUT_STARTED")
        for index in range(33)
    ]
    transport, _ = install_stub(
        monkeypatch, [hello(), *events, identified(), version_reply()]
    )

    with pytest.raises(ObsControlError, match="events could not be processed"):
        connect_control("127.0.0.1", 4455, PASSWORD, cancelled=lambda: False)

    assert transport.close_calls == 1


def test_exit_started_closes_without_reconnect(monkeypatch: pytest.MonkeyPatch) -> None:
    control, transport, calls = connected_stub(monkeypatch)
    transport.responses.append(exit_started())

    with pytest.raises(ObsControlError, match="shutting down"):
        control.poll_event()

    assert control.closed
    assert transport.close_calls == 1
    assert len(calls) == 1
    with pytest.raises(ObsControlError, match="closed"):
        control.stream_status()
    assert len(calls) == 1


def test_exit_started_before_identified_aborts_quarantine(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transport, _ = install_stub(
        monkeypatch, [hello(), exit_started(), identified(), version_reply()]
    )

    with pytest.raises(ObsControlError, match="shutting down"):
        connect_control("127.0.0.1", 4455, PASSWORD, cancelled=lambda: False)

    assert transport.close_calls == 1
    assert [json.loads(message)["op"] for message in transport.sent] == [1]


@pytest.mark.parametrize(
    "message",
    [
        wire(
            5,
            {"eventIntent": 64, "eventType": "ExitStarted", "eventData": {}},
        ),
        wire(
            5,
            {
                "eventIntent": 1,
                "eventType": "StreamStateChanged",
                "eventData": {
                    "outputActive": True,
                    "outputState": "OBS_WEBSOCKET_OUTPUT_STARTED",
                },
            },
        ),
    ],
    ids=["exit-as-output", "stream-as-general"],
)
def test_known_event_types_require_their_exact_subscription_intent(
    monkeypatch: pytest.MonkeyPatch, message: str
) -> None:
    control, transport, _ = connected_stub(monkeypatch)
    transport.responses.append(message)

    with pytest.raises(ObsControlError, match="Unexpected OBS event subscription"):
        control.poll_event()

    assert control.closed
    assert transport.close_calls == 1


@pytest.mark.parametrize(
    "message",
    [
        wire(5, {"eventIntent": True, "eventType": "CustomEvent", "eventData": {}}),
        wire(5, {"eventIntent": 2, "eventType": "CustomEvent", "eventData": {}}),
        wire(5, {"eventIntent": 1, "eventType": 7, "eventData": {}}),
        wire(
            5,
            {
                "eventIntent": 64,
                "eventType": "StreamStateChanged",
                "eventData": {"outputActive": 1, "outputState": "OBS_WEBSOCKET_OUTPUT_STARTED"},
            },
        ),
        wire(
            5,
            {
                "eventIntent": 64,
                "eventType": "StreamStateChanged",
                "eventData": {"outputActive": True, "outputState": "UNKNOWN"},
            },
        ),
    ],
    ids=[
        "bool-intent",
        "unsubscribed-intent",
        "non-string-type",
        "non-bool-active",
        "unknown-state",
    ],
)
def test_event_envelope_and_stream_schema_are_strict(
    monkeypatch: pytest.MonkeyPatch, message: str
) -> None:
    control, transport, _ = connected_stub(monkeypatch)
    transport.responses.append(message)

    with pytest.raises(ObsControlError):
        control.poll_event()

    assert control.closed
    assert transport.close_calls == 1


@pytest.mark.parametrize(
    "raw",
    [
        '{"op":0,"op":0,"d":{}}',
        '{"op":0,"d":{"rpcVersion":1,"rpcVersion":1}}',
        '{"op":NaN,"d":{}}',
        '{"op":Infinity,"d":{}}',
        '{"op":0,"d":{"value":1e999}}',
        "[]",
        '{"op":true,"d":{}}',
        '{"op":0,"d":[]}',
        "{not-json",
        '"root"',
        "é" * 32_769,
        "x" * 65_537,
    ],
    ids=[
        "duplicate-root",
        "duplicate-nested",
        "nan",
        "infinity",
        "overflow-float",
        "array-root",
        "boolean-op",
        "array-data",
        "invalid-json",
        "string-root",
        "utf8-oversize",
        "character-oversize",
    ],
)
def test_malformed_or_oversize_messages_are_rejected_and_closed(
    monkeypatch: pytest.MonkeyPatch, raw: str
) -> None:
    transport, _ = install_stub(monkeypatch, [raw])

    with pytest.raises(ObsControlError) as raised:
        connect_control("127.0.0.1", 4455, PASSWORD, cancelled=lambda: False)

    assert transport.close_calls == 1
    assert raw[:100] not in str(raised.value)


@pytest.mark.parametrize(
    "hello_message,identified_message",
    [
        (hello(rpc_version=True), identified()),
        (hello(rpc_version=0), identified()),
        (hello(rpc_version=2), identified()),
        (hello(rpc_version="1"), identified()),
        (hello(authentication=None), identified()),
        (hello(authentication={"challenge": CHALLENGE}), identified()),
        (hello(authentication={"challenge": "not-base64", "salt": SALT}), identified()),
        (hello(authentication={"challenge": CHALLENGE, "salt": "AA=="}), identified()),
        (hello(), identified(rpc_version=True)),
        (hello(), identified(rpc_version=0)),
        (hello(), identified(rpc_version=2)),
        (hello(), identified(rpc_version="1")),
    ],
)
def test_handshake_requires_rpc1_and_canonical_authentication(
    monkeypatch: pytest.MonkeyPatch,
    hello_message: str,
    identified_message: str,
) -> None:
    transport, _ = install_stub(
        monkeypatch, [hello_message, identified_message, version_reply()]
    )

    with pytest.raises(ObsControlError):
        connect_control("127.0.0.1", 4455, PASSWORD, cancelled=lambda: False)

    assert transport.close_calls == 1


@pytest.mark.parametrize(
    "version_data",
    [
        {**VERSION_DATA, "rpcVersion": True},
        {**VERSION_DATA, "rpcVersion": 0},
        {**VERSION_DATA, "availableRequests": "GetVersion"},
        {**VERSION_DATA, "availableRequests": ["GetVersion"]},
        {**VERSION_DATA, "availableRequests": ["GetVersion", 7, "GetStreamStatus"]},
        {**VERSION_DATA, "availableRequests": ["x" * 129, "GetVersion", "GetStreamStatus"]},
        {**VERSION_DATA, "availableRequests": ["x"] * 1_025},
        {**VERSION_DATA, "obsVersion": ""},
        {**VERSION_DATA, "obsVersion": "32 version"},
        {**VERSION_DATA, "obsVersion": "x" * 65},
        {**VERSION_DATA, "obsWebSocketVersion": None},
        {**VERSION_DATA, "obsWebSocketVersion": "4.9.1"},
    ],
)
def test_version_capabilities_and_fields_are_strict(
    monkeypatch: pytest.MonkeyPatch, version_data: dict[str, Any]
) -> None:
    transport, _ = install_stub(
        monkeypatch, [hello(), identified(), version_reply(version_data)]
    )

    with pytest.raises(ObsControlError):
        connect_control("127.0.0.1", 4455, PASSWORD, cancelled=lambda: False)

    assert transport.close_calls == 1


def bad_status_reply(kind: str) -> Callable[[ScriptedTransport], str]:
    if kind == "wrong_id":
        return status_reply(request_id="attacker-chosen")
    if kind == "wrong_type":
        return status_reply(response_type="StartStream")
    if kind == "wrong_op":
        return status_reply(op=6)
    if kind == "false_result":
        return status_reply(result=False)
    if kind == "wrong_code":
        return status_reply(code=401)
    if kind == "bool_code":
        return status_reply(code=True)
    if kind == "active_int":
        return status_reply(active=1)
    if kind == "reconnecting_int":
        return status_reply(reconnecting=0)
    if kind == "data_list":
        return request_reply("GetStreamStatus", [])
    raise AssertionError(kind)


@pytest.mark.parametrize(
    "kind",
    [
        "wrong_id",
        "wrong_type",
        "wrong_op",
        "false_result",
        "wrong_code",
        "bool_code",
        "active_int",
        "reconnecting_int",
        "data_list",
    ],
)
def test_response_correlation_status_and_schema_are_strict(
    monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    control, transport, _ = connected_stub(monkeypatch)
    transport.responses.append(bad_status_reply(kind))

    with pytest.raises(ObsControlError):
        control.stream_status()

    assert control.closed
    assert transport.close_calls == 1


def test_only_version_and_stream_status_requests_can_be_sent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    control, transport, _ = connected_stub(monkeypatch)
    sent_before = list(transport.sent)

    with pytest.raises(ObsControlError, match="Unsupported OBS control request"):
        control._request("StartStream")

    assert transport.sent == sent_before
    assert control.closed
    assert not any(
        hasattr(control, method)
        for method in ("start_stream", "stop_stream", "start_record", "stop_record")
    )
    request_types = [
        item["d"]["requestType"]
        for item in map(json.loads, transport.sent)
        if item["op"] == 6
    ]
    assert request_types == ["GetVersion"]


def test_status_sends_only_read_request_and_returns_typed_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    control, transport, _ = connected_stub(monkeypatch)
    transport.responses.append(status_reply(active=True, reconnecting=True))

    snapshot = control.stream_status()

    assert snapshot == StreamSnapshot(
        active=True, reconnecting=True, event_revision=0, events_pending=False
    )
    assert type(snapshot.active) is bool
    assert type(snapshot.reconnecting) is bool
    request_types = [
        item["d"]["requestType"]
        for item in map(json.loads, transport.sent)
        if item["op"] == 6
    ]
    assert request_types == ["GetVersion", "GetStreamStatus"]
    control.close()


def test_authenticated_control_returns_caller_owned_process_lease(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    control, transport, _ = connected_stub(monkeypatch)
    lease = FakeProcessLease()
    transport.retain_peer_process_result = lease

    retained = control.retain_peer_process()

    assert retained is lease
    assert transport.retain_peer_process_calls == 1
    assert not control.closed
    control.close()
    assert lease.close_calls == 0
    lease.close()
    assert lease.close_calls == 1


@pytest.mark.parametrize(
    "identified,has_version",
    [(False, False), (False, True), (True, False)],
)
def test_incomplete_authentication_cannot_retain_process(
    identified: bool, has_version: bool
) -> None:
    transport = ScriptedTransport([])
    control = ObsControl(transport, lambda: False)
    control._identified = identified
    if has_version:
        control.version = ObsVersion("32.2.2", "5.7.4")

    with pytest.raises(ObsControlError, match="authentication is incomplete"):
        control.retain_peer_process()

    assert transport.retain_peer_process_calls == 0
    assert not control.closed
    control.close()


def test_closed_control_cannot_retain_process(monkeypatch: pytest.MonkeyPatch) -> None:
    control, transport, _ = connected_stub(monkeypatch)
    control.close()

    with pytest.raises(ObsControlError, match="closed"):
        control.retain_peer_process()

    assert transport.retain_peer_process_calls == 0
    assert transport.close_calls == 1


def test_retain_failure_closes_control_and_sanitizes_native_detail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    control, transport, _ = connected_stub(monkeypatch)
    transport.retain_peer_process_error = ObsWebSocketError("private process detail")

    with pytest.raises(ObsControlError) as raised:
        control.retain_peer_process()

    assert str(raised.value) == "OBS control connection ended unexpectedly"
    assert raised.value.__cause__ is None
    assert control.closed
    assert transport.close_calls == 1


def test_cancellation_after_retain_closes_returned_lease_and_control(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cancelled = False
    control, transport, _ = connected_stub(
        monkeypatch, cancelled=lambda: cancelled
    )
    lease = FakeProcessLease()
    transport.retain_peer_process_result = lease

    def cancel_after_duplication() -> None:
        nonlocal cancelled
        cancelled = True

    transport.retain_peer_process_callback = cancel_after_duplication

    with pytest.raises(ObsControlCancelled, match="cancelled"):
        control.retain_peer_process()

    assert lease.close_calls == 1
    assert control.closed
    assert transport.close_calls == 1


def test_cancellation_before_request_closes_without_sending(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cancelled = False
    control, transport, _ = connected_stub(monkeypatch, cancelled=lambda: cancelled)
    sent_before = list(transport.sent)
    cancelled = True

    with pytest.raises(ObsControlCancelled, match="cancelled"):
        control.stream_status()

    assert transport.sent == sent_before
    assert transport.close_calls == 1
    assert control.closed


def test_transport_connect_cancellation_is_sanitized(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret = "do-not-repeat-this-password"

    def cancelled_connect(*args: Any, **kwargs: Any) -> None:
        raise ObsWebSocketCancelled(secret)

    monkeypatch.setattr(obs_control.obs_websocket, "connect", cancelled_connect)

    with pytest.raises(ObsControlCancelled) as raised:
        connect_control("127.0.0.1", 4455, PASSWORD, cancelled=lambda: False)

    assert secret not in str(raised.value)
    assert raised.value.__cause__ is None


def test_constructor_failure_closes_transport_and_is_sanitized(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transport, _ = install_stub(monkeypatch, [])
    monkeypatch.setattr(
        obs_control.secrets,
        "token_hex",
        lambda _size: (_ for _ in ()).throw(RuntimeError("secret constructor detail")),
    )

    with pytest.raises(ObsControlError) as raised:
        connect_control("127.0.0.1", 4455, PASSWORD, cancelled=lambda: False)

    assert str(raised.value) == "Could not connect to authenticated local OBS"
    assert raised.value.__cause__ is None
    assert transport.close_calls == 1


def test_wrong_password_authentication_failure_is_closed_and_sanitized(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def reject_authentication(transport: ScriptedTransport) -> BaseException:
        identify_message = json.loads(transport.sent[-1])
        assert identify_message["d"]["authentication"] != EXPECTED_AUTH
        return ObsWebSocketError("peer authentication detail")

    transport, _ = install_stub(monkeypatch, [hello(), reject_authentication])

    with pytest.raises(ObsControlError) as raised:
        connect_control(
            "127.0.0.1", 4455, "wrong password", cancelled=lambda: False
        )

    assert str(raised.value) == "Could not connect to authenticated local OBS"
    assert raised.value.__cause__ is None
    assert transport.close_calls == 1


def test_transport_failure_is_sanitized_and_never_reconnects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    control, transport, calls = connected_stub(monkeypatch)
    secret = "peer echoed a credential"
    transport.responses.append(ObsWebSocketError(secret))

    with pytest.raises(ObsControlError) as raised:
        control.stream_status()

    assert str(raised.value) == "OBS control connection ended unexpectedly"
    assert secret not in repr(raised.value)
    assert raised.value.__cause__ is None
    assert transport.close_calls == 1
    assert len(calls) == 1


def test_request_deadline_closes_connection_without_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    control, transport, calls = connected_stub(monkeypatch)
    sent_before = len(transport.sent)
    ticks = iter([100.0, 106.0])
    monkeypatch.setattr(obs_control.time, "monotonic", lambda: next(ticks))

    with pytest.raises(ObsControlError, match="status request timed out"):
        control.stream_status()

    assert len(transport.sent) == sent_before + 1
    assert transport.receive_timeouts[-1] <= obs_control.REQUEST_TIMEOUT
    assert transport.close_calls == 1
    assert len(calls) == 1


@pytest.mark.parametrize("timeout", [True, False, 0, -1, 5.1, math.nan, math.inf, "1"])
def test_poll_timeout_is_finite_positive_and_bounded(
    monkeypatch: pytest.MonkeyPatch, timeout: Any
) -> None:
    control, transport, _ = connected_stub(monkeypatch)

    with pytest.raises(ValueError, match="event timeout"):
        control.poll_event(timeout)

    assert transport.close_calls == 0
    control.close()


def test_poll_deadline_returns_none_without_closing(monkeypatch: pytest.MonkeyPatch) -> None:
    control, transport, _ = connected_stub(monkeypatch)
    ticks = iter([20.0, 21.0])
    monkeypatch.setattr(obs_control.time, "monotonic", lambda: next(ticks))

    assert control.poll_event(timeout=0.5) is None
    assert not control.closed
    assert transport.close_calls == 0
    control.close()


@contextmanager
def loopback_server(
    handler: Callable[[Any], None],
) -> Iterator[int]:
    errors: list[BaseException] = []
    finished = threading.Event()

    def checked_handler(connection: Any) -> None:
        try:
            handler(connection)
        except BaseException as exc:
            errors.append(exc)
        finally:
            finished.set()

    server_logger = logging.Logger("tests.obs.synthetic-server")
    server_logger.disabled = True
    server_logger.propagate = False
    server_logger.addHandler(logging.NullHandler())
    server = serve(
        checked_handler,
        "127.0.0.1",
        0,
        subprotocols=["obswebsocket.json"],
        compression=None,
        ping_interval=None,
        server_header=None,
        logger=server_logger,
    )
    thread = threading.Thread(target=server.serve_forever, name="obs-control-test")
    thread.start()
    try:
        yield server.socket.getsockname()[1]
        assert finished.wait(2), "loopback OBS peer did not finish"
        assert errors == []
    finally:
        server.shutdown()
        thread.join(2)
        assert not thread.is_alive()


def test_real_loopback_adapter_auth_status_and_ordered_events(
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[dict[str, Any]] = []
    caplog.set_level(logging.DEBUG)
    install_native_identity_stub(monkeypatch)

    def handler(connection: Any) -> None:
        connection.send(hello())
        identify_message = json.loads(connection.recv(timeout=2))
        seen.append(identify_message)
        connection.send(stream_event(False, "OBS_WEBSOCKET_OUTPUT_STARTING"))
        connection.send(identified())

        version_request = json.loads(connection.recv(timeout=2))
        seen.append(version_request)
        connection.send(
            wire(
                7,
                {
                    "requestType": "GetVersion",
                    "requestId": version_request["d"]["requestId"],
                    "requestStatus": {"result": True, "code": 100},
                    "responseData": VERSION_DATA,
                },
            )
        )

        status_request = json.loads(connection.recv(timeout=2))
        seen.append(status_request)
        connection.send(ignored_event())
        connection.send(stream_event(True, "OBS_WEBSOCKET_OUTPUT_STARTED"))
        connection.send(
            wire(
                7,
                {
                    "requestType": "GetStreamStatus",
                    "requestId": status_request["d"]["requestId"],
                    "requestStatus": {"result": True, "code": 100},
                    "responseData": {
                        "outputActive": True,
                        "outputReconnecting": False,
                    },
                },
            )
        )

    with loopback_server(handler) as port:
        with connect_control(
            "127.0.0.1", port, PASSWORD, cancelled=lambda: False
        ) as control:
            assert control.version == ObsVersion("32.2.2", "5.7.4")
            assert control.stream_status() == StreamSnapshot(True, False, 2, True)
            assert control.poll_event() == StreamEvent(
                False, "OBS_WEBSOCKET_OUTPUT_STARTING", 1
            )
            assert control.poll_event() == StreamEvent(
                True, "OBS_WEBSOCKET_OUTPUT_STARTED", 2
            )

    assert seen[0] == {
        "op": 1,
        "d": {
            "rpcVersion": 1,
            "authentication": EXPECTED_AUTH,
            "eventSubscriptions": 65,
        },
    }
    assert [message["d"]["requestType"] for message in seen[1:]] == [
        "GetVersion",
        "GetStreamStatus",
    ]
    client_records = [
        record for record in caplog.records if record.name.startswith("utterleaf.obs")
    ]
    assert client_records == []


def test_real_loopback_wrong_password_closes_4009_without_requests(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[dict[str, Any]] = []
    install_native_identity_stub(monkeypatch)

    def handler(connection: Any) -> None:
        connection.send(hello())
        identify_message = json.loads(connection.recv(timeout=2))
        seen.append(identify_message)
        assert identify_message["d"]["authentication"] != EXPECTED_AUTH
        connection.close(code=4009, reason="Authentication Failed")

    with loopback_server(handler) as port:
        with pytest.raises(ObsControlError) as raised:
            connect_control(
                "127.0.0.1", port, "wrong password", cancelled=lambda: False
            )

    assert str(raised.value) == "Could not connect to authenticated local OBS"
    assert raised.value.__cause__ is None
    assert len(seen) == 1
    assert seen[0]["op"] == 1


@pytest.mark.skipif(sys.platform != "win32", reason="Windows peer identity integration")
def test_real_windows_peer_identity_controls_complete_status_flow(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected_path = getattr(sys, "_base_executable", sys.executable)
    seen_request_types: list[str] = []
    monkeypatch.setattr(
        obs_control.obs_websocket.windows_peer_identity,
        "open_expected_executable",
        REAL_OPEN_EXPECTED_EXECUTABLE,
    )

    def handler(connection: Any) -> None:
        connection.send(hello())
        identify_message = json.loads(connection.recv(timeout=2))
        assert identify_message["d"]["authentication"] == EXPECTED_AUTH
        connection.send(identified())

        version_request = json.loads(connection.recv(timeout=2))
        seen_request_types.append(version_request["d"]["requestType"])
        connection.send(
            wire(
                7,
                {
                    "requestType": "GetVersion",
                    "requestId": version_request["d"]["requestId"],
                    "requestStatus": {"result": True, "code": 100},
                    "responseData": VERSION_DATA,
                },
            )
        )

        status_request = json.loads(connection.recv(timeout=2))
        seen_request_types.append(status_request["d"]["requestType"])
        connection.send(
            wire(
                7,
                {
                    "requestType": "GetStreamStatus",
                    "requestId": status_request["d"]["requestId"],
                    "requestStatus": {"result": True, "code": 100},
                    "responseData": {
                        "outputActive": False,
                        "outputReconnecting": False,
                    },
                },
            )
        )
        try:
            connection.recv(timeout=2)
        except Exception:
            pass

    with loopback_server(handler) as port:
        with ObsControl.connect(
            "127.0.0.1",
            port,
            PASSWORD,
            expected_executable=expected_path,
            cancelled=lambda: False,
        ) as control:
            assert control.version == ObsVersion("32.2.2", "5.7.4")
            assert control.stream_status() == StreamSnapshot(False, False, 0, False)

    assert seen_request_types == ["GetVersion", "GetStreamStatus"]
