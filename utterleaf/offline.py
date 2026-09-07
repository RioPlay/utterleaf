"""Keep Utterleaf off the network except a one-time model fetch."""

from __future__ import annotations

import os


def apply_offline_defaults() -> None:
    """Disable Hub telemetry. Never phone home."""
    os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
    os.environ.setdefault("HF_HUB_DISABLE_IMPLICIT_TOKEN", "1")
    os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
    os.environ.setdefault("DO_NOT_TRACK", "1")


def stay_offline() -> None:
    """After weights are on disk, refuse Hub access for the rest of the process."""
    apply_offline_defaults()
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
