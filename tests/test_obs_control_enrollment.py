"""Focused wire and lifecycle checks for the typed OBS enrollment exchange."""
from __future__ import annotations

import hmac
import json
import logging
import os
import struct
import threading
import pytest

from utterleaf import obs_authorization, obs_control
from utterleaf.obs_control import ObsControlError, ObsControlCancelled
from utterleaf.obs_websocket import ObsWebSocketError

from test_obs_control import (
    connected_stub,
    connect_control,
    hello,
    identified,
    install_stub,
    install_native_identity_stub,
    loopback_server,
    status_reply,
    stream_event,
    version_reply,
    wire,
    PASSWORD,
    EXPECTED_AUTH,
    VERSION_DATA,
)


KEY = bytearray(range(1, 33))


def _proof(challenge):
    return hmac.digest(KEY, b"Utterleaf OBS prepare authorization v1\0" + bytes.fromhex(challenge), "sha256").hex()
def _challenge(issue):
    return struct.pack("<4sBBBBI16s32s", b"ULAA", 1, 1, 0,
                       issue["additionalMixMask"], issue["clientPid"],
                       bytes.fromhex(issue["sessionId"]), b"n" * 32).hex()


def _vendor_response(transport):
    request = json.loads(transport.sent[-1])
    request_id = request["d"]["requestId"]
    data = {"requestType": "CallVendorRequest", "requestId": request_id,
            "requestStatus": {"result": True, "code": 100},
            "responseData": {"vendorName": "Utterleaf",
                              "requestType": "IssueAuthorization",
                              "responseData": {
                                  "ok": True, "protocolVersion": 1,
                                  "challenge": _challenge(request["d"]["requestData"]["requestData"]),
                              }}}
    return wire(7, data)


def _prepare_response(transport):
    request = json.loads(transport.sent[-1])
    request_id = request["d"]["requestId"]
    return wire(7, {"requestType": "CallVendorRequest", "requestId": request_id,
                    "requestStatus": {"result": True, "code": 100},
                    "responseData": {"vendorName": "Utterleaf",
                                      "requestType": "PrepareSession",
                                      "responseData": {"ok": True,
                                                        "protocolVersion": 1}}})


def _connected(monkeypatch, responses, *, cancelled=lambda: False):
    version = dict(VERSION_DATA)
    version["availableRequests"] = [*VERSION_DATA["availableRequests"], "CallVendorRequest"]
    transport, _ = install_stub(monkeypatch, [hello(), identified(), version_reply(version), *responses])
    control = connect_control("127.0.0.1", 4455, "pw", cancelled=cancelled)
    return control, transport


def test_prepare_session_uses_typed_two_step_exchange_and_fresh_session(monkeypatch):
    control, transport = _connected(monkeypatch, [_vendor_response, _prepare_response])
    try:
        result = control.prepare_session(KEY)
        calls = [json.loads(item)["d"] for item in transport.sent[2:]]
        assert result == bytes.fromhex(calls[0]["requestData"]["requestData"]["sessionId"])
        assert [item["requestType"] for item in calls] == ["CallVendorRequest", "CallVendorRequest"]
        first = calls[0]["requestData"]
        assert set(first) == {"vendorName", "requestType", "requestData"}
        assert first["vendorName"] == "Utterleaf"
        assert first["requestType"] == "IssueAuthorization"
        issue = first["requestData"]
        assert issue["clientPid"] == os.getpid()
        assert isinstance(issue["sessionId"], str)
        assert len(issue["sessionId"]) == 32
        assert issue["sessionId"] == issue["sessionId"].lower()
        assert int(issue["sessionId"], 16) != 0
        assert issue["additionalMixMask"] == 0
        second = calls[1]["requestData"]
        assert set(second) == {"vendorName", "requestType", "requestData"}
        assert second["vendorName"] == "Utterleaf"
        assert second["requestType"] == "PrepareSession"
        assert set(second["requestData"]) == {"challenge", "proof"}
        assert len(second["requestData"]["challenge"]) == 120
        assert len(second["requestData"]["proof"]) == 64
        assert second["requestData"]["proof"] == _proof(second["requestData"]["challenge"])
        assert KEY == bytearray(range(1, 33))
    finally:
        control.close()


