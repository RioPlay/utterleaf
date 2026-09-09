"""Every failure the user can hit must say something true on screen."""

import pytest

from utterleaf import indicator
from utterleaf.app import ENGINE_FAILED, LINGER, LOADING, NO_MIC, status_hint
from utterleaf.config import Config


def test_every_error_kind_has_a_look() -> None:
    for kind in indicator.ERROR_KINDS:
        look = indicator.appearance(kind)
        assert look is not None, kind
        label, _fill, accent = look
        assert label
        assert accent.lower() == "#e46962"


def test_paste_failure_is_not_blamed_on_hearing() -> None:
    assert indicator.appearance("no_paste")[0] == "Couldn't paste"
    assert indicator.appearance("missed")[0] == "Didn't hear"
    assert indicator.appearance("transcribe")[0] == "Couldn't transcribe"


def test_failures_linger_longer_than_successes() -> None:
    assert LINGER["no_paste"] > LINGER["pasted"]
    assert LINGER["no_paste"] > LINGER["missed"]
    assert LINGER["transcribe"] == LINGER["no_paste"]


def test_engine_failure_does_not_auto_hide() -> None:
    assert "engine" not in LINGER


def test_status_hint_follows_mode(monkeypatch) -> None:
    monkeypatch.setattr("utterleaf.app.is_wayland", lambda: False)
    assert status_hint(Config(hotkey="f8", mode="hold")) == "hold f8"
    assert status_hint(Config(hotkey="f8", mode="toggle")) == "press f8"


@pytest.mark.parametrize("mode", ["hold", "toggle"])
def test_wayland_status_hint_uses_desktop_shortcut(monkeypatch, mode) -> None:
    monkeypatch.setattr("utterleaf.app.is_wayland", lambda: True)
    assert status_hint(Config(hotkey="f8", mode=mode)) == "desktop shortcut: utterleaf --toggle"


def test_status_strings_are_distinct() -> None:
    assert len({LOADING, ENGINE_FAILED, NO_MIC}) == 3


def test_windows_gets_the_native_pill(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(indicator.sys, "platform", "win32")
    monkeypatch.setattr("utterleaf.host.sys.platform", "win32")
    assert indicator.pill_backend() is indicator._run_win32


def test_macos_and_linux_do_not_run_tk_on_a_worker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Tk must own the process main thread (macOS aborts otherwise). Child process.
    monkeypatch.setattr("utterleaf.host.sys.platform", "darwin")
    assert indicator.pill_backend() is None
    monkeypatch.setattr("utterleaf.host.sys.platform", "linux")
    assert indicator.pill_backend() is None


def test_macos_pill_is_a_child_process(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeStdin:
        def __init__(self) -> None:
            self.writes: list[str] = []

        def write(self, payload: str) -> None:
            self.writes.append(payload)

        def flush(self) -> None:
            return None

        def close(self) -> None:
            return None

    class FakeProc:
        def __init__(self) -> None:
            self.stdin = FakeStdin()

        def wait(self, timeout):
            return 0

    fake = FakeProc()
    monkeypatch.setattr("utterleaf.host.sys.platform", "darwin")
    monkeypatch.setattr(indicator, "spawn_pill_process", lambda: fake)
    pill = indicator.Indicator(enabled=True)
    pill.start()
    assert pill.enabled is True
    assert pill._thread is None
    assert pill._proc is fake
    pill.set("listening", "hello")
    assert fake.stdin.writes == ["listening\thello\n"]
    pill.close()
    assert fake.stdin.writes[-1] == "quit\n"
    assert pill.enabled is False


def test_pill_process_spawn_failure_disables(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("utterleaf.host.sys.platform", "linux")

    def boom():
        raise OSError("no display")

    monkeypatch.setattr(indicator, "spawn_pill_process", boom)
    pill = indicator.Indicator(enabled=True)
    pill.start()
    assert pill.enabled is False
    pill.set("listening")
    assert pill._q.empty()


def test_a_dying_pill_does_not_raise() -> None:
    def explode(_q):
        raise RuntimeError("window server went away")

    indicator._guarded(explode)(None)
