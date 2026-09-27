"""Pure public snapshot grammar: no private tokens, normalization or runtime work."""

import builtins
from pathlib import Path
import socket
import subprocess
import sys
import threading

import pytest

from utterleaf.app_status import presentation_reply, snapshot_message, snapshot_reply, status_message
from utterleaf.model_presentation import PUBLIC_MODEL_TOKENS


STATES = {
    "idle": "Idle · app is running",
    "ready": "Ready · applied speech model loaded",
    "listening": "Listening · speech capture in progress",
    "processing": "Processing · preparing or transcribing speech",
    "attention": "Needs attention · check the tray or open Help",
    "unknown": "App is running · detailed status unavailable",
}
MODELS = {
    "tiny": "Tiny", "tiny.en": "Tiny English", "base": "Base", "base.en": "Base English",
    "small": "Small", "small.en": "Small English", "medium": "Medium", "medium.en": "Medium English",
    "large-v3": "Large v3", "distil-small.en": "Distilled Small English", "custom": "Custom model",
}


@pytest.mark.parametrize("state", STATES)
def test_all_public_models_and_states_roundtrip_using_fixed_local_names(state):
    assert PUBLIC_MODEL_TOKENS == frozenset(MODELS) - {"custom"}
    for token, name in MODELS.items():
        reply = snapshot_reply(state, token)
        assert reply == f"status-v2:{state}:{token}"
        assert reply.isascii() and len(reply) <= 36
        assert snapshot_message(reply) == f"{STATES[state]}\nLoaded model for applied settings: {name}."


@pytest.mark.parametrize("state", STATES)
def test_missing_proof_never_encodes_ready_and_other_states_keep_unconfirmed(state):
    expected = "idle" if state == "ready" else state
    assert snapshot_reply(state, None) == f"status-v2:{expected}:unconfirmed"
    assert snapshot_message(snapshot_reply(state, None)) == (
        f"{STATES[expected]}\nLoaded model for applied settings: not confirmed.")
    assert snapshot_message("status-v2:ready:unconfirmed") is None


@pytest.mark.parametrize("value", [
    None, "", "READY", " ready", "ready ", "recording", "busy", "error", "private-sentinel",
    "idle:tiny", "idle\n", "idle\x00", "ıdle", "unknown\u202e", 1, True, [], {}, object(),
])
def test_encoder_invalid_states_are_unknown_without_string_coercion(value):
    assert snapshot_reply(value, "tiny") == "status-v2:unknown:tiny"
    assert snapshot_reply(value, None) == "status-v2:unknown:unconfirmed"


@pytest.mark.parametrize("value", [
    "", "Tiny", " tiny", "tiny ", "tiny\n", "tiny\x00", "tіny", "custom\u202e", "unconfirmed",
    "private-sentinel", "C:/private-sentinel/model", "/private-sentinel/model", "private/repository",
    "tiny:idle", "tiny.en\r\nstatus-v2:ready:tiny", pytest.param("x" * 5000, id="oversized-model"),
    1, True, [], {}, object(),
])
def test_encoder_invalid_models_are_unconfirmed_not_custom_or_ready(value):
    assert snapshot_reply("idle", value) == "status-v2:idle:unconfirmed"
    assert snapshot_reply("ready", value) == "status-v2:idle:unconfirmed"


