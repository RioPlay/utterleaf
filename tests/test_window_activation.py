import os
from types import SimpleNamespace

import pytest

from utterleaf import settings_instance, window_activation as activation


def test_foreground_permission_is_limited_to_named_owner(monkeypatch):
    calls = []
    monkeypatch.setattr(activation.sys, "platform", "win32")
    monkeypatch.setattr(activation, "_user32", lambda: SimpleNamespace(
        AllowSetForegroundWindow=lambda pid: calls.append(pid) or True))
    for pid in (None, True, 0, -1, "123", 0xFFFFFFFF):
        assert not activation.allow_activation(pid)
    assert activation.allow_activation(123)
    assert calls == [123]


def test_activation_grants_owner_before_enqueuing_request(tmp_path, monkeypatch):
    monkeypatch.setattr(settings_instance, "data_dir", lambda: tmp_path)
    calls = []
    monkeypatch.setattr(activation, "allow_activation", lambda pid: calls.append(("grant", pid)))
    instance = settings_instance.SettingsInstance()
    try:
        assert instance.acquire(lambda: calls.append(("activate", os.getpid())))
        assert settings_instance.activate()
        assert calls == [("grant", os.getpid()), ("activate", os.getpid())]
    finally:
        instance.close()


@pytest.mark.parametrize("payload", [b"x" * 2049, b"[]", b"null", b"\xff"])
def test_malformed_activation_metadata_does_not_raise(tmp_path, monkeypatch, payload):
    monkeypatch.setattr(settings_instance, "data_dir", lambda: tmp_path)
    (tmp_path / "settings-instance.json").write_bytes(payload)
    assert not settings_instance.activate()


def test_raise_reuses_window_and_preserves_modal_and_topmost(monkeypatch):
    import tkinter as tk
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(str(exc))
    modal = None
    calls = []
    try:
        entry = tk.Entry(root)
        entry.pack()
        entry.insert(0, "Unsaved changes")
        modal = tk.Toplevel(root)
        root.update()
        modal.grab_set()
        api = SimpleNamespace(GetAncestor=lambda hwnd, mode: hwnd,
                              IsIconic=lambda hwnd: False,
                              SetForegroundWindow=lambda hwnd: calls.append(hwnd) or True)
        monkeypatch.setattr(activation.sys, "platform", "win32")
        monkeypatch.setattr(activation, "_user32", lambda: api)
        before = root.winfo_id()
        activation.raise_window(root)
        root.update()
        assert root.winfo_id() == before
        assert entry.get() == "Unsaved changes"
        assert root.grab_current() is modal
        assert not root.attributes("-topmost")
        assert calls == [modal.winfo_id()]
    finally:
        if modal is not None:
            modal.destroy()
        root.destroy()
