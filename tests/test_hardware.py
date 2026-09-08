from utterleaf.config import Config
from utterleaf.hardware import Accelerator, cuda_runtime_ok, mark_cuda_unusable, ov_model_id, pick
import subprocess
from types import SimpleNamespace


def test_windows_hardware_helpers_never_create_console_windows(monkeypatch):
    from utterleaf import hardware
    monkeypatch.setattr(hardware.sys, "platform", "win32")
    flag = 0x08000000
    monkeypatch.setattr(subprocess, "CREATE_NO_WINDOW", flag, raising=False)
    calls = []
    def run(command, **kwargs):
        calls.append((command, kwargs))
        return SimpleNamespace(returncode=0, stdout="Intel AI Boost\n" if command[0] == "powershell"
                               else "NVIDIA GeForce RTX 3090, 24576\n")
    monkeypatch.setattr(hardware.subprocess, "run", run)
    assert "RTX 3090" in hardware.nvidia_gpu_label()
    assert hardware._windows_npu_names() == ["Intel AI Boost"]
    assert len(calls) == 2
    for command, kwargs in calls:
        assert kwargs["creationflags"] & flag
        assert kwargs["timeout"] == 4
        assert not kwargs.get("shell")
    assert "-NonInteractive" in calls[1][0]


def test_posix_gpu_helper_does_not_use_windows_creation_flags(monkeypatch):
    from utterleaf import hardware
    monkeypatch.setattr(hardware.sys, "platform", "linux")
    def run(command, **kwargs):
        assert kwargs["creationflags"] == 0
        return SimpleNamespace(returncode=0, stdout="GPU, 1000")
    monkeypatch.setattr(hardware.subprocess, "run", run)
    assert hardware.nvidia_gpu_label() == "GPU (1000 MiB)"


def test_auto_prefers_ready_nvidia_over_npu() -> None:
    accels = [
        Accelerator("npu", "Intel AI Boost", "openvino", True),
        Accelerator("gpu", "NVIDIA GeForce RTX 3090", "ctranslate2", True),
        Accelerator("cpu", "CPU", "ctranslate2", True),
    ]
    chosen = pick(Config(model="tiny", language="en"), accels)
    assert chosen.kind == "gpu"
    assert chosen.backend == "ctranslate2"


def test_npu_without_backend_falls_to_gpu() -> None:
    accels = [
        Accelerator("npu", "Intel AI Boost", "openvino", False),
        Accelerator("gpu", "CUDA (1 device)", "ctranslate2", True),
        Accelerator("cpu", "CPU", "ctranslate2", True),
    ]
    chosen = pick(Config(), accels)
    assert chosen.kind == "gpu"


def test_gpu_preferred_over_cpu() -> None:
    accels = [
        Accelerator("gpu", "CUDA (1 device)", "ctranslate2", True),
        Accelerator("cpu", "CPU", "ctranslate2", True),
    ]
    chosen = pick(Config(), accels)
    assert chosen.kind == "gpu"


def test_no_accelerator_uses_cpu() -> None:
    accels = [Accelerator("cpu", "CPU", "ctranslate2", True)]
    chosen = pick(Config(), accels)
    assert chosen.kind == "cpu"
    assert chosen.backend == "ctranslate2"


def test_explicit_cpu_skips_npu() -> None:
    accels = [
        Accelerator("npu", "Intel AI Boost", "openvino", True),
        Accelerator("cpu", "CPU", "ctranslate2", True),
    ]
    chosen = pick(Config(device="cpu", model="tiny"), accels)
    assert chosen.kind == "cpu"


def test_cuda_alias_selects_gpu() -> None:
    accels = [
        Accelerator("gpu", "CUDA (1 device)", "ctranslate2", True),
        Accelerator("cpu", "CPU", "ctranslate2", True),
    ]
    chosen = pick(Config(device="cuda"), accels)
    assert chosen.kind == "gpu"


def test_npu_skips_unknown_model() -> None:
    accels = [
        Accelerator("npu", "Intel AI Boost", "openvino", True),
        Accelerator("cpu", "CPU", "ctranslate2", True),
    ]
    chosen = pick(Config(model="large-v3", language="en"), accels)
    assert chosen.kind == "cpu"


def test_missing_cublas_marks_cuda_not_ready() -> None:
    import utterleaf.hardware as hardware

    hardware._cuda_runtime = None
    mark_cuda_unusable()
    assert cuda_runtime_ok() is False
    hardware._cuda_runtime = None


def test_linux_cuda_preload_loads_sonames_from_discovered_dirs(monkeypatch, tmp_path):
    import ctypes
    from utterleaf import hardware

    (tmp_path / "libcublas.so.12").write_bytes(b"")
    (tmp_path / "libcudnn.so.9").write_bytes(b"")
    (tmp_path / "libbroken.so.9").write_bytes(b"")
    calls = []

    def fake_cdll(path):
        calls.append(path)
        if "broken" in path:
            raise OSError("unresolved dependency")

    monkeypatch.setattr(ctypes, "CDLL", fake_cdll)
    monkeypatch.setattr(hardware, "cuda_library_dirs", lambda: [tmp_path])
    assert hardware._preload_linux_cuda() is True
    assert str(tmp_path / "libcublas.so.12") in calls
    assert str(tmp_path / "libcudnn.so.9") in calls
    assert str(tmp_path / "libbroken.so.9") in calls


def test_linux_cuda_preload_reports_false_without_libs(monkeypatch):
    import ctypes
    from utterleaf import hardware

    monkeypatch.setattr(ctypes, "CDLL", lambda _path: None)
    monkeypatch.setattr(hardware, "cuda_library_dirs", lambda: [])
    assert hardware._preload_linux_cuda() is False


def test_cuda_without_runtime_is_skipped() -> None:
    accels = [
        Accelerator("gpu", "CUDA (1 device), cublas not found", "ctranslate2", False),
        Accelerator("cpu", "CPU", "ctranslate2", True),
    ]
    chosen = pick(Config(), accels)
    assert chosen.kind == "cpu"


def test_ov_model_ids_for_lightweight() -> None:
    assert ov_model_id("tiny") == "OpenVINO/whisper-tiny-fp16-ov"
    assert ov_model_id("base.en") == "OpenVINO/whisper-base.en-fp16-ov"
    assert ov_model_id("large-v3") is None