@pytest.mark.parametrize("reply", [
    None, "", "unknown", "restart-required", "unauthorized", "status-v1:ready", "status-v3:ready:tiny",
    "STATUS-V2:ready:tiny", "status-v2:Ready:tiny", "status-v2:ready:Tiny", "status-v2:ready:Custom",
    "status-v2", "status-v2:", "status-v2:idle", "status-v2::tiny", "status-v2:ready:",
    "status-v2:ready:tiny:", "status-v2:ready:tiny:private-sentinel", ":status-v2:ready:tiny",
    "status-v2:recording:tiny", "status-v2:busy:tiny", "status-v2:error:tiny", "status-v2:private:tiny",
    "status-v2:ready:private-sentinel", "status-v2:ready:C:/private-sentinel", "status-v2:ready:/private",
    "status-v2:ready:org/model", "status-v2:ready:tіny", "status-v2:ready:tiny\u202e",
    "status-v2:ready:tiny\x00", "status-v2:ready:tiny\n", "status-v2:ready:tiny\r\n",
    "status-v2:ready:tiny\t", "status-v2:ready:tiny ", " status-v2:ready:tiny", "\nstatus-v2:ready:tiny",
    "status-v2: ready:tiny", "status-v2:ready: tiny", "status-v2:ready:tiny\u00a0",
    "status-v2:ready:tiny\nstatus-v2:ready:base",
    pytest.param("status-v2:ready:" + "x" * 100_000, id="oversized-reply"),
    '{"reply":"status-v2:ready:tiny"}', b"status-v2:ready:tiny", 1, True, [], {}, object(),
])
def test_parser_rejects_malformed_non_v2_private_and_oversized_replies(reply):
    assert snapshot_message(reply) is None


def test_tokens_must_be_plain_strings_and_are_not_coerced():
    class UntrustedString(str):
        def __hash__(self):
            raise AssertionError("Do not invoke an untrusted token's hash")

    class UntrustedObject:
        def __str__(self):
            raise AssertionError("Do not stringify an untrusted token")

    assert snapshot_reply(UntrustedString("ready"), UntrustedString("tiny")) == "status-v2:unknown:unconfirmed"
    assert snapshot_reply(UntrustedObject(), UntrustedObject()) == "status-v2:unknown:unconfirmed"
    assert snapshot_message(UntrustedString("status-v2:ready:tiny")) is None
    assert snapshot_message(UntrustedObject()) is None


def test_exact_maximum_frame_is_accepted_but_appended_data_is_rejected():
    reply = "status-v2:processing:distil-small.en"
    assert snapshot_message(reply) == (
        "Processing · preparing or transcribing speech\n"
        "Loaded model for applied settings: Distilled Small English.")
    for suffix in (":", " ", "\n", "x", "private-sentinel"):
        assert snapshot_message(reply + suffix) is None


def test_legacy_presentation_and_status_remain_unchanged():
    assert presentation_reply("recording") == "status-v1:listening"
    assert presentation_reply("busy") == "status-v1:processing"
    for state, message in STATES.items():
        assert status_message("status-v1:" + state) == message
    assert status_message("unknown") == "App is running · detailed status unavailable in this version"
    assert status_message(None) == "App not reached · Start Utterleaf, then refresh status"
    assert status_message("status-v2:ready:tiny") == "Could not read app status · restart Utterleaf, then retry"


def test_codec_calls_perform_no_file_network_or_worker_operations(monkeypatch):
    def forbidden(*_args, **_kwargs):
        pytest.fail("Snapshot codec crossed an I/O or worker boundary")

    with monkeypatch.context() as patch:
        patch.setattr(builtins, "open", forbidden)
        patch.setattr(Path, "open", forbidden)
        patch.setattr(Path, "stat", forbidden)
        patch.setattr(socket, "socket", forbidden)
        patch.setattr(threading.Thread, "start", forbidden)
        for state in STATES:
            for token in (*MODELS, None):
                assert snapshot_message(snapshot_reply(state, token)) is not None


def test_codec_import_is_lightweight_in_a_fresh_interpreter():
    script = """
import sys
from utterleaf.app_status import snapshot_message, snapshot_reply
forbidden = ('utterleaf.app', 'utterleaf.audio', 'utterleaf.config', 'utterleaf.hardware',
             'utterleaf.models', 'utterleaf.model_inventory', 'utterleaf.transcribe',
             'utterleaf.settings_ui', 'utterleaf.ipc', 'tkinter', 'sounddevice', 'numpy',
             'faster_whisper', 'openvino')
assert not any(name in sys.modules for name in forbidden), sorted(set(forbidden) & sys.modules.keys())
assert snapshot_reply('ready', 'tiny') == 'status-v2:ready:tiny'
assert snapshot_message('status-v2:ready:custom').endswith('Custom model.')
"""
    result = subprocess.run([sys.executable, "-B", "-c", script], capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr
