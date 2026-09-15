"""Real Tk and worker lifecycle tests; no consumer state, OBS or audio."""
import gc
import sys
import threading
import time
import tkinter as tk
from tkinter import ttk
from types import SimpleNamespace

import pytest

from utterleaf import obs_pairing_ui as ui
from utterleaf.obs_pairing_store import PairingStoreCancelled, PairingStoreCommitError, PairingStoreError


class Store:
    def __init__(self, paired=False):
        self.paired, self.closed, self.claimed = paired, False, False
        self.calls, self.keys, self.threads = [], [], []
        self.removed = True
        self.error = None
        self.entered, self.release = threading.Event(), threading.Event()
        self.block = False
        self.commit_before_release = False

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.closed = True

    def claim_owner(self):
        self.claimed = True
        self.threads.append(threading.get_ident())

    def load(self):
        assert self.claimed
        if self.error == "load":
            raise PairingStoreError("DO NOT DISPLAY PRIVATE PAYLOAD")
        if not self.paired:
            return None
        value = bytearray(b"k" * 32)
        self.keys.append(value)
        return value

    def import_package(self, path, *, replace, cancelled):
        assert self.claimed
        self.calls.append(("import", path, replace))
        self.threads.append(threading.get_ident())
        if self.commit_before_release:
            self.paired = True
        self.entered.set()
        if self.block:
            assert self.release.wait(5)
        if not self.commit_before_release and cancelled():
            raise PairingStoreCancelled("Cancelled before commit")
        if self.error == "commit":
            raise PairingStoreCommitError("DO NOT DISPLAY PRIVATE PAYLOAD")
        if self.error == "import":
            raise RuntimeError("DO NOT DISPLAY PRIVATE PAYLOAD")
        self.paired = True
        return SimpleNamespace(package_removed=self.removed)

    def forget(self):
        assert self.claimed
        self.calls.append(("forget",))
        self.threads.append(threading.get_ident())
        self.paired = False
        if self.error == "forget":
            raise PairingStoreError("DO NOT DISPLAY PRIVATE PAYLOAD")
        return True


@pytest.fixture(scope="module")
def tk_root():
    try:
        root = tk.Tk()
    except tk.TclError as error:
        pytest.skip(f"Tk display unavailable: {error}")
    root.withdraw()
    yield root
    root.destroy()
    del root
    gc.collect()


def pump(root, predicate, timeout=5):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        root.update()
        if predicate():
            return
        time.sleep(.005)
    raise AssertionError("Timed out waiting for the controlled UI operation")


@pytest.fixture
def opened(tk_root, monkeypatch):
    dialogs = []
    monkeypatch.setattr(ui.filedialog, "askopenfilename", lambda **_: "C:/fixture/transfer.ulobs")
    monkeypatch.setattr(ui.messagebox, "askyesno", lambda *_, **__: True)

    def make(store=None, factory=None):
        store = store or Store()
        dialog = ui.ObsPairingDialog(tk_root, store_factory=factory or (lambda: store))
        dialogs.append((dialog, store))
        pump(tk_root, lambda: not dialog.busy)
        return dialog, store

    yield make
    for dialog, store in dialogs:
        store.release.set()
        if not dialog.closed:
            dialog.close()
            pump(tk_root, lambda: dialog.stopped.is_set())
            if not dialog.closed:
                dialog.close()
        dialog.worker.join(timeout=5) if dialog.worker.ident is not None else None
        assert not dialog.worker.is_alive()
    dialogs.clear()
    gc.collect()


def test_explicit_store_status_wipes_key_and_stays_on_worker(opened):
    dialog, store = opened(Store(paired=True))
    assert dialog.state.get() == "Pairing saved"
    assert store.claimed and not store.closed and not store.calls
    assert store.keys and all(value == bytes(32) for value in store.keys)
    assert set(store.threads) != {threading.get_ident()}
    assert dialog.worker.daemon is False


@pytest.mark.parametrize("cancel_at", ["picker", "confirm"])
def test_import_cancellation_before_mutation(opened, monkeypatch, cancel_at):
    dialog, store = opened()
    if cancel_at == "picker":
        monkeypatch.setattr(ui.filedialog, "askopenfilename", lambda **_: "")
    else:
        monkeypatch.setattr(ui.messagebox, "askyesno", lambda *_, **__: False)
    dialog.import_button.invoke()
    assert not store.calls and not dialog.busy and dialog.paired is False


@pytest.mark.parametrize("paired, removed", [(False, True), (True, False)])
def test_import_and_replace_report_verified_cleanup(opened, tk_root, paired, removed):
    dialog, store = opened(Store(paired=paired))
    store.removed = removed
    dialog.import_button.invoke()
    pump(tk_root, lambda: not dialog.busy)
    assert store.calls == [("import", "C:/fixture/transfer.ulobs", paired)]
    assert dialog.paired is True
    assert ("was removed" if removed else "file remains") in dialog.status.get()


@pytest.mark.parametrize("committed", [False, True])
def test_cancel_during_import_reports_actual_commit(opened, tk_root, committed):
    dialog, store = opened()
    store.block, store.commit_before_release = True, committed
    dialog.import_button.invoke()
    assert store.entered.wait(3)
    dialog.cancel_button.invoke()
    store.release.set()
    pump(tk_root, lambda: not dialog.busy)
    assert dialog.paired is committed
    assert ("committed before cancellation" if committed else "Cancelled before commit") in dialog.status.get()
    assert not store.closed


@pytest.mark.parametrize("committed", [False, True])
def test_close_waits_and_keeps_committed_result_for_acknowledgement(opened, tk_root, committed):
    dialog, store = opened()
    store.block, store.commit_before_release = True, committed
    dialog.import_pairing()
    assert store.entered.wait(3)
    closed = []
    dialog.close(on_closed=lambda: closed.append(True))
    assert not dialog.closed and not store.closed
    store.release.set()
    pump(tk_root, lambda: dialog.stopped.is_set() and not dialog.busy)
    if committed:
        assert not dialog.closed and not closed
        assert "committed before cancellation" in dialog.status.get()
        dialog.close()
    else:
        pump(tk_root, lambda: dialog.closed)
    assert store.closed and dialog.closed and closed == [True]


@pytest.mark.parametrize("error", ["import", "commit", "forget", "load"])
def test_failure_copy_has_no_raw_payload_or_false_rollback(opened, tk_root, error):
    dialog, store = opened(Store(paired=error == "forget"))
    store.error = error
    {"load": dialog.refresh, "forget": dialog.forget_pairing}.get(error, dialog.import_pairing)()
    pump(tk_root, lambda: not dialog.busy)
    assert "PRIVATE PAYLOAD" not in dialog.status.get()
    if error in ("import", "commit", "forget", "load"):
        assert dialog.paired is None
        assert str(dialog.import_button.cget("state")) == "disabled"
        assert str(dialog.forget_button.cget("state")) == "normal"
    if error == "commit":
        assert "was written" in dialog.status.get()
    store.error = None
    dialog.refresh()
    pump(tk_root, lambda: not dialog.busy)
    assert dialog.paired is store.paired


def test_forget_requires_confirmation_and_only_deletes_desktop_copy(opened, tk_root, monkeypatch):
    dialog, store = opened(Store(paired=True))
    monkeypatch.setattr(ui.messagebox, "askyesno", lambda *_, **__: False)
    dialog.forget_button.invoke()
    assert not store.calls
    monkeypatch.setattr(ui.messagebox, "askyesno", lambda *_, **__: True)
    dialog.forget_button.invoke()
    pump(tk_root, lambda: not dialog.busy)
    assert store.calls == [("forget",)] and dialog.paired is False
    assert "Other copies remain valid" in dialog.status.get()


def test_open_failure_can_retry_and_never_displays_exception(opened, tk_root):
    store = Store()
    calls = []
    def factory():
        calls.append(True)
        if len(calls) == 1:
            raise RuntimeError("DO NOT DISPLAY PRIVATE PAYLOAD")
        return store
    dialog, _ = opened(store, factory)
    assert "PRIVATE PAYLOAD" not in dialog.status.get()
    assert dialog.paired is None and str(dialog.import_button.cget("state")) == "disabled"
    dialog.refresh()
    pump(tk_root, lambda: not dialog.busy)
    assert store.claimed and dialog.paired is False and len(calls) == 2


def test_thread_start_failure_is_visible_and_can_close(opened, monkeypatch):
    def fail(_thread):
        raise RuntimeError("PRIVATE THREAD DETAIL")
    monkeypatch.setattr(threading.Thread, "start", fail)
    dialog, store = opened()
    assert "PRIVATE THREAD DETAIL" not in dialog.status.get()
    assert not store.claimed and dialog.stopped.is_set()
    dialog.close()
    assert dialog.closed


def test_external_parent_destruction_releases_worker(opened, tk_root):
    dialog, store = opened()
    dialog.root.destroy()
    pump(tk_root, lambda: dialog.stopped.is_set())
    assert dialog.closed and store.closed


@pytest.mark.parametrize("width,height,font_size", [(620, 530, 10), (450, 460, 10), (450, 460, 16)])
def test_compact_scrolling_focus_and_footer_fit(opened, tk_root, width, height, font_size):
    dialog, _ = opened()
    tk_root.deiconify()
    dialog.root.deiconify()
    dialog.root.geometry(f"{width}x{height}")
    style = ttk.Style(dialog.root)
    style.configure("TButton", font=("Segoe UI", font_size))
    style.configure("Primary.TButton", font=("Segoe UI", font_size, "bold"))
    for label, _ in dialog.labels:
        label.configure(font=("Segoe UI", font_size))
    tk_root.update()
    for button in (dialog.refresh_button, dialog.forget_button, dialog.close_button):
        assert button.winfo_rootx() >= dialog.root.winfo_rootx()
        assert button.winfo_rootx() + button.winfo_width() <= dialog.root.winfo_rootx() + dialog.root.winfo_width()
        assert button.winfo_rooty() + button.winfo_height() <= dialog.root.winfo_rooty() + dialog.root.winfo_height()
    dialog.canvas.yview_moveto(1)
    dialog._reveal_focus(SimpleNamespace(widget=dialog.import_button))
    tk_root.update()
    top = dialog.import_button.winfo_rooty() - dialog.canvas.winfo_rooty()
    assert top >= 0 and top + dialog.import_button.winfo_height() <= dialog.canvas.winfo_height()
    tk_root.withdraw()


