"""Pick a local accelerator. Prefer a working NVIDIA GPU, then NPU, then CPU."""

from __future__ import annotations

import logging
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from utterleaf.config import Config

log = logging.getLogger("utterleaf")

# OpenVINO IR repos that run on Intel NPU without a conversion step.
OV_MODELS = {
    "tiny": "OpenVINO/whisper-tiny-fp16-ov",
    "tiny.en": "OpenVINO/whisper-tiny.en-fp16-ov",
    "base": "OpenVINO/whisper-base-fp16-ov",
    "base.en": "OpenVINO/whisper-base.en-fp16-ov",
    "small": "OpenVINO/whisper-small-fp16-ov",
    "small.en": "OpenVINO/whisper-small.en-fp16-ov",
}

NPU_NAME_RE = re.compile(
    r"\bNPU\b|AI Boost|Neural Process|Ryzen AI|\bAMD IPU\b|Hexagon|Copilot\+",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Accelerator:
    kind: str  # npu | gpu | cpu
    name: str
    backend: str  # openvino | ctranslate2
    ready: bool


def openvino_available() -> bool:
    try:
        import openvino  # noqa: F401
        import openvino_genai  # noqa: F401
    except Exception:
        return False
    return True


def openvino_devices() -> list[str]:
    try:
        import openvino as ov

        return list(ov.Core().available_devices)
    except Exception:
        return []


def ov_model_id(name: str) -> str | None:
    return OV_MODELS.get(name)


_cuda_runtime: bool | None = None
_cuda_dirs_enabled = False

def mark_cuda_unusable() -> None:
    global _cuda_runtime
    _cuda_runtime = False


def nvidia_gpu_label() -> str:
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.total",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=4,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
    except Exception:
        return ""
    if result.returncode != 0 or not result.stdout.strip():
        return ""
    line = result.stdout.strip().splitlines()[0]
    parts = [part.strip() for part in line.split(",")]
    if len(parts) >= 2 and parts[1].isdigit():
        return f"{parts[0]} ({parts[1]} MiB)"
    return parts[0] if parts else ""


def _nvidia_pip_lib_dirs() -> list[Path]:
    dirs: list[Path] = []
    try:
        import importlib.util

        for mod in (
            "nvidia.cublas",
            "nvidia.cudnn",
            "nvidia.cuda_runtime",
            "nvidia.cuda_nvrtc",
        ):
            spec = importlib.util.find_spec(mod)
            if spec is None or not spec.submodule_search_locations:
                continue
            root = Path(next(iter(spec.submodule_search_locations)))
            for child in (root / "bin", root / "lib", root / "lib" / "x64"):
                if child.is_dir():
                    dirs.append(child)
            # Wheels sometimes put DLLs at the package root.
            if any(root.glob("cublas64_*.dll")) or any(root.glob("libcublas.so*")):
                dirs.append(root)
    except Exception:
        log.debug("NVIDIA pip package scan failed", exc_info=True)
    return dirs


def _toolkit_bin_dirs() -> list[Path]:
    dirs: list[Path] = []
    for key in ("CUDA_PATH", "CUDA_PATH_V12_9", "CUDA_PATH_V12_8", "CUDA_PATH_V12_6", "CUDA_PATH_V13_0"):
        raw = os.environ.get(key)
        if raw:
            bin_dir = Path(raw) / "bin"
            if bin_dir.is_dir():
                dirs.append(bin_dir)
    toolkit = Path(r"C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA")
    if toolkit.is_dir():
        for version in sorted(toolkit.iterdir(), reverse=True):
            bin_dir = version / "bin"
            if bin_dir.is_dir():
                dirs.append(bin_dir)
    return dirs


def _linux_toolkit_dirs() -> list[Path]:
    if not sys.platform.startswith("linux"):
        return []
    dirs: list[Path] = []
    for entry in sorted(Path("/usr/local").glob("cuda*/lib64")):
        if entry.is_dir():
            dirs.append(entry)
    return dirs


def cuda_library_dirs() -> list[Path]:
    found: list[Path] = []
    seen: set[str] = set()
    for item in _nvidia_pip_lib_dirs() + _toolkit_bin_dirs() + _linux_toolkit_dirs():
        key = str(item.resolve()) if item.exists() else str(item)
        if key not in seen:
            seen.add(key)
            found.append(item)
    return found


def enable_cuda_libs() -> list[Path]:
    """Put cublas/cudnn on PATH so CTranslate2 can load the NVIDIA GPU."""
    global _cuda_dirs_enabled, _cuda_runtime
    dirs = cuda_library_dirs()
    if not dirs:
        return []
    if not _cuda_dirs_enabled:
        prefix = os.pathsep.join(str(path) for path in dirs)
        os.environ["PATH"] = prefix + os.pathsep + os.environ.get("PATH", "")
        if hasattr(os, "add_dll_directory"):
            for path in dirs:
                try:
                    os.add_dll_directory(str(path))
                except OSError:
                    pass
        _cuda_dirs_enabled = True
        _cuda_runtime = None
        log.info("CUDA library dirs: %s", "; ".join(str(path) for path in dirs))
    return dirs


def _preload_linux_cuda() -> bool:
    """Linux dlopen ignores PATH, so the directories found above are useless
    until the sonames are resident. Load every NVIDIA .so by absolute path;
    a resident library satisfies CTranslate2's later dlopen by soname. The
    wheels' $ORIGIN rpath resolves each lib's own dependencies."""
    import ctypes

    loaded_cublas = False
    for directory in cuda_library_dirs():
        for path in sorted(directory.glob("lib*.so*")):
            try:
                ctypes.CDLL(str(path))
            except OSError:
                continue
            if path.name.startswith("libcublas.so"):
                loaded_cublas = True
                log.info("Loaded NVIDIA %s", path.name)
    return loaded_cublas


def _cublas_loadable() -> bool:
    enable_cuda_libs()
    import ctypes

    loader = ctypes.WinDLL if sys.platform == "win32" else ctypes.CDLL
    names = (
        ("cublas64_12.dll", "cublas64_13.dll", "cublas64_11.dll")
        if sys.platform == "win32"
        else ("libcublas.so.12", "libcublas.so.13", "libcublas.so.11")
    )
    for name in names:
        try:
            loader(name)
            log.info("Loaded NVIDIA %s", name)
            return True
        except OSError:
            continue
    if sys.platform == "win32":
        return False
    return _preload_linux_cuda()


def cuda_runtime_ok() -> bool:
    """GPU is usable only if CTranslate2 can load NVIDIA's math libraries."""
    global _cuda_runtime
    if _cuda_runtime is not None:
        return _cuda_runtime
    _cuda_runtime = _cublas_loadable()
    if not _cuda_runtime:
        log.info("NVIDIA GPU present but cublas is not loadable; install: pip install 'utterleaf[cuda]'")
    return _cuda_runtime


def _windows_npu_names() -> list[str]:
    if sys.platform != "win32":
        return []
    names: list[str] = []
    try:
        import subprocess

        result = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                "Get-CimInstance Win32_PnPEntity | "
                "Where-Object { $_.Name -match 'NPU|AI Boost|Neural Process|Ryzen AI|AMD IPU|Hexagon|Copilot\\+' } | "
                "Select-Object -ExpandProperty Name",
            ],
            capture_output=True,
            text=True,
            check=False,
            creationflags=subprocess.CREATE_NO_WINDOW,
            timeout=4,
        )
        for line in result.stdout.splitlines():
            line = line.strip()
            if line and NPU_NAME_RE.search(line):
                names.append(line)
    except Exception:
        log.debug("Windows NPU probe failed", exc_info=True)
    return names


