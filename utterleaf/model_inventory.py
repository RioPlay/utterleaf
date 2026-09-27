"""Bounded, read-only inventory of Utterleaf's guided model installations.

Sizes are logical bytes in recognized setup files, not download sizes, physical
disk usage, or reclaimable space. Shared caches and other files are excluded.
File presence never establishes that an engine has loaded a model successfully.
"""

from dataclasses import dataclass
from pathlib import Path
import stat

from utterleaf import models
from utterleaf.hardware import ov_model_id
from utterleaf.model_setup import CT2_REQUIRED, GUIDED_NAMES, OV_REQUIRED, inspect_model


@dataclass(frozen=True)
class ModelInstallation:
    name: str
    backend: str
    state: str
    size_bytes: int | None
    detail: str = ""


_NAME_ORDER = (
    "tiny", "tiny.en", "base", "base.en", "small", "small.en", "medium",
    "medium.en", "large-v3", "distil-small.en",
)
_CT2_FILES = (*CT2_REQUIRED, "vocabulary.txt", "vocabulary.json")
_CHANGED = "Setup files changed during this check. Refresh the inventory to check them again."


def _file_snapshot(folder: Path, filenames: tuple[str, ...]) -> tuple:
    """Stat only known names and check read access without reading weight data."""
    result = []
    for filename in filenames:
        path = folder / filename
        try:
            info = path.stat()
        except FileNotFoundError:
            result.append(None)
            continue
        if stat.S_ISREG(info.st_mode):
            # inspect_model checks JSON readability, but its binary-file check
            # needs only stat. Do not count inaccessible weights as known size.
            with path.open("rb"):
                pass
        result.append((info.st_dev, info.st_ino, info.st_mode, info.st_size,
                       info.st_mtime_ns, info.st_ctime_ns))
    return tuple(result)


def _installation(name: str, backend: str, folder: Path, filenames: tuple[str, ...]):
    try:
        initial_folder = folder.stat()
    except FileNotFoundError:
        return None
    except OSError as exc:
        return ModelInstallation(name, backend, "error", None, str(exc))
    if not stat.S_ISDIR(initial_folder.st_mode):
        return ModelInstallation(name, backend, "error", None,
                                 f"The expected model folder is not a directory: {folder}")
    try:
        before = _file_snapshot(folder, filenames)
        availability = inspect_model(name, backend)
        after = _file_snapshot(folder, filenames)
        final_folder = folder.stat()
    except OSError as exc:
        return ModelInstallation(name, backend, "error", None, str(exc))
    if (availability.state == "missing" or before != after
            or not stat.S_ISDIR(final_folder.st_mode)
            or (initial_folder.st_dev, initial_folder.st_ino)
            != (final_folder.st_dev, final_folder.st_ino)):
        return ModelInstallation(name, backend, "error", None, _CHANGED)
    if availability.state not in {"installed", "incomplete"}:
        raise ValueError("Unexpected state for a guided model installation")
    size = sum(info[3] for info in after if info is not None and stat.S_ISREG(info[2]))
    return ModelInstallation(name, backend, availability.state, size)


def inventory_models() -> tuple[ModelInstallation, ...]:
    """Inspect the fixed guided catalogue, never enumerate arbitrary store paths.

    Absent directories are omitted. A per-installation I/O error or detected
    change retains an error row with unknown size; unexpected failures propagate
    to the caller. Pre/post metadata checks are not a transactional file snapshot.
    """
    order = {name: index for index, name in enumerate(_NAME_ORDER)}
    result = []
    for name in sorted(GUIDED_NAMES, key=lambda value: (order.get(value, len(order)), value)):
        entry = _installation(name, "ctranslate2", models.ct2_dir(name), _CT2_FILES)
        if entry is not None:
            result.append(entry)
        repo = ov_model_id(name)
        if repo is not None:
            entry = _installation(name, "openvino", models.ov_dir(repo), OV_REQUIRED)
            if entry is not None:
                result.append(entry)
    return tuple(result)
