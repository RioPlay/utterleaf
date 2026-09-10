import os
from pathlib import Path
import subprocess
import sys
import threading

import pytest

from utterleaf import model_setup as setup
from utterleaf.config import Config


@pytest.fixture
def cache(tmp_path, monkeypatch):
    monkeypatch.setattr("utterleaf.models.models_dir", lambda: tmp_path)
    return tmp_path


def install_files(path):
    path.mkdir(parents=True, exist_ok=True)
    for name, data in (("model.bin", b"weights"), ("config.json", b"{}"),
                       ("tokenizer.json", b"{}"), ("vocabulary.txt", b"words")):
        (path / name).write_bytes(data)


def test_missing_partial_and_installed_are_local_only(cache, monkeypatch):
    monkeypatch.setattr("huggingface_hub.snapshot_download", lambda *a, **k: pytest.fail("A status check must not download"))
    status = setup.inspect_model("tiny.en")
    assert status.state == "missing"
    status.path.mkdir()
    (status.path / "model.bin").write_bytes(b"weights")
    (status.path / "config.json").write_text("{}")
    assert setup.inspect_model("tiny.en").state == "incomplete"
    install_files(status.path)
    assert setup.inspect_model("tiny.en").state == "installed"
    (status.path / "tokenizer.json").write_text("broken JSON")
    assert setup.inspect_model("tiny.en").state == "incomplete"
    assert not (cache / "config.toml").exists()


def test_model_language_resolution_and_custom_path_rejection(cache):
    assert setup.model_name(Config(model="small", language="en")) == "small.en"
    assert setup.model_name(Config(model="small", language="auto")) == "small"
    assert setup.inspect_model("../../outside").state == "unsupported"
    assert setup.download_selected("../../outside", "ctranslate2") == 2
    assert list(cache.iterdir()) == []


def test_download_repairs_only_missing_files_without_changing_existing_weights(cache, monkeypatch):
    status = setup.inspect_model("tiny.en")
    install_files(status.path)
    (status.path / "tokenizer.json").unlink()
    calls = []
    def download(repo, **kwargs):
        calls.append((repo, kwargs))
        (status.path / "tokenizer.json").write_text("{}")
    monkeypatch.setattr("huggingface_hub.snapshot_download", download)
    assert setup.download_selected("tiny.en", "ctranslate2") == 0
    assert (status.path / "model.bin").read_bytes() == b"weights"
    assert calls[0][1]["allow_patterns"] == ["tokenizer.json"]
    assert calls[0][1]["token"] is False
    assert calls[0][1]["local_files_only"] is False


def test_installed_model_does_not_download_again(cache, monkeypatch):
    install_files(setup.inspect_model("tiny.en").path)
    monkeypatch.setattr("huggingface_hub.snapshot_download", lambda *a, **k: pytest.fail("Installed weights must stay unchanged"))
    assert setup.download_selected("tiny.en", "ctranslate2") == 0


def test_one_time_download_does_not_change_parent_offline_environment_or_config(cache, monkeypatch):
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    monkeypatch.setenv("TRANSFORMERS_OFFLINE", "1")
    cfg = Config(allow_network=False, restore_clipboard=False)
    before = cfg.__dict__.copy()
    calls = []
    class Child:
        returncode = 0
        def poll(self): return 0
        def wait(self, **kw): return 0
    def launch(command, **kwargs):
        calls.append((command, kwargs))
        return Child()
    monkeypatch.setattr(setup.subprocess, "Popen", launch)
    setup.run_download("tiny.en", "ctranslate2")
    childenv = calls[0][1]["env"]
    assert "HF_HUB_OFFLINE" not in childenv
    assert "TRANSFORMERS_OFFLINE" not in childenv
    assert childenv["HF_HUB_DISABLE_IMPLICIT_TOKEN"] == "1"
    assert os.environ["HF_HUB_OFFLINE"] == "1"
    assert os.environ["TRANSFORMERS_OFFLINE"] == "1"
    assert cfg.__dict__ == before
    assert calls[0][1]["shell"] is False
    assert calls[0][1]["stdout"] == setup.subprocess.DEVNULL
    assert calls[0][1]["stderr"] == setup.subprocess.DEVNULL