def test_prepare_session_rejects_malformed_vendor_response_without_proof(monkeypatch):
    def malformed(transport):
        request = json.loads(transport.sent[-1])
        return wire(7, {"requestType": "CallVendorRequest", "requestId": request["d"]["requestId"],
                        "requestStatus": {"result": True, "code": 100},
                        "responseData": {"vendorName": "Other", "requestType": "IssueAuthorization",
                                          "responseData": {"ok": True, "protocolVersion": 1,
                                                            "challenge": "ab" * 60}}})
    control, transport = _connected(monkeypatch, [malformed])
    with pytest.raises(ObsControlError):
        control.prepare_session(bytes(KEY), additional_mix_mask=1)
    assert len(transport.sent) == 3
    assert transport.close_calls >= 1


@pytest.mark.parametrize("key,mask", [
    (b"x", 0), (bytes(32), 0), ("x" * 32, 0), (memoryview(KEY), 0),
    (bytes(KEY), -1), (bytes(KEY), 64), (bytes(KEY), True), (bytes(KEY), 1.0),
])
def test_prepare_session_rejects_bad_arguments_before_network(monkeypatch, key, mask):
    control, transport = _connected(monkeypatch, [])
    try:
        with pytest.raises(ObsControlError):
            control.prepare_session(key, additional_mix_mask=mask)
        assert len(transport.sent) == 2
        assert control.closed
    finally:
        control.close()


def test_prepare_session_peer_failure_sends_no_proof(monkeypatch):
    def fail_peer(transport):
        transport.verify_peer_error = ObsControlError("peer changed")
        return _vendor_response(transport)
    control, transport = _connected(monkeypatch, [fail_peer])
    with pytest.raises(ObsControlError):
        control.prepare_session(bytes(KEY))
    assert len(transport.sent) == 3
    assert transport.close_calls >= 1


def test_prepare_session_rejects_second_use_on_same_connection(monkeypatch):
    control, transport = _connected(monkeypatch, [_vendor_response, _prepare_response])
    try:
        control.prepare_session(bytes(KEY))
        with pytest.raises(ObsControlError):
            control.prepare_session(bytes(KEY))
        assert len(transport.sent) == 4
    finally:
        control.close()


def test_status_only_server_remains_usable_until_preparation_is_requested(monkeypatch):
    control, transport, _ = connected_stub(monkeypatch)
    transport.responses.append(status_reply())
    assert not control.stream_status().active
    with pytest.raises(ObsControlError, match="does not support"):
        control.prepare_session(KEY)
    assert [json.loads(item)["d"].get("requestType") for item in transport.sent] == [
        None, "GetVersion", "GetStreamStatus",
    ]
    assert control.closed


@pytest.mark.parametrize("stage", ["issue", "prepare"])
@pytest.mark.parametrize("path,value", [
    (("requestId",), "stale"),
    (("requestType",), "GetStreamStatus"),
    (("requestStatus", "result"), 1),
    (("requestStatus", "code"), True),
    (("responseData", "vendorName"), "utterleaf"),
    (("responseData", "requestType"), "OtherOperation"),
    (("responseData", "extra"), "unexpected"),
    (("responseData", "responseData"), []),
    (("responseData", "responseData"), {"ok": False}),
    (("responseData", "responseData", "ok"), 1),
    (("responseData", "responseData", "protocolVersion"), True),
    (("responseData", "responseData", "protocolVersion"), 2),
    (("responseData", "responseData", "extra"), "unexpected"),
])
def test_vendor_response_contract_is_strict(monkeypatch, stage, path, value):
    def malformed(transport):
        message = json.loads((_vendor_response if stage == "issue" else _prepare_response)(transport))
        target = message["d"]
        for field in path[:-1]:
            target = target[field]
        target[path[-1]] = value
        return json.dumps(message)
    control, transport = _connected(monkeypatch, [malformed] if stage == "issue" else [_vendor_response, malformed])
    with pytest.raises(ObsControlError):
        control.prepare_session(KEY)
    assert control.closed
    assert len(transport.sent) == (3 if stage == "issue" else 4)


