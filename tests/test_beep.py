import io
import wave

import pytest

from utterleaf import beep as app


def test_tone_is_a_valid_mono_wav() -> None:
    with wave.open(io.BytesIO(app.tone_wav(760)), "rb") as handle:
        assert handle.getnchannels() == 1
        assert handle.getsampwidth() == 2
        assert handle.getframerate() == 22050
        assert handle.getnframes() > 0


def test_tone_fades_so_it_does_not_click() -> None:
    import struct

    with wave.open(io.BytesIO(app.tone_wav(760)), "rb") as handle:
        frames = handle.readframes(handle.getnframes())
    samples = struct.unpack(f"<{len(frames) // 2}h", frames)
    assert samples[0] == 0
    assert abs(samples[-1]) < abs(max(samples, key=abs))


def test_macos_prefers_afplay(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(app.sys, "platform", "darwin")
    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/afplay" if name == "afplay" else None)
    assert app.audio_player() == ["/usr/bin/afplay"]


def test_linux_falls_back_through_players(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(app.sys, "platform", "linux")
    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/aplay" if name == "aplay" else None)
    assert app.audio_player() == ["/usr/bin/aplay", "-q"]


def test_no_player_reports_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(app.sys, "platform", "linux")
    monkeypatch.setattr("shutil.which", lambda _name: None)
    assert app.audio_player() is None


def test_beep_uses_the_player_on_posix(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []
    monkeypatch.setattr(app.sys, "platform", "linux")
    monkeypatch.setattr(app, "audio_player", lambda: ["/usr/bin/paplay"])
    monkeypatch.setattr("subprocess.Popen", lambda args, **_kw: calls.append(args))
    app._beep_sync("start")
    assert len(calls) == 1
    assert calls[0][0] == "/usr/bin/paplay"
    assert calls[0][1].endswith(".wav")
