"""App-owned model cache. Download once if missing, then never touch the network."""

from __future__ import annotations

import logging
from pathlib import Path

from utterleaf.config import models_dir
from utterleaf.offline import stay_offline

log = logging.getLogger("utterleaf")


def hub_cache() -> Path:
    return models_dir() / "hub"


def ct2_dir(name: str) -> Path:
    return models_dir() / f"faster-whisper-{name}"


def ov_dir(repo: str) -> Path:
    return models_dir() / repo.replace("/", "--")


def ct2_ready(path: Path) -> bool:
    return (path / "model.bin").is_file() and (path / "config.json").is_file()


def ov_ready(path: Path) -> bool:
    if not path.is_dir():
        return False
    return any(path.rglob("*.xml"))


def ensure_ct2(name: str, *, allow_network: bool) -> Path:
    dest = ct2_dir(name)
    if ct2_ready(dest):
        stay_offline()
        return dest
    if not allow_network:
        raise RuntimeError(
            f"Model '{name}' is not in {dest}. Run: utterleaf --download-model"
        )
    dest.mkdir(parents=True, exist_ok=True)
    log.info("Downloading Whisper %s into %s (one-time)", name, dest)
    from faster_whisper.utils import download_model

    download_model(
        name,
        output_dir=str(dest),
        cache_dir=str(hub_cache()),
        local_files_only=False,
    )
    if not ct2_ready(dest):
        raise RuntimeError(f"Download finished but {dest} is missing model.bin")
    stay_offline()
    return dest


def ensure_ov(repo: str, *, allow_network: bool) -> Path:
    dest = ov_dir(repo)
    if ov_ready(dest):
        stay_offline()
        return dest
    if not allow_network:
        raise RuntimeError(
            f"OpenVINO model '{repo}' is not in {dest}. Run: utterleaf --download-model"
        )
    dest.mkdir(parents=True, exist_ok=True)
    log.info("Downloading OpenVINO %s into %s (one-time)", repo, dest)
    from huggingface_hub import snapshot_download

    snapshot_download(
        repo,
        local_dir=str(dest),
        cache_dir=str(hub_cache()),
        local_files_only=False,
        token=False,
    )
    if not ov_ready(dest):
        raise RuntimeError(f"Download finished but {dest} has no OpenVINO IR (.xml)")
    stay_offline()
    return dest


def status_lines(name: str, ov_repo: str | None) -> list[str]:
    lines = [f"model cache: {models_dir()}"]
    ct2 = ct2_dir(name)
    lines.append(
        f"  {ct2.name}: {'ready' if ct2_ready(ct2) else 'missing (download on first use)'}"
    )
    if ov_repo:
        ov = ov_dir(ov_repo)
        lines.append(
            f"  {ov.name}: {'ready' if ov_ready(ov) else 'missing (download if NPU/Intel GPU is used)'}"
        )
    return lines
