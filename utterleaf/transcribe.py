"""Local speech-to-text. Small on-device model; NPU or GPU if the machine has one."""

from __future__ import annotations

import logging
import threading
from pathlib import Path

import numpy as np

from utterleaf.clean import prepare
from utterleaf.config import Config
from utterleaf.hardware import (
    Accelerator,
    enable_cuda_libs,
    mark_cuda_unusable,
    openvino_available,
    ov_model_id,
    pick,
)

CPU = Accelerator("cpu", "CPU", "ctranslate2", True)
from utterleaf.models import ensure_ct2, ensure_ov

log = logging.getLogger("utterleaf")

_engine = None
_engine_key: tuple | None = None
_lock = threading.Lock()
_infer_lock = threading.Lock()
# Set while a real paste decode is in flight so the live draft does not start another infer.
_final_requested = threading.Event()

EN_ONLY = {"tiny", "base", "small", "medium"}
# Drafts only the tail so a long hold cannot occupy the GPU when the user releases.
PREVIEW_SECONDS = 4.0


def _dictionary_prompt() -> str:
    try:
        from utterleaf.polish import load_vocabulary

        names = [written for _spoken, written in load_vocabulary()[:40]]
    except Exception:
        return ""
    return ", ".join(names)


def resolve_name(cfg: Config) -> str:
    name = cfg.model.strip()
    if cfg.language.lower() in {"en", "english"} and name in EN_ONLY:
        return f"{name}.en"
    return name


class CTranslateEngine:
    def __init__(self, model) -> None:
        self.model = model

    def transcribe(self, audio: np.ndarray, cfg: Config) -> str:
        language = None if cfg.language.lower() in {"auto", ""} else cfg.language
        seconds = float(len(audio)) / 16000.0
        prompt = _dictionary_prompt()
        kwargs = {
            "language": language,
            "vad_filter": seconds >= 1.4,
            "beam_size": 5,
            "condition_on_previous_text": False,
        }
        if prompt:
            kwargs["initial_prompt"] = prompt
        with _infer_lock:
            segments, _info = self.model.transcribe(audio, **kwargs)
            parts = [segment.text for segment in segments]
        return " ".join(part.strip() for part in parts if part and part.strip()).strip()


def request_final() -> None:
    """Stop new live drafts; a release or paste decode is about to need the engine."""
    _final_requested.set()


def clear_final() -> None:
    _final_requested.clear()


def peek_engine():
    """Cached engine, or None. Preview uses this so a draft never calls pick() or loads."""
    with _lock:
        return _engine


def transcribe_preview(audio: np.ndarray, cfg: Config) -> str:
    """Fast draft for the pill. Never waits on, or starts, a final decode."""
    if _final_requested.is_set():
        return ""
    if audio.size < int(16000 * 0.6):
        return ""
    limit = int(PREVIEW_SECONDS * 16000)
    if audio.size > limit:
        audio = audio[-limit:]
    engine = peek_engine()
    if not isinstance(engine, CTranslateEngine):
        return ""
    language = None if cfg.language.lower() in {"auto", ""} else cfg.language
    if not _infer_lock.acquire(blocking=False):
        return ""
    try:
        if _final_requested.is_set():
            return ""
        segments, _info = engine.model.transcribe(
            audio,
            language=language,
            vad_filter=False,
            beam_size=1,
            condition_on_previous_text=False,
        )
        parts = [segment.text for segment in segments]
    finally:
        _infer_lock.release()
    return " ".join(part.strip() for part in parts if part and part.strip()).strip()


class OpenVinoEngine:
    def __init__(self, pipe) -> None:
        self.pipe = pipe

    def transcribe(self, audio: np.ndarray, cfg: Config) -> str:
        kwargs: dict = {}
        if cfg.language.lower() not in {"auto", ""}:
            kwargs["language"] = cfg.language
        result = self.pipe.generate(np.ascontiguousarray(audio, dtype=np.float32), **kwargs)
        if isinstance(result, str):
            return result.strip()
        texts = getattr(result, "texts", None)
        if texts:
            return " ".join(str(part).strip() for part in texts if str(part).strip())
        return str(result).strip()


