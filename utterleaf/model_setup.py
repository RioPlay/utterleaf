"""Local model availability and explicitly authorized, isolated model downloads."""

from dataclasses import dataclass
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from utterleaf.config import Config
from utterleaf import models
from utterleaf.hardware import ov_model_id

GUIDED_NAMES = frozenset({"tiny", "tiny.en", "base", "base.en", "small", "small.en", "medium",
                          "medium.en", "large-v3", "distil-small.en"})
CT2_REQUIRED = ("model.bin", "config.json", "tokenizer.json")
OV_REQUIRED = ("config.json", "generation_config.json", "openvino_encoder_model.xml",
               "openvino_encoder_model.bin", "openvino_decoder_model.xml", "openvino_decoder_model.bin",
               "openvino_tokenizer.xml", "openvino_tokenizer.bin", "openvino_detokenizer.xml", "openvino_detokenizer.bin")


@dataclass(frozen=True)
class ModelAvailability:
    name: str
    backend: str
    state: str
    path: Path | None
    missing: tuple[str, ...] = ()


def model_name(cfg: Config) -> str:
    name = cfg.model.strip()
    if cfg.language.lower() in {"en", "english"} and name in {"tiny", "base", "small", "medium"}:
        return name + ".en"
    return name


def _usable(path: Path) -> bool:
    try:
        if not path.is_file() or path.stat().st_size == 0:
            return False
        if path.suffix == ".json":
            with path.open("rb") as stream:
                data = stream.read(8 * 1024 * 1024 + 1)
            allowed = (dict, list) if path.name == "vocabulary.json" else (dict,)
            if len(data) > 8 * 1024 * 1024 or not isinstance(json.loads(data), allowed):
                return False
        return True
    except (OSError, ValueError, RecursionError):
        return False


def inspect_model(name: str, backend: str = "ctranslate2") -> ModelAvailability:
    """Check required local files only; never initializes an engine or uses network."""
    if name not in GUIDED_NAMES or backend not in {"ctranslate2", "openvino"}:
        return ModelAvailability(name, backend, "unsupported", None)
    if backend == "openvino":
        repo = ov_model_id(name)
        if repo is None:
            return ModelAvailability(name, backend, "unsupported", None)
        path, required = models.ov_dir(repo), OV_REQUIRED
    else:
        path, required = models.ct2_dir(name), CT2_REQUIRED
    missing = [filename for filename in required if not _usable(path / filename)]
    if backend == "ctranslate2" and not any(_usable(path / name) for name in ("vocabulary.txt", "vocabulary.json")):
        missing.append("vocabulary.*")
    state = "installed" if not missing else "incomplete" if path.exists() else "missing"
    return ModelAvailability(name, backend, state, path, tuple(missing))


def download_selected(name: str, backend: str) -> int:
    """Child-process entry. Download only absent/invalid required files, never configs."""
    status = inspect_model(name, backend)
    if status.state == "unsupported":
        return 2
    from filelock import FileLock, Timeout
    from utterleaf.offline import apply_offline_defaults

    apply_offline_defaults()
    status.path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with FileLock(str(status.path) + ".setup.lock", timeout=0):
            status = inspect_model(name, backend)
            if status.state == "installed":
                return 0
            from huggingface_hub import snapshot_download
            repo = (ov_model_id(name) if backend == "openvino" else
                    "Systran/faster-distil-whisper-small.en" if name == "distil-small.en" else
                    f"Systran/faster-whisper-{name}")
            snapshot_download(repo, local_dir=str(status.path), cache_dir=str(models.hub_cache()),
                              allow_patterns=list(status.missing), local_files_only=False,
                              force_download=True, token=False)
            return 0 if inspect_model(name, backend).state == "installed" else 1
    except Timeout:
        return 3
    except Exception:
        # Subprocess stdout/stderr are discarded; keep messages independent of URLs/tokens.
        return 1


def run_download(name: str, backend: str, *, cancel=None) -> None:
    """A child receives one-time network permission; parent environment is unchanged."""
    if inspect_model(name, backend).state == "unsupported":
        raise ValueError("Choose a listed model for guided installation")
    if cancel is not None and cancel.is_set():
        raise RuntimeError("Download cancelled. Any partial files are kept for retry.")
    executable = Path(sys.executable)
    if getattr(sys, "frozen", False):
        if sys.platform == "win32" and executable.with_name("utterleaf-cli.exe").exists():
            executable = executable.with_name("utterleaf-cli.exe")
        command = [str(executable)]
    else:
        command = [str(executable), "-m", "utterleaf"]
    command += ["--model-setup-download", name, "--model-setup-backend", backend]
    environment = os.environ.copy()
    for key in ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE"):
        environment.pop(key, None)
    environment.update(HF_HUB_DISABLE_TELEMETRY="1", HF_HUB_DISABLE_IMPLICIT_TOKEN="1", DO_NOT_TRACK="1")
    process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, shell=False, env=environment,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0)
    deadline = time.monotonic() + 1800
    try:
        while process.poll() is None:
            if cancel is not None and cancel.is_set():
                raise RuntimeError("Download cancelled. Any partial files are kept for retry.")
            if time.monotonic() >= deadline:
                raise RuntimeError("Download timed out. Check your connection and retry.")
            try:
                process.wait(timeout=0.1)
            except subprocess.TimeoutExpired:
                pass
        if process.returncode == 3:
            raise RuntimeError("This model is already downloading in another window. Refresh its status shortly.")
        if process.returncode:
            raise RuntimeError("Model download did not finish. Check your connection and free disk space, then retry.")
    finally:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=5)