def _linux_npu_names() -> list[str]:
    names: list[str] = []
    accel = Path("/sys/class/accel")
    if accel.exists():
        for child in accel.iterdir():
            names.append(f"accel:{child.name}")
    if Path("/dev/accel").exists() and not names:
        names.append("Linux accel device")
    return names


def probe() -> list[Accelerator]:
    found: list[Accelerator] = []
    ov_ready = openvino_available()
    ov_devs = openvino_devices() if ov_ready else []

    npu_names = []
    if "NPU" in ov_devs:
        npu_names.append("OpenVINO NPU")
    npu_names.extend(_windows_npu_names())
    npu_names.extend(_linux_npu_names())
    # de-dupe while keeping order
    seen: set[str] = set()
    unique_npu: list[str] = []
    for name in npu_names:
        if name not in seen:
            seen.add(name)
            unique_npu.append(name)
    if unique_npu:
        found.append(
            Accelerator(
                kind="npu",
                name=", ".join(unique_npu),
                backend="openvino",
                ready=ov_ready,
            )
        )

    enable_cuda_libs()
    cuda_count = 0
    try:
        from ctranslate2 import get_cuda_device_count

        cuda_count = int(get_cuda_device_count())
    except Exception:
        cuda_count = 0
    gpu_label = nvidia_gpu_label()
    if cuda_count > 0 or gpu_label:
        usable = cuda_count > 0 and cuda_runtime_ok()
        if gpu_label:
            label = gpu_label
        else:
            label = f"CUDA ({cuda_count} device{'s' if cuda_count != 1 else ''})"
        if cuda_count > 0 and not usable:
            label += ", cublas not found"
        elif cuda_count == 0 and gpu_label:
            label += ", CTranslate2 sees no CUDA device"
            usable = False
        found.append(
            Accelerator(kind="gpu", name=label, backend="ctranslate2", ready=usable)
        )

    ov_gpus = [dev for dev in ov_devs if dev == "GPU" or dev.startswith("GPU.")]
    if ov_gpus:
        found.append(
            Accelerator(
                kind="gpu",
                name=f"OpenVINO {', '.join(ov_gpus)}",
                backend="openvino",
                ready=ov_ready,
            )
        )

    found.append(Accelerator(kind="cpu", name="CPU", backend="ctranslate2", ready=True))
    return found