def _ct2_device(accel: Accelerator, cfg: Config) -> tuple[str, str]:
    device = "cuda" if accel.kind == "gpu" else "cpu"
    compute = cfg.compute_type
    if compute == "auto":
        compute = "float16" if device == "cuda" else "int8"
    return device, compute


def _ov_device(accel: Accelerator) -> str:
    return "NPU" if accel.kind == "npu" else "GPU"


def _load_openvino(cfg: Config, accel: Accelerator):
    import openvino_genai as ov_genai

    name = resolve_name(cfg)
    repo = ov_model_id(name)
    if repo is None:
        raise RuntimeError(f"no OpenVINO model for {name}")
    path = ensure_ov(repo, allow_network=cfg.allow_network)
    ov_device = _ov_device(accel)
    log.info("Loading OpenVINO %s on %s from %s", name, ov_device, path)
    return OpenVinoEngine(ov_genai.WhisperPipeline(str(path), ov_device))


def _load_ctranslate(cfg: Config, accel: Accelerator):
    from faster_whisper import WhisperModel

    if accel.kind == "gpu":
        enable_cuda_libs()
    name = resolve_name(cfg)
    path = ensure_ct2(name, allow_network=cfg.allow_network)
    device, compute = _ct2_device(accel, cfg)
    log.info("Loading Whisper %s on %s/%s from %s", name, device, compute, path)
    return CTranslateEngine(
        WhisperModel(str(path), device=device, compute_type=compute, local_files_only=True)
    )


def download_weights(cfg: Config) -> list[Path]:
    """Fetch any missing weights into the app model folder. Only network use."""
    name = resolve_name(cfg)
    saved = [ensure_ct2(name, allow_network=True)]
    repo = ov_model_id(name)
    if repo is not None and openvino_available():
        saved.append(ensure_ov(repo, allow_network=True))
    return saved


def reset_engine() -> None:
    global _engine, _engine_key
    with _lock:
        _engine = None
        _engine_key = None


def _reset_engine() -> None:
    reset_engine()


def _cuda_runtime_error(exc: BaseException) -> bool:
    text = str(exc).lower()
    return any(token in text for token in ("cublas", "cudnn", "cuda", "nvrtc"))


def load_model(cfg: Config, accel: Accelerator | None = None):
    """Load (or reuse) the local engine. Downloads once if the cache is empty."""
    global _engine, _engine_key
    name = resolve_name(cfg)
    with _lock:
        if (
            accel is None
            and _engine is not None
            and _engine_key is not None
            and _engine_key[0] == name
        ):
            return _engine
        chosen = accel or pick(cfg)
        key = (name, chosen.kind, chosen.backend)
        if _engine is not None and _engine_key == key:
            return _engine
        try:
            if chosen.backend == "openvino":
                _engine = _load_openvino(cfg, chosen)
            else:
                _engine = _load_ctranslate(cfg, chosen)
        except Exception:
            if chosen.kind == "cpu":
                raise
            log.exception("Accelerator load failed; falling back to CPU")
            if chosen.kind == "gpu" and chosen.backend == "ctranslate2":
                mark_cuda_unusable()
            chosen = CPU
            _engine = _load_ctranslate(cfg, chosen)
        _engine_key = (name, chosen.kind, chosen.backend)
        return _engine


def transcribe(audio: np.ndarray, cfg: Config) -> str:
    if audio.size == 0:
        return ""
    request_final()
    try:
        audio = prepare(audio, mode=getattr(cfg, "denoise", "auto"))
        try:
            return load_model(cfg).transcribe(audio, cfg)
        except RuntimeError as exc:
            if not _cuda_runtime_error(exc):
                raise
            log.warning("GPU failed (%s); retrying on CPU", exc)
            mark_cuda_unusable()
            _reset_engine()
            return load_model(cfg, CPU).transcribe(audio, cfg)
    finally:
        clear_final()
