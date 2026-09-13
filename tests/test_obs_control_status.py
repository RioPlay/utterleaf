"""Strict, read-only Utterleaf OBS plugin compatibility checks."""
from __future__ import annotations

import json

import pytest

from utterleaf.obs_control import ObsControlDisconnected, ObsControlError, ObsPluginStatus
from utterleaf.obs_websocket import ObsWebSocketDisconnected, ObsWebSocketError

from test_obs_control import connect_control, hello, identified, install_stub, version_reply, wire, VERSION_DATA
from test_obs_control_enrollment import KEY, _prepare_response, _vendor_response


STATUS = {
    "ok": True,
    "protocolVersion": 1,
    "commandVersion": 1,
    "audioVersion": 1,
    "maxBusMask": 63,
}


def _status_response(transport, *, response=STATUS, vendor="Utterleaf", operation="GetStatus", extra=None):
    request = json.loads(transport.sent[-1])["d"]
    data = {
        "requestType": "CallVendorRequest",
        "requestId": request["requestId"],
        "requestStatus": {"result": True, "code": 100},
        "responseData": {
            "vendorName": vendor,
            "requestType": operation,
            "responseData": response,
        },
    }
    if extra is not None:
        data["responseData"]["extra"] = extra
    return wire(7, data)


def _connected(monkeypatch, responses, *, vendor=True):
    version = dict(VERSION_DATA)
    if vendor:
        version["availableRequests"] = [*VERSION_DATA["availableRequests"], "CallVendorRequest"]
    transport, _ = install_stub(
        monkeypatch, [hello(), identified(), version_reply(version), *responses]
    )
    return connect_control("127.0.0.1", 4455, "pw", cancelled=lambda: False), transport


def test_plugin_status_uses_exact_empty_request_and_typed_result(monkeypatch):
    control, transport = _connected(monkeypatch, [_status_response])
    with control:
        assert control.plugin_status() == ObsPluginStatus(1, 1, 1, 63)
        request = json.loads(transport.sent[-1])["d"]
        assert request["requestType"] == "CallVendorRequest"
        assert request["requestData"] == {
            "vendorName": "Utterleaf", "requestType": "GetStatus", "requestData": {},
        }


def test_repeated_status_is_inert_before_and_after_preparation(monkeypatch):
    responses = [_status_response, _status_response, _vendor_response, _prepare_response, _status_response]
    control, transport = _connected(monkeypatch, responses)
    with control:
        assert control.plugin_status() == ObsPluginStatus(1, 1, 1, 63)
        assert control.plugin_status() == ObsPluginStatus(1, 1, 1, 63)
        session = control.prepare_session(KEY)
        assert len(session) == 16
        assert control.plugin_status() == ObsPluginStatus(1, 1, 1, 63)
    operations = [
        json.loads(item)["d"]["requestData"]["requestType"]
        for item in transport.sent[2:]
    ]
    assert operations == ["GetStatus", "GetStatus", "IssueAuthorization", "PrepareSession", "GetStatus"]


@pytest.mark.parametrize("change", [
    lambda data: data.update(protocolVersion=2),
    lambda data: data.update(commandVersion=2),
    lambda data: data.update(audioVersion=2),
    lambda data: data.update(maxBusMask=62),
    lambda data: data.update(commandVersion=True),
    lambda data: data.update(extra=0),
])
def test_plugin_status_rejects_unsupported_or_malformed_metadata(monkeypatch, change):
    response = dict(STATUS)
    change(response)
    control, transport = _connected(
        monkeypatch, [lambda current: _status_response(current, response=response)]
    )
    with pytest.raises(ObsControlError):
        control.plugin_status()
    assert control.closed and len(transport.sent) == 3


@pytest.mark.parametrize("reply", [
    lambda transport: _status_response(transport, vendor="Other"),
    lambda transport: _status_response(transport, operation="PrepareSession"),
    lambda transport: _status_response(transport, extra=False),
    lambda transport: _status_response(transport, response={"ok": False}),
])
def test_plugin_status_rejects_wrong_wrapper_or_refusal(monkeypatch, reply):
    control, transport = _connected(monkeypatch, [reply])
    with pytest.raises(ObsControlError):
        control.plugin_status()
    assert control.closed and len(transport.sent) == 3


def test_plugin_status_requires_vendor_request_support_without_sending(monkeypatch):
    control, transport = _connected(monkeypatch, [], vendor=False)
    with pytest.raises(ObsControlError):
        control.plugin_status()
    assert control.closed and len(transport.sent) == 2


def test_plugin_status_preserves_only_typed_transport_disconnect(monkeypatch):
    control, transport = _connected(monkeypatch, [ObsWebSocketDisconnected("private")])
    with pytest.raises(ObsControlDisconnected) as caught:
        control.plugin_status()
    assert str(caught.value) == "OBS control disconnected"
    assert control.closed and len(transport.sent) == 3


def test_plugin_status_keeps_other_transport_failures_terminal(monkeypatch):
    control, _transport = _connected(monkeypatch, [ObsWebSocketError("private")])
    with pytest.raises(ObsControlError) as caught:
        control.plugin_status()
    assert type(caught.value) is ObsControlError
    assert "private" not in str(caught.value)


def test_connect_preserves_typed_disconnect(monkeypatch):
    install_stub(monkeypatch, [hello(), identified(), ObsWebSocketDisconnected("private")])
    with pytest.raises(ObsControlDisconnected) as caught:
        connect_control("127.0.0.1", 4455, "pw", cancelled=lambda: False)
    assert str(caught.value) == "OBS control disconnected"