@pytest.mark.skipif(sys.platform != "win32", reason="Real Windows DPAPI store")
def test_real_disposable_import_reload_and_forget_through_ui(opened, tk_root, tmp_path, monkeypatch):
    from utterleaf.obs_pairing_store import ObsPairingStore, _Native, encode_pairing_package, ROLE_TRANSFER
    native = _Native()
    transfer = tmp_path / "transfer.ulobs"
    key = bytearray(b"s" * 32)
    with native.opened(str(transfer), create=True, write=True) as handle:
        native.write(handle, encode_pairing_package(key, ROLE_TRANSFER, _native=native))
    sentinel = tmp_path / "transcript.txt"
    sentinel.write_text("keep")
    factory = lambda: ObsPairingStore(_root=tmp_path)
    dialog, _ = opened(factory=factory)
    monkeypatch.setattr(ui.filedialog, "askopenfilename", lambda **_: str(transfer))
    dialog.import_pairing()
    pump(tk_root, lambda: not dialog.busy)
    assert dialog.paired and not transfer.exists()
    dialog.close()
    pump(tk_root, lambda: dialog.closed)
    second, _ = opened(factory=factory)
    assert second.paired
    second.forget_pairing()
    pump(tk_root, lambda: not second.busy)
    assert second.paired is False and sentinel.read_text() == "keep"


@pytest.mark.skipif(sys.platform != "win32", reason="Windows Settings pairing entry")
def test_settings_entry_is_lazy_singleton_and_parent_close_waits(opened, tk_root, monkeypatch):
    from utterleaf import settings_ui
    from utterleaf.config import Config
    monkeypatch.setattr(settings_ui, "startup_enabled", lambda: False)
    monkeypatch.setattr(settings_ui, "dictionary_text", lambda: "")
    parent = tk.Toplevel(tk_root)
    app = settings_ui.SettingsWindow(parent, Config(), background=False)
    store = Store()
    actual_dialog = ui.ObsPairingDialog
    dialogs = []
    def create(root):
        dialog = actual_dialog(root, store_factory=lambda: store)
        dialogs.append(dialog)
        return dialog
    monkeypatch.setattr(ui, "ObsPairingDialog", create)
    try:
        assert not store.claimed and app.obs_pairing_dialog is None
        app.vars["hotkey"].set("f8")
        before = app._snapshot()
        app.show_obs_pairing()
        app.show_obs_pairing()
        assert len(dialogs) == 1 and app._snapshot() == before
        dialog = dialogs[0]
        pump(tk_root, lambda: not dialog.busy)
        store.block = store.commit_before_release = True
        dialog.import_pairing()
        assert store.entered.wait(3)
        app.close()
        assert not app.closed and not dialog.closed
        store.release.set()
        pump(tk_root, lambda: dialog.stopped.is_set() and not dialog.busy)
        assert not app.closed and not dialog.closed
        dialog.close()
        assert app.closed and store.closed
    finally:
        store.release.set()
        if not app.closed:
            app.vars["hotkey"].set(app.baseline["hotkey"])
            app.close()
            if dialogs and not dialogs[0].closed:
                pump(tk_root, lambda: dialogs[0].stopped.is_set())
                dialogs[0].close()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows Settings pairing entry")
def test_reset_and_discard_leave_pairing_untouched(opened, tk_root, monkeypatch):
    from utterleaf import settings_ui
    from utterleaf.config import Config
    monkeypatch.setattr(settings_ui, "startup_enabled", lambda: False)
    monkeypatch.setattr(settings_ui, "dictionary_text", lambda: "")
    app = settings_ui.SettingsWindow(tk.Toplevel(tk_root), Config(hotkey="f8"), background=False)
    dialog, store = opened(Store(paired=True))
    app.obs_pairing_dialog = dialog
    try:
        app.restore_defaults()
        assert store.paired and not store.calls
        dialog.close()
        pump(tk_root, lambda: dialog.closed)
        monkeypatch.setattr(settings_ui.messagebox, "askyesno", lambda *_, **__: False)
        app.close()
        assert not app.closed and store.paired and not store.calls
        monkeypatch.setattr(settings_ui.messagebox, "askyesno", lambda *_, **__: True)
        app.close()
        assert app.closed and store.paired and not store.calls
    finally:
        if not app.closed:
            app.closed = True
            app.root.after_cancel(app.poll_id)
            if app._page_reset is not None:
                app.root.after_cancel(app._page_reset)
            app.root.destroy()