@pytest.mark.parametrize("offset", [0, 4, 5, 6, 7, 8, 12])
def test_changed_challenge_binding_never_gets_a_proof(monkeypatch, offset):
    def changed(transport):
        message = json.loads(_vendor_response(transport))
        response = message["d"]["responseData"]["responseData"]
        challenge = bytearray.fromhex(response["challenge"])
        challenge[offset] ^= 1
        response["challenge"] = challenge.hex()
        return json.dumps(message)
    control, transport = _connected(monkeypatch, [changed])
    with pytest.raises(ObsControlError):
        control.prepare_session(KEY, additional_mix_mask=3)
    assert control.closed and len(transport.sent) == 3


@pytest.mark.parametrize("challenge", [None, 120, "a" * 118, "A" * 120, "gg" * 60, " " * 120])
def test_challenge_hex_is_canonical(monkeypatch, challenge):
    def changed(transport):
        message = json.loads(_vendor_response(transport))
        message["d"]["responseData"]["responseData"]["challenge"] = challenge
        return json.dumps(message)
    control, transport = _connected(monkeypatch, [changed])
    with pytest.raises(ObsControlError):
        control.prepare_session(KEY)
    assert control.closed and len(transport.sent) == 3


@pytest.mark.parametrize("fails", [False, True])
def test_post_challenge_peer_check_precedes_signing_and_owned_key_is_cleared(monkeypatch, fails):
    control, transport = _connected(monkeypatch, [
        _vendor_response, ObsWebSocketError("private detail") if fails else _prepare_response,
    ])
    original = obs_authorization.create_prepare_proof
    observed = []
    def checked(key, *args, **kwargs):
        assert transport.operations[-1] == "verify_peer"
        assert len(transport.sent) == 3
        assert key is not KEY and key == KEY
        observed.append(key)
        return original(key, *args, **kwargs)
    monkeypatch.setattr(obs_authorization, "create_prepare_proof", checked)
    with control:
        if fails:
            with pytest.raises(ObsControlError):
                control.prepare_session(KEY)
        else:
            control.prepare_session(KEY)
    assert observed == [bytearray(32)]
    assert KEY == bytearray(range(1, 33))


@pytest.mark.parametrize("stage", ["issue", "prepare"])
@pytest.mark.parametrize("failure_type", [TimeoutError, ObsWebSocketError])
def test_request_failure_is_terminal_and_not_retried(monkeypatch, stage, failure_type):
    failure = failure_type("private remote detail")
    control, transport = _connected(monkeypatch, [failure] if stage == "issue" else [_vendor_response, failure])
    with pytest.raises(ObsControlError) as caught:
        control.prepare_session(KEY)
    assert "private remote detail" not in str(caught.value)
    sent = len(transport.sent)
    assert sent == (3 if stage == "issue" else 4)
    with pytest.raises(ObsControlError):
        control.prepare_session(KEY)
    assert len(transport.sent) == sent and control.closed


def test_cancellation_after_challenge_sends_no_proof(monkeypatch):
    cancelled = threading.Event()
    def cancel(transport):
        response = _vendor_response(transport)
        cancelled.set()
        return response
    control, transport = _connected(monkeypatch, [cancel], cancelled=cancelled.is_set)
    with pytest.raises(ObsControlCancelled):
        control.prepare_session(KEY)
    assert control.closed and len(transport.sent) == 3


