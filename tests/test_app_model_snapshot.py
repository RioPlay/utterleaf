"""Applied-model status uses synthetic metadata, never a model or microphone."""

from dataclasses import replace
import threading

import pytest

from utterleaf import app as app_module, transcribe
from utterleaf.config import Config


@pytest.fixture
def runtime(monkeypatch):
    app = object.__new__(app_module.Utterleaf)
    app.cfg = Config(model="base", device="cpu", language="en", allow_network=False)
    app._stop = threading.Event()
    app._model_generation = 7
    app._model_phase = "ready"
    app._reported_status = "status-v1:idle"
    monkeypatch.setattr(transcribe, "_engine_config_key", transcribe._config_key(app.cfg))

    def forbidden(*_args, **_kwargs):
        pytest.fail("Read-only status accessed an external subsystem")

    for target in ("utterleaf.app.load_model", "utterleaf.app.reset_engine", "utterleaf.app.pick",
                   "utterleaf.config.load", "utterleaf.config.save", "utterleaf.hardware.probe",
                   "utterleaf.audio.list_input_names", "utterleaf.audio.Recorder.start",
                   "utterleaf.model_setup.inspect_model", "socket.create_connection"):
        monkeypatch.setattr(target, forbidden)
    return app


@pytest.mark.parametrize("state", ["idle", "ready", "listening", "processing", "attention", "unknown"])
@pytest.mark.parametrize("confirmed", [True, False])
def test_public_state_and_matching_proof_are_combined_without_runtime_work(runtime, monkeypatch, state, confirmed):
    runtime._reported_status = "status-v1:" + state
    if not confirmed:
        monkeypatch.setattr(transcribe, "_engine_config_key", None)
    expected = "ready" if state == "idle" and confirmed else state
    if expected == "ready" and not confirmed:
        expected = "idle"
    token = "base.en" if confirmed else "unconfirmed"
    assert runtime._handle_ipc("status-detail") == f"status-v2:{expected}:{token}"


@pytest.mark.parametrize("phase,expected", [("loading", "processing:unconfirmed"),
    ("failed", "attention:base.en"), ("ready", "ready:base.en")])
def test_idle_snapshot_preserves_durable_load_state(runtime, phase, expected):
    runtime._model_phase = phase
    assert runtime._handle_ipc("status-detail") == "status-v2:" + expected


@pytest.mark.parametrize("state", ["listening", "processing", "attention"])
def test_loading_cannot_hide_active_state_or_reuse_old_matching_proof(runtime, monkeypatch, state):
    runtime._model_phase = "loading"
    runtime._reported_status = "status-v1:" + state
    monkeypatch.setattr(app_module, "loaded_model_token", lambda _cfg: pytest.fail("Loading reused old proof"))
    assert runtime._handle_ipc("status-detail") == f"status-v2:{state}:unconfirmed"


@pytest.mark.parametrize("change", [{"model": "tiny"}, {"device": "gpu"},
    {"compute_type": "float16"}, {"language": "fr"}])
def test_changed_applied_request_cannot_name_previous_loaded_model(runtime, change):
    runtime.cfg = replace(runtime.cfg, **change)
    assert runtime._handle_ipc("status-detail") == "status-v2:idle:unconfirmed"


@pytest.mark.parametrize("model,language,token", [("tiny", "en", "tiny.en"),
    ("base", "fr", "base"), ("distil-small.en", "en", "distil-small.en"),
    ("private-org/private-model", "en", "custom"),
    (r"C:\Users\Private Person\model", "en", "custom")])
def test_names_come_from_loaded_request_not_backend_caption_or_take(runtime, monkeypatch, model, language, token):
    runtime.cfg = replace(runtime.cfg, model=model, language=language)
    monkeypatch.setattr(transcribe, "_engine_config_key", transcribe._config_key(runtime.cfg))
    monkeypatch.setattr(transcribe, "_engine_key", ("private-backend", "private-device"))
    runtime._display_caption = "private transcript and device name"
    runtime._take_config = Config(model="medium")
    assert runtime._handle_ipc("status-detail") == f"status-v2:ready:{token}"


@pytest.mark.parametrize("change", ["replace", "equal_replace", "mutate", "generation", "phase", "status", "quit"])
def test_changes_during_sampling_invalidate_the_entire_combined_claim(runtime, monkeypatch, change):
    applied = runtime.cfg
    captured = []

    def sample(cfg):
        assert cfg == applied and cfg is not applied
        captured.append(cfg)
        if change == "replace":
            runtime.cfg = replace(applied, model="tiny")
        elif change == "equal_replace":
            runtime.cfg = replace(applied)
        elif change == "mutate":
            applied.model = "tiny"
        elif change == "generation":
            runtime._model_generation += 1
        elif change == "phase":
            runtime._model_phase = "failed"
        elif change == "status":
            runtime._reported_status = "status-v1:listening"
        else:
            runtime._stop.set()
        return "base.en"

    monkeypatch.setattr(app_module, "loaded_model_token", sample)
    assert runtime._handle_ipc("status-detail") == "status-v2:unknown:unconfirmed"
    assert len(captured) == 1 and captured[0].model == "base"


def test_quit_snapshot_does_not_consult_old_proof(runtime, monkeypatch):
    runtime._stop.set()
    monkeypatch.setattr(app_module, "loaded_model_token", lambda _cfg: pytest.fail("Read proof after Quit"))
    assert runtime._handle_ipc("status-detail") == "status-v2:unknown:unconfirmed"


def test_snapshot_preserves_preferences_generation_and_presentation(runtime, monkeypatch):
    before = replace(runtime.cfg), runtime._model_generation, runtime._model_phase, runtime._reported_status
    monkeypatch.setattr(threading.Thread, "start", lambda _self: pytest.fail("Status started a worker"))
    for _ in range(3):
        assert runtime._handle_ipc("status-detail") == "status-v2:ready:base.en"
    assert (runtime.cfg, runtime._model_generation, runtime._model_phase, runtime._reported_status) == before


def test_query_remains_nonblocking_while_runtime_lanes_are_held(runtime, monkeypatch):
    locks = [threading.Lock() for _ in range(6)]
    for name, lock in zip(("_presentation_lock", "_model_load_lock", "_capture_lock", "_lock"), locks):
        setattr(runtime, name, lock)
    monkeypatch.setattr(transcribe, "_lock", locks[4])
    monkeypatch.setattr(transcribe, "_infer_lock", locks[5])
    answers, errors = [], []
    finished = threading.Event()

    def read():
        try:
            answers.append(runtime._handle_ipc("status-detail"))
        except BaseException as exc:
            errors.append(exc)
        finally:
            finished.set()

    reader = threading.Thread(target=read, daemon=True)
    for lock in locks:
        lock.acquire()
    try:
        reader.start()
        assert finished.wait(2), "Status waited on a runtime lane"
    finally:
        for lock in reversed(locks):
            lock.release()
        reader.join(2)
    assert not reader.is_alive() and errors == []
    assert answers == ["status-v2:ready:base.en"]


def test_legacy_status_and_ping_are_unchanged(runtime):
    assert runtime._handle_ipc("status") == "status-v1:ready"
    assert runtime._handle_ipc("ping") == "ok"
    runtime._reported_status = "status-v1:listening"
    assert runtime._handle_ipc("status") == "status-v1:listening"
    assert runtime._handle_ipc("status-detail") == "status-v2:listening:base.en"
