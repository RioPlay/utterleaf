from contextlib import contextmanager
import threading
from types import SimpleNamespace

import pytest

from utterleaf import audio_owner


@pytest.fixture
def lifecycle(monkeypatch):
    events = []
    @contextmanager
    def scope():
        events.append(("initialize", threading.get_ident()))
        try:
            yield
        finally:
            events.append(("uninitialize", threading.get_ident()))
    monkeypatch.setattr(audio_owner, "_com_scope", scope)
    return events


def test_owner_lifetime_reentrancy_and_order(lifecycle):
    owner = audio_owner.AudioOwner()
    caller = threading.get_ident()
    identity = owner.call(threading.get_ident)
    assert identity != caller
    assert owner.call(lambda: owner.call(threading.get_ident)) == identity
    owner.close(lambda: lifecycle.append(("teardown", threading.get_ident())))
    assert lifecycle == [("initialize", identity), ("teardown", identity), ("uninitialize", identity)]
    assert not owner._thread.is_alive()
    owner.close(lambda: pytest.fail("Repeated close must not tear down twice"))
    with pytest.raises(RuntimeError, match="closed"):
        owner.call(lambda: None)


def test_original_base_exception_preserved_and_worker_survives(lifecycle):
    owner = audio_owner.AudioOwner()
    error = KeyboardInterrupt("synthetic")
    def fail():
        raise error
    try:
        with pytest.raises(KeyboardInterrupt) as caught:
            owner.call(fail)
        assert caught.value is error
        assert owner.call(lambda: 42) == 42
    finally:
        owner.close(lambda: None)


def test_teardown_failure_still_uninitializes_and_joins(lifecycle):
    owner = audio_owner.AudioOwner()
    error = RuntimeError("teardown failed")
    def fail():
        raise error
    with pytest.raises(RuntimeError) as caught:
        owner.close(fail)
    assert caught.value is error
    assert lifecycle[-1][0] == "uninitialize"
    assert not owner._thread.is_alive()


def test_initialization_failure_does_not_leave_worker(monkeypatch):
    failure = OSError("COM unavailable")
    worker = []
    @contextmanager
    def scope():
        worker.append(threading.current_thread())
        raise failure
        yield
    monkeypatch.setattr(audio_owner, "_com_scope", scope)
    with pytest.raises(OSError) as caught:
        audio_owner.AudioOwner()
    assert caught.value is failure
    assert not worker[0].is_alive()


def test_close_waits_for_accepted_call_before_teardown(lifecycle):
    owner = audio_owner.AudioOwner()
    entered, release, closed = threading.Event(), threading.Event(), threading.Event()
    def action():
        entered.set()
        release.wait()
        lifecycle.append(("call", threading.get_ident()))
    caller = threading.Thread(target=lambda: owner.call(action))
    def close():
        owner.close(lambda: lifecycle.append(("teardown", threading.get_ident())))
        closed.set()
    closer = threading.Thread(target=close)
    caller.start()
    assert entered.wait(2)
    closer.start()
    try:
        assert not closed.wait(0.05)
    finally:
        release.set()
        caller.join(2)
        closer.join(2)
    assert closed.is_set()
    assert [name for name, _ in lifecycle] == ["initialize", "call", "teardown", "uninitialize"]


@pytest.mark.parametrize("hresult,balanced", [(0, True), (1, True), (-2147417850, False)])
def test_com_success_and_existing_apartment_balance(monkeypatch, hresult, balanced):
    calls = []
    def initialize(pointer, mode):
        calls.append(("initialize", pointer, mode))
        return hresult
    def uninitialize():
        calls.append(("uninitialize",))
    ole = SimpleNamespace(CoInitializeEx=initialize, CoUninitialize=uninitialize)
    monkeypatch.setattr(audio_owner.ctypes, "WinDLL", lambda name: ole, raising=False)
    with pytest.raises(ValueError):
        with audio_owner._com_scope():
            raise ValueError("body failure")
    assert calls == [("initialize", None, 0)] + ([("uninitialize",)] if balanced else [])


def test_com_failure_is_not_uninitialized(monkeypatch):
    def initialize(*args):
        return -2147467259
    def uninitialize():
        pytest.fail("Failed initialization has no COM reference to release")
    ole = SimpleNamespace(CoInitializeEx=initialize, CoUninitialize=uninitialize)
    monkeypatch.setattr(audio_owner.ctypes, "WinDLL", lambda name: ole, raising=False)
    with pytest.raises(OSError, match="0x80004005"):
        with audio_owner._com_scope():
            pytest.fail("COM failure must prevent audio access")