@pytest.mark.parametrize("second", ["stream_status", "poll_event", "retain_peer_process", "prepare_session", "close"])
def test_overlapping_operations_close_without_crossing_responses(monkeypatch, second):
    entered, release = threading.Event(), threading.Event()
    failures = []
    def blocked(transport):
        entered.set()
        assert release.wait(2)
        return _vendor_response(transport)
    control, transport = _connected(monkeypatch, [blocked])
    def prepare():
        try:
            control.prepare_session(KEY)
        except ObsControlError as exc:
            failures.append(exc)
    worker = threading.Thread(target=prepare)
    worker.start()
    try:
        assert entered.wait(2)
        if second == "close":
            control.close()
        else:
            with pytest.raises(ObsControlError, match="serialized"):
                getattr(control, second)(*([KEY] if second == "prepare_session" else []))
    finally:
        release.set()
        worker.join(2)
        control.close()
    assert not worker.is_alive() and len(failures) == 1
    assert control.closed and len(transport.sent) == 3


def test_fresh_session_each_connection_and_events_preserve_order(monkeypatch):
    sessions = []
    for _ in range(2):
        control, transport = _connected(monkeypatch, [
            stream_event(False, "OBS_WEBSOCKET_OUTPUT_STARTING"), _vendor_response,
            stream_event(True, "OBS_WEBSOCKET_OUTPUT_STARTED"), _prepare_response,
        ])
        with control:
            sessions.append(control.prepare_session(KEY, additional_mix_mask=63))
            assert not control.poll_event().active
            assert control.poll_event().active
            assert json.loads(transport.sent[2])["d"]["requestData"]["requestData"]["additionalMixMask"] == 63
    assert len(set(sessions)) == 2


def test_real_loopback_prepare_matches_independent_proof_without_logging(monkeypatch, caplog):
    install_native_identity_stub(monkeypatch)
    caplog.set_level(logging.DEBUG)
    seen = []
    def handler(connection):
        def receive():
            message = json.loads(connection.recv(timeout=2))
            seen.append(message)
            return message["d"]
        def reply(request, data):
            connection.send(wire(7, {
                "requestType": request["requestType"], "requestId": request["requestId"],
                "requestStatus": {"result": True, "code": 100}, "responseData": data,
            }))
        connection.send(hello())
        assert receive()["authentication"] == EXPECTED_AUTH
        connection.send(identified())
        request = receive()
        reply(request, {**VERSION_DATA, "availableRequests": [*VERSION_DATA["availableRequests"], "CallVendorRequest"]})
        request = receive()
        assert request["requestType"] == "CallVendorRequest"
        vendor = request["requestData"]
        assert vendor["vendorName"] == "Utterleaf" and vendor["requestType"] == "IssueAuthorization"
        issue = vendor["requestData"]
        assert issue["clientPid"] == os.getpid() and issue["additionalMixMask"] == 5
        challenge = _challenge(issue)
        reply(request, {"vendorName": "Utterleaf", "requestType": "IssueAuthorization",
                        "responseData": {"ok": True, "protocolVersion": 1, "challenge": challenge}})
        request = receive()
        assert request["requestType"] == "CallVendorRequest"
        assert request["requestData"] == {
            "vendorName": "Utterleaf", "requestType": "PrepareSession",
            "requestData": {"challenge": challenge, "proof": _proof(challenge)},
        }
        reply(request, {"vendorName": "Utterleaf", "requestType": "PrepareSession",
                        "responseData": {"ok": True, "protocolVersion": 1}})
    with loopback_server(handler) as port:
        with connect_control("127.0.0.1", port, PASSWORD, cancelled=lambda: False) as control:
            session = control.prepare_session(KEY, additional_mix_mask=5)
    assert session.hex() == seen[2]["d"]["requestData"]["requestData"]["sessionId"]
    assert len(seen) == 4 and KEY.hex() not in json.dumps(seen)
    assert not [record for record in caplog.records if record.name.startswith(("utterleaf", "websockets"))]