def test_cancel_before_download_never_starts_child(cache, monkeypatch):
    cancel = threading.Event(); cancel.set()
    monkeypatch.setattr(setup.subprocess, "Popen", lambda *a, **k: pytest.fail("Cancelled download must not start"))
    with pytest.raises(RuntimeError, match="cancelled"):
        setup.run_download("tiny.en", "ctranslate2", cancel=cancel)


def test_cancel_running_download_kills_and_reaps_child(cache, monkeypatch):
    cancel = threading.Event()
    class Child:
        killed = False
        reaped = False
        returncode = None
        def poll(self):
            cancel.set()
            return self.returncode
        def kill(self):
            self.killed = True
            self.returncode = -9
        def wait(self, **kwargs):
            self.reaped = True
            return self.returncode
    child = Child()
    monkeypatch.setattr(setup.subprocess, "Popen", lambda *a, **k: child)
    with pytest.raises(RuntimeError, match="cancelled"):
        setup.run_download("tiny.en", "ctranslate2", cancel=cancel)
    assert child.killed and child.reaped


def test_concurrent_repair_does_not_enter_downloader(cache, monkeypatch):
    from filelock import FileLock
    path = setup.inspect_model("tiny.en").path
    monkeypatch.setattr("huggingface_hub.snapshot_download", lambda *a, **k: pytest.fail("Concurrent repair must not start"))
    with FileLock(str(path) + ".setup.lock"):
        assert setup.download_selected("tiny.en", "ctranslate2") == 3


def test_separate_npu_files_are_not_mistaken_for_cpu_model(cache):
    state = setup.inspect_model("tiny.en", "openvino")
    state.path.mkdir()
    (state.path / "openvino_encoder_model.xml").write_text("<net/>")
    assert setup.inspect_model("tiny.en", "openvino").state == "incomplete"
    assert setup.inspect_model("tiny.en").state == "missing"


def test_setup_cli_rejects_other_actions_before_side_effects(monkeypatch):
    from utterleaf.__main__ import main
    monkeypatch.setattr(setup, "download_selected", lambda *a: pytest.fail("Conflicting actions must not download"))
    with pytest.raises(SystemExit) as exc:
        main(["--model-setup-download", "tiny.en", "--model-setup-backend", "ctranslate2", "--offline"])
    assert exc.value.code == 2


def test_setup_cli_child_returns_for_installed_model_without_app_startup(tmp_path):
    environment = os.environ.copy()
    environment.update(APPDATA=str(tmp_path), HOME=str(tmp_path), USERPROFILE=str(tmp_path),
                       XDG_CONFIG_HOME=str(tmp_path), HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1")
    if sys.platform == "win32":
        data = tmp_path / "Utterleaf"
    elif sys.platform == "darwin":
        data = tmp_path / "Library" / "Application Support" / "Utterleaf"
    else:
        data = tmp_path / "utterleaf"
    folder = data / "models" / "faster-whisper-tiny.en"
    install_files(folder)
    before = {p.name: p.read_bytes() for p in folder.iterdir()}
    result = subprocess.run(
        [sys.executable, "-m", "utterleaf", "--model-setup-download", "tiny.en",
         "--model-setup-backend", "ctranslate2"],
        cwd=Path(__file__).resolve().parents[1], env=environment,
        stdin=subprocess.DEVNULL, capture_output=True, timeout=20,
    )
    assert result.returncode == 0, result.stderr.decode(errors="replace")
    assert result.stdout == b"" and result.stderr == b""
    assert {p.name: p.read_bytes() for p in folder.iterdir()} == before
    assert not (data / "config.toml").exists()
    assert not (data / "dictionary.txt").exists()
