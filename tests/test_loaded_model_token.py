"""Loaded-model snapshots use synthetic engines, never models or devices."""

from dataclasses import replace
import threading

import pytest

from utterleaf import transcribe as transcription
from utterleaf.config import Config
from utterleaf.hardware import Accelerator
from utterleaf.model_presentation import PUBLIC_MODEL_TOKENS, model_token


EXPECTED_TOKENS = frozenset({
    "tiny", "tiny.en", "base", "base.en", "small", "small.en", "medium",
    "medium.en", "large-v3", "distil-small.en",
})
GPU = Accelerator("gpu", "Private hardware name", "ctranslate2", True)


@pytest.fixture
def engines(monkeypatch):
    monkeypatch.setattr(transcription, "_engine", None)
    monkeypatch.setattr(transcription, "_engine_key", None)
    monkeypatch.setattr(transcription, "_engine_config_key", None)
    monkeypatch.setattr(transcription, "_lock", threading.Lock())
    monkeypatch.setattr(transcription, "_infer_lock", threading.Lock())
    monkeypatch.setattr(transcription, "pick", lambda _cfg: transcription.CPU)
    monkeypatch.setattr(transcription, "mark_cuda_unusable", lambda: None)
    loaded = []

    def load(cfg, accelerator):
        engine = object()
        loaded.append((replace(cfg), accelerator, engine))
        return engine

    def blocked(*_args, **_kwargs):
        pytest.fail("Loaded-model snapshot accessed an external subsystem")

    monkeypatch.setattr(transcription, "_load_ctranslate", load)
    monkeypatch.setattr(transcription, "_load_openvino", load)
    for target in ("utterleaf.transcribe.ensure_ct2", "utterleaf.transcribe.ensure_ov",
                   "utterleaf.hardware.probe", "utterleaf.hardware.openvino_devices",
                   "utterleaf.config.load", "utterleaf.config.save", "socket.create_connection"):
        monkeypatch.setattr(target, blocked)
    return loaded


def test_public_token_catalogue_is_fixed_and_immutable():
    assert type(PUBLIC_MODEL_TOKENS) is frozenset
    assert PUBLIC_MODEL_TOKENS == EXPECTED_TOKENS


@pytest.mark.parametrize("name", sorted(EXPECTED_TOKENS))
def test_exact_public_tokens_are_preserved(name):
    assert model_token(name) == name


@pytest.mark.parametrize("name", [
    "", " small", "small ", "SMALL", "small\n", "large-v3.en",
    "private-org/private-model", r"C:\Users\Private Person\model",
    "/home/private-person/model", "../../private-model", "private-model.en",
    "status-v2:ready:tiny", None, [], 3,
])
def test_unknown_or_malformed_identifiers_are_never_echoed(name):
    assert model_token(name) == "custom"


@pytest.mark.parametrize("model,language,expected", [
    ("tiny", "en", "tiny.en"), ("base", "english", "base.en"),
    ("small", "auto", "small"), ("medium", "fr", "medium"),
    ("large-v3", "en", "large-v3"), ("distil-small.en", "en", "distil-small.en"),
    ("private-org/private-model", "en", "custom"),
    (r"C:\Users\Private Person\model", "en", "custom"),
])
def test_only_successful_matching_loads_expose_public_tokens(engines, model, language, expected):
    cfg = Config(model=model, language=language, allow_network=False)
    assert transcription.loaded_model_token(cfg) is None
    transcription.load_model(cfg)
    assert transcription.loaded_model_token(cfg) == expected
    assert len(engines) == 1 and not engines[0][0].allow_network


def test_cache_hit_and_non_model_preferences_keep_the_same_proof(engines, monkeypatch):
    cfg = Config()
    first = transcription.load_model(cfg)
    proof = transcription._engine_config_key
    changed = replace(cfg, microphone="Private microphone", beep=False, allow_network=False)
    monkeypatch.setattr(transcription, "pick", lambda _cfg: pytest.fail("Cached snapshot probed hardware"))
    assert transcription.load_model(changed) is first
    assert transcription.loaded_model_token(changed) == "small.en"
    assert transcription._engine_config_key is proof
    assert len(engines) == 1


@pytest.mark.parametrize("change", [
    {"model": "base"}, {"device": "gpu"}, {"compute_type": "float16"}, {"language": "fr"},
])
def test_changed_request_cannot_claim_previous_loaded_model(engines, change):
    cfg = Config(model="small", device="cpu")
    transcription.load_model(cfg)
    assert transcription.loaded_model_token(replace(cfg, **change)) is None
    assert transcription.loaded_model_token(cfg) == "small.en"


def test_reset_removes_the_loaded_token(engines):
    cfg = Config()
    transcription.load_model(cfg)
    transcription.reset_engine()
    assert transcription.loaded_model_token(cfg) is None


@pytest.mark.parametrize("failure", ["pick", "cpu", "fallback"])
def test_failed_replacement_cannot_retain_previous_token(engines, monkeypatch, failure):
    previous = Config(model="small", device="cpu")
    current = replace(previous, model="base")
    transcription.load_model(previous)

    def fail(*_args):
        assert transcription.loaded_model_token(previous) is None
        assert transcription.loaded_model_token(current) is None
        raise RuntimeError("Synthetic private load failure")

    if failure == "pick":
        monkeypatch.setattr(transcription, "pick", fail)
    else:
        monkeypatch.setattr(transcription, "pick", lambda _cfg: GPU if failure == "fallback" else transcription.CPU)
        monkeypatch.setattr(transcription, "_load_ctranslate", fail)
    with pytest.raises(RuntimeError, match="Synthetic private"):
        transcription.load_model(current)
    assert transcription.loaded_model_token(previous) is None
    assert transcription.loaded_model_token(current) is None


