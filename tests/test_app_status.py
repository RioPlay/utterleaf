from types import SimpleNamespace
import threading

import pytest

from utterleaf import app as app_module
from utterleaf.app import ENGINE_FAILED, LOADING, Utterleaf
from utterleaf.app_status import presentation_reply, status_message
from utterleaf.config import Config


@pytest.mark.parametrize(
    ("color", "reply"),
    [
        ("idle", "status-v1:idle"),
        ("recording", "status-v1:listening"),
        ("busy", "status-v1:processing"),
        ("error", "status-v1:attention"),
        ("not-a-presentation-state", "status-v1:unknown"),
    ],
)
def test_presentation_reply_is_a_fixed_enum(color, reply):
    assert presentation_reply(color) == reply


@pytest.mark.parametrize(
    ("reply", "message"),
    [
        ("status-v1:idle", "Idle · app is running"),
        ("status-v1:ready", "Ready · applied speech model loaded"),
        ("status-v1:listening", "Listening · speech capture in progress"),
        ("status-v1:processing", "Processing · preparing or transcribing speech"),
        ("status-v1:attention", "Needs attention · check the tray or open Help"),
        ("status-v1:unknown", "App is running · detailed status unavailable"),
        ("unknown", "App is running · detailed status unavailable in this version"),
        ("restart-required", "Restart Utterleaf to check its status"),
        (None, "App not reached · Start Utterleaf, then refresh status"),
    ],
)
def test_status_message_uses_only_fixed_local_copy(reply, message):
    assert status_message(reply) == message


@pytest.mark.parametrize(
    "reply",
    [
        "",
        "unauthorized",
        "STATUS-V1:IDLE",
        " status-v1:idle",
        "status-v1:idle ",
        "status-v1:ready:private-model-name",
        '{"status":"status-v1:idle"}',
        "private transcript from USB Microphone at C:\\Users\\example",
    ],
)
def test_status_message_rejects_malformed_or_private_server_output(reply):
    message = status_message(reply)
    assert message == "Could not read app status · restart Utterleaf, then retry"
    if reply:
        assert reply not in message


def test_app_initial_status_is_processing_without_capture_or_model_work(monkeypatch):
    calls = []

    def fail(name):
        return lambda *args, **kwargs: pytest.fail(f"unexpected {name}")

    monkeypatch.setattr(app_module, "Recorder", lambda **kwargs: calls.append(("recorder", kwargs)) or object())
    monkeypatch.setattr(app_module, "Indicator", lambda **kwargs: calls.append(("indicator", kwargs)) or object())
    monkeypatch.setattr(app_module, "pick", fail("hardware selection"))
    monkeypatch.setattr(app_module, "load_model", fail("model loading"))

    app = Utterleaf(Config(tray=False, indicator=False, beep=False))

    assert app._reported_status == "status-v1:processing"
    assert calls == [
        ("recorder", {"device": "", "continuous": True}),
        ("indicator", {"enabled": False}),
    ]


class _Indicator:
    def __init__(self):
        self.calls = []

    def set(self, badge, caption=""):
        self.calls.append((badge, caption))


def _publisher() -> Utterleaf:
    app = object.__new__(Utterleaf)
    app._presentation_lock = threading.RLock()
    app._stop = threading.Event()
    app._status = "ordinary status"
    app._reported_status = "status-v1:unknown"
    app._indicator_generation = 0
    app.icon = None
    app.indicator = _Indicator()
    return app


def test_published_status_follows_loading_and_error_overrides_without_private_text():
    app = _publisher()
    private_status = "private transcript and C:\\Users\\example\\model.bin"
    private_caption = "USB Microphone — confidential device"

    app._set_icon("idle", LOADING)
    assert app._handle_ipc("status") == "status-v1:processing"
    app._set_icon("recording", private_status, caption=private_caption)
    assert app._handle_ipc("status") == "status-v1:listening"
    app._set_icon("busy", private_status, caption=private_caption)
    assert app._handle_ipc("status") == "status-v1:processing"
    app._set_icon("idle", private_status)
    assert app._handle_ipc("status") == "status-v1:idle"
    app._set_icon("idle", ENGINE_FAILED, badge="engine", caption=private_caption)
    assert app._handle_ipc("status") == "status-v1:attention"
    app._set_icon("error", private_status, caption=private_caption)
    reply = app._handle_ipc("status")
    assert reply == "status-v1:attention"
    assert private_status not in reply
    assert private_caption not in reply


def test_status_query_is_read_only_and_needs_no_runtime_subsystems(monkeypatch):
    app = object.__new__(Utterleaf)
    app._reported_status = "status-v1:listening"
    app.last_text = "private transcript"
    app.last_app = "private field name"
    app.cfg = SimpleNamespace(microphone="private microphone", model="private model path")
    before = dict(app.__dict__)

    monkeypatch.setattr(
        app_module,
        "threading",
        SimpleNamespace(Thread=lambda *args, **kwargs: pytest.fail("status query started a worker")),
    )

    reply = app._handle_ipc(" STATUS ")

    assert reply == "status-v1:listening"
    assert app.__dict__ == before
    assert all(value not in reply for value in (app.last_text, app.last_app, app.cfg.microphone, app.cfg.model))


def test_status_query_without_a_published_state_uses_fixed_unknown_fallback():
    app = object.__new__(Utterleaf)
    assert app._handle_ipc("status") == "status-v1:unknown"
    assert app.__dict__ == {}