def pick(cfg: Config, accelerators: list[Accelerator] | None = None) -> Accelerator:
    """Working NVIDIA CUDA first, then NPU, then any other GPU, then CPU."""
    accels = list(accelerators if accelerators is not None else probe())
    wanted = cfg.device.strip().lower()
    if wanted == "cuda":
        wanted = "gpu"

    def first_ready(kind: str) -> Accelerator | None:
        for item in accels:
            if item.kind == kind and item.ready:
                if item.backend == "openvino" and ov_model_id(_model_key(cfg)) is None:
                    log.info(
                        "%s present but no OpenVINO build for model %s; using next device",
                        kind.upper(),
                        cfg.model,
                    )
                    return None
                return item
        return None

    if wanted != "auto":
        match = first_ready(wanted)
        if match is not None:
            return match
        log.warning("Requested device %s is not ready; falling back", wanted)

    # Working NVIDIA CUDA first — a 3090 beats an NPU for Whisper.
    for item in accels:
        if item.ready and item.kind == "gpu" and item.backend == "ctranslate2":
            return item
    for kind in ("npu", "gpu", "cpu"):
        match = first_ready(kind)
        if match is not None:
            return match
    return Accelerator(kind="cpu", name="CPU", backend="ctranslate2", ready=True)


def _model_key(cfg: Config) -> str:
    name = cfg.model.strip()
    if cfg.language.lower() in {"en", "english"} and name in {"tiny", "base", "small", "medium"}:
        return f"{name}.en"
    return name


def describe(accels: list[Accelerator], chosen: Accelerator) -> list[str]:
    lines = []
    for item in accels:
        if item.ready:
            status = "ready"
        elif item.kind == "gpu" and item.backend == "ctranslate2":
            status = "present, install CUDA libs: pip install 'utterleaf[cuda]'"
        else:
            status = "present, install extra to use (pip install 'utterleaf[npu]')"
        lines.append(f"  {item.kind}: {item.name} via {item.backend} ({status})")
    lines.append(f"picked: {chosen.kind} / {chosen.backend} ({chosen.name})")
    return lines


def generate_diagnostic_report(cfg: Config) -> str:
    """Create a detailed text report of available hardware and current setup."""
    accels = probe()
    chosen = pick(cfg, accels)
    
    lines = [
        "Utterleaf Hardware Diagnostic Report",
        "=================================",
        f"OS: {sys.platform}",
        f"Python: {sys.version.split()[0]}",
        f"Configured Device: {cfg.device}",
        f"Picked Accelerator: {chosen.kind} ({chosen.name}) via {chosen.backend}",
        "",
        "Available Accelerators:",
    ]
    lines.extend(describe(accels, chosen))
    
    lines.append("")
    lines.append("OpenVINO Status:")
    lines.append(f"  Available: {openvino_available()}")
    
    lines.append("")
    lines.append("CUDA Status:")
    lines.append(f"  Runtime OK: {cuda_runtime_ok()}")
    lines.append(f"  Library Dirs: {', '.join(map(str, cuda_library_dirs()))}")
    
    return "\n".join(lines)
