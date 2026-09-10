import json
import subprocess
import sys
import threading
import pytest

from utterleaf import settings_instance


def test_second_process_activates_owner_and_lock_can_be_reused(tmp_path, monkeypatch):
    monkeypatch.setattr(settings_instance, "data_dir", lambda: tmp_path)
    activated = threading.Event()
    first = settings_instance.SettingsInstance()
    assert first.acquire(activated.set)
    try:
        script = """
import sys
from pathlib import Path
from utterleaf import settings_instance as module
module.data_dir = lambda: Path(sys.argv[1])
instance = module.SettingsInstance()
assert not instance.acquire(lambda: None)
instance.close()
"""
        result = subprocess.run([sys.executable, "-c", script, str(tmp_path)], capture_output=True, text=True, timeout=10)
        assert result.returncode == 0, result.stderr
        assert activated.wait(1)
        assert first.endpoint.exists()  # A losing launcher must not erase ownership.
    finally:
        first.close()
    assert not settings_instance.activate()
    replacement = settings_instance.SettingsInstance()
    try:
        assert replacement.acquire(lambda: None)
    finally:
        replacement.close()


def test_stale_endpoint_does_not_prevent_opening(tmp_path, monkeypatch):
    monkeypatch.setattr(settings_instance, "data_dir", lambda: tmp_path)
    (tmp_path / "settings-instance.json").write_text(json.dumps({"port": 0, "token": "stale"}))
    assert not settings_instance.activate()
    instance = settings_instance.SettingsInstance()
    try:
        assert instance.acquire(lambda: None)
        assert settings_instance.activate()
    finally:
        instance.close()


def test_tray_reuses_settings_without_spawning(monkeypatch):
    from utterleaf import settings
    launches = []
    monkeypatch.setattr(settings, "_relaunch", lambda *args: launches.append(args))
    monkeypatch.setattr(settings_instance, "activate", lambda: True)
    settings.launch_settings()
    assert launches == []
    monkeypatch.setattr(settings_instance, "activate", lambda: False)
    settings.launch_settings()
    assert launches == [("--settings",)]


def test_crashed_owner_releases_os_lock(tmp_path, monkeypatch):
    monkeypatch.setattr(settings_instance, "data_dir", lambda: tmp_path)
    script = """
import os, sys
from pathlib import Path
from utterleaf import settings_instance as module
module.data_dir = lambda: Path(sys.argv[1])
instance = module.SettingsInstance()
assert instance.acquire(lambda: None)
os._exit(0)
"""
    result = subprocess.run([sys.executable, "-c", script, str(tmp_path)], capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    assert (tmp_path / "settings-instance.json").exists()
    replacement = settings_instance.SettingsInstance()
    try:
        assert replacement.acquire(lambda: None)
    finally:
        replacement.close()


def test_files_and_settings_activate_independently(tmp_path, monkeypatch):
    monkeypatch.setattr(settings_instance, "data_dir", lambda: tmp_path)
    settings_event, files_event = threading.Event(), threading.Event()
    settings = settings_instance.SettingsInstance()
    files = settings_instance.SettingsInstance("files")
    try:
        assert settings.acquire(settings_event.set)
        assert files.acquire(files_event.set)
        assert settings_instance.activate("files")
        assert files_event.wait(1)
        assert not settings_event.is_set()
        assert settings_instance.activate()
        assert settings_event.wait(1)
        assert files.endpoint.name == "files-instance.json"
        assert settings.endpoint.name == "settings-instance.json"
    finally:
        files.close()
        settings.close()


def test_files_second_process_activates_owner(tmp_path, monkeypatch):
    monkeypatch.setattr(settings_instance, "data_dir", lambda: tmp_path)
    activated = threading.Event()
    owner = settings_instance.SettingsInstance("files")
    assert owner.acquire(activated.set)
    try:
        script = """
import sys
from pathlib import Path
from utterleaf import settings_instance as module
module.data_dir = lambda: Path(sys.argv[1])
instance = module.SettingsInstance('files')
assert not instance.acquire(lambda: None)
instance.close()
"""
        result = subprocess.run([sys.executable, "-c", script, str(tmp_path)], capture_output=True, text=True, timeout=10)
        assert result.returncode == 0, result.stderr
        assert activated.wait(1)
        assert owner.endpoint.exists()
    finally:
        owner.close()


def test_window_namespace_is_constrained():
    with pytest.raises(ValueError):
        settings_instance.SettingsInstance("../arbitrary")
    with pytest.raises(ValueError):
        settings_instance.activate("../arbitrary")
