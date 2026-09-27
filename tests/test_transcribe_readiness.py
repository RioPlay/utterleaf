"""Model readiness checks use fake backends, without devices or model files."""

from dataclasses import replace
import threading

import pytest

from utterleaf import transcribe as transcription
from utterleaf.config import Config
from utterleaf.hardware import Accelerator


GPU = Accelerator("gpu", "Fake GPU", "ctranslate2", True)
NPU = Accelerator("npu", "Fake NPU", "openvino", True)


@pytest.fixture
def engines(monkeypatch):
    monkeypatch.setattr(transcription, "_engine", None)
    monkeypatch.setattr(transcription, "_engine_key", None)
    monkeypatch.setattr(transcription, "_engine_config_key", None)
    monkeypatch.setattr(transcription, "pick", lambda cfg: transcription.CPU)
    loaded = []

    def load(cfg, accelerator):
        engine = object()
        loaded.append((replace(cfg), accelerator, engine))
        return engine

    monkeypatch.setattr(transcription, "_load_ctranslate", load)
    monkeypatch.setattr(transcription, "_load_openvino", load)
    monkeypatch.setattr(transcription, "mark_cuda_unusable", lambda: None)
    return loaded


def test_only_a_successful_load_establishes_readiness(engines):
    cfg = Config(model="small", language="en", allow_network=False)
    assert not transcription.engine_ready(cfg)

    loaded = transcription.load_model(cfg)

    assert transcription.engine_ready(cfg)
    assert transcription._engine_key == ("small.en", "cpu", "ctranslate2")
    assert engines == [(cfg, transcription.CPU, loaded)]
    assert not engines[0][0].allow_network


@pytest.mark.parametrize("change", [
    {"model": "base"},
    {"device": "gpu"},
    {"compute_type": "float16"},
    {"language": "fr"},
])
@pytest.mark.parametrize("explicit_accelerator", [False, True])
def test_changed_model_preferences_cannot_reuse_an_old_engine(
    engines, change, explicit_accelerator,
):
    cfg = Config(model="large-v3", device="cpu", language="en")
    accelerator = transcription.CPU if explicit_accelerator else None
    first = transcription.load_model(cfg, accelerator)
    changed = replace(cfg, **change)

    assert not transcription.engine_ready(changed)
    second = transcription.load_model(changed, accelerator)

    assert second is not first
    assert len(engines) == 2
    assert transcription.engine_ready(changed)
    assert not transcription.engine_ready(cfg)


def test_non_model_preferences_preserve_cache_and_readiness(engines, monkeypatch):
    cfg = Config()
    first = transcription.load_model(cfg)
    changed = replace(cfg, microphone="Other input", beep=False, allow_network=False)
    monkeypatch.setattr(transcription, "pick", lambda cfg: pytest.fail("cached model probed hardware"))

    assert transcription.engine_ready(changed)
    assert transcription.load_model(changed) is first
    assert len(engines) == 1


def test_explicit_backend_change_loads_again(engines):
    cfg = Config(device="auto")
    first = transcription.load_model(cfg, transcription.CPU)

    second = transcription.load_model(cfg, NPU)

    assert second is not first
    assert transcription.engine_ready(cfg)
    assert transcription._engine_key == ("small.en", "npu", "openvino")


def test_cpu_fallback_remembers_requested_preferences(engines, monkeypatch):
    cfg = Config(device="gpu", compute_type="int8")
    actual_load = transcription._load_ctranslate

    def load(config, accelerator):
        if accelerator.kind == "gpu":
            assert not transcription.engine_ready(config)
            raise RuntimeError("fake GPU unavailable")
        return actual_load(config, accelerator)

    monkeypatch.setattr(transcription, "pick", lambda cfg: GPU)
    monkeypatch.setattr(transcription, "_load_ctranslate", load)
    first = transcription.load_model(cfg)
    monkeypatch.setattr(transcription, "pick", lambda cfg: pytest.fail("fallback cache reprobed hardware"))

    assert transcription.engine_ready(cfg)
    assert transcription._engine_key == ("small.en", "cpu", "ctranslate2")
    assert transcription.load_model(cfg) is first
    assert transcription.load_model(cfg, transcription.CPU) is first
    assert len(engines) == 1


@pytest.mark.parametrize("failure", ["pick", "cpu", "fallback"])
def test_failed_replacement_clears_prior_readiness(engines, monkeypatch, failure):
    original = Config(device="cpu")
    transcription.load_model(original)
    changed = replace(original, model="base")

    def fail(*args):
        assert not transcription.engine_ready(original)
        assert not transcription.engine_ready(changed)
        raise RuntimeError("fake loading failure")

    if failure == "pick":
        monkeypatch.setattr(transcription, "pick", fail)
    else:
        monkeypatch.setattr(transcription, "pick", lambda cfg: GPU if failure == "fallback" else transcription.CPU)
        monkeypatch.setattr(transcription, "_load_ctranslate", fail)

    with pytest.raises(RuntimeError, match="fake loading failure"):
        transcription.load_model(changed)

    assert not transcription.engine_ready(original)
    assert not transcription.engine_ready(changed)


def test_reset_removes_successful_load_proof(engines):
    cfg = Config()
    transcription.load_model(cfg)

    transcription.reset_engine()

    assert not transcription.engine_ready(cfg)
    assert transcription._engine is None
    assert transcription._engine_key is None


def test_readiness_does_not_wait_for_native_load_or_inference(engines, monkeypatch):
    cfg = Config()
    entered = threading.Event()
    release = threading.Event()
    errors = []

    def load(config, accelerator):
        entered.set()
        if not release.wait(2):
            raise TimeoutError("test did not release fake load")
        return object()

    def work():
        try:
            transcription.load_model(cfg)
        except BaseException as exc:
            errors.append(exc)

    monkeypatch.setattr(transcription, "_load_ctranslate", load)
    worker = threading.Thread(target=work)
    worker.start()
    try:
        assert entered.wait(2)
        assert transcription._lock.locked()
        with transcription._infer_lock:
            assert not transcription.engine_ready(cfg)
        assert worker.is_alive()
    finally:
        release.set()
        worker.join(2)
    assert not worker.is_alive()
    assert errors == []
    checked = threading.Event()
    answers = []

    def read():
        answers.append(transcription.engine_ready(cfg))
        checked.set()

    reader = threading.Thread(target=read)
    try:
        with transcription._lock, transcription._infer_lock:
            reader.start()
            assert checked.wait(1), "readiness waited behind a runtime lock"
    finally:
        reader.join(2)
    assert not reader.is_alive()
    assert answers == [True]


def test_old_config_loading_replaces_current_readiness(engines):
    original = Config(model="small")
    current = replace(original, model="base")
    transcription.load_model(current)
    assert transcription.engine_ready(current)

    transcription.load_model(original)

    assert not transcription.engine_ready(current)
    assert transcription.engine_ready(original)


def test_load_captures_preferences_before_backend_work(engines, monkeypatch):
    cfg = Config(model="small")
    original = replace(cfg)

    def load(config, accelerator):
        cfg.model = "base"
        assert config.model == "small"
        return object()

    monkeypatch.setattr(transcription, "_load_ctranslate", load)

    transcription.load_model(cfg)

    assert transcription.engine_ready(original)
    assert not transcription.engine_ready(cfg)