def test_cpu_fallback_still_matches_requested_preferences(engines, monkeypatch):
    cfg = Config(model="base", device="gpu")
    cpu_load = transcription._load_ctranslate

    def load(config, accelerator):
        if accelerator.kind == "gpu":
            raise RuntimeError("Synthetic private GPU failure")
        return cpu_load(config, accelerator)

    monkeypatch.setattr(transcription, "pick", lambda _cfg: GPU)
    monkeypatch.setattr(transcription, "_load_ctranslate", load)
    transcription.load_model(cfg)
    assert transcription._engine_key == ("base.en", "cpu", "ctranslate2")
    assert transcription.loaded_model_token(cfg) == "base.en"
    assert transcription.loaded_model_token(replace(cfg, device="cpu")) is None


@pytest.mark.parametrize("change", ["request", "reset", "equal_replacement", "different_replacement"])
def test_changes_while_mapping_invalidate_the_snapshot(engines, monkeypatch, change):
    cfg = Config()
    transcription.load_model(cfg)
    proof = transcription._engine_config_key

    def token(name):
        assert name == proof[0]
        if change == "request":
            cfg.model = "base"
        elif change == "reset":
            transcription.reset_engine()
        elif change == "equal_replacement":
            transcription._engine_config_key = tuple(list(proof))
            assert transcription._engine_config_key == proof
            assert transcription._engine_config_key is not proof
        else:
            transcription._engine_config_key = transcription._config_key(replace(cfg, model="base"))
        return model_token(name)

    monkeypatch.setattr(transcription, "model_token", token)
    assert transcription.loaded_model_token(cfg) is None


def test_replacement_during_request_recheck_is_detected(engines, monkeypatch):
    cfg = Config()
    transcription.load_model(cfg)
    config_key = transcription._config_key
    reads = []

    def read(config):
        result = config_key(config)
        reads.append(result)
        if len(reads) == 2:
            transcription._engine_config_key = None
        return result

    monkeypatch.setattr(transcription, "_config_key", read)
    assert transcription.loaded_model_token(cfg) is None
    assert len(reads) == 2


def test_snapshot_does_not_read_engine_or_actual_backend_or_mutate_preferences(engines, monkeypatch):
    cfg = Config()
    transcription.load_model(cfg)
    proof, before = transcription._engine_config_key, replace(cfg)

    class Unreadable:
        def __bool__(self):
            pytest.fail("Snapshot read the engine")

        def __getitem__(self, _key):
            pytest.fail("Snapshot read actual backend metadata")

    marker = Unreadable()
    monkeypatch.setattr(transcription, "_engine", marker)
    monkeypatch.setattr(transcription, "_engine_key", marker)
    monkeypatch.setattr(transcription, "pick", lambda _cfg: pytest.fail("Snapshot probed hardware"))
    for _ in range(3):
        assert transcription.loaded_model_token(cfg) == "small.en"
    assert transcription._engine_config_key is proof
    assert transcription._engine is marker and transcription._engine_key is marker
    assert cfg == before and len(engines) == 1


def _reader(cfg, answers, failures, finished):
    try:
        answers.append(transcription.loaded_model_token(cfg))
    except BaseException as exc:
        failures.append(exc)
    finally:
        finished.set()


def test_snapshot_does_not_wait_for_loading_or_inference_locks(engines):
    cfg = Config()
    transcription.load_model(cfg)
    answers, failures, finished = [], [], threading.Event()
    reader = threading.Thread(target=_reader, args=(cfg, answers, failures, finished), daemon=True)
    try:
        with transcription._lock, transcription._infer_lock:
            reader.start()
            assert finished.wait(2), "Snapshot waited behind a runtime lock"
    finally:
        reader.join(2)
    assert not reader.is_alive() and failures == []
    assert answers == ["small.en"]


def test_blocked_native_load_returns_unconfirmed_promptly(engines, monkeypatch):
    cfg = Config()
    entered, release, finished = threading.Event(), threading.Event(), threading.Event()
    answers, failures = [], []

    def blocked_load(*_args):
        entered.set()
        if not release.wait(5):
            raise TimeoutError("Synthetic load was not released")
        return object()

    def load():
        try:
            transcription.load_model(cfg)
        except BaseException as exc:
            failures.append(exc)

    monkeypatch.setattr(transcription, "_load_ctranslate", blocked_load)
    worker = threading.Thread(target=load, daemon=True)
    reader = threading.Thread(target=_reader, args=(cfg, answers, failures, finished), daemon=True)
    worker.start()
    try:
        assert entered.wait(2)
        assert transcription._lock.locked()
        with transcription._infer_lock:
            reader.start()
            assert finished.wait(2), "Snapshot waited for a native load"
        assert answers == [None] and worker.is_alive()
    finally:
        release.set()
        worker.join(2)
        if reader.ident is not None:
            reader.join(2)
    assert not worker.is_alive() and not reader.is_alive() and failures == []
    assert transcription.loaded_model_token(cfg) == "small.en"
