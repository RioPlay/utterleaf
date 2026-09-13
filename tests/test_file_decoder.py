"""Optional-decoder trust, subprocess bounds, and opt-in real format coverage."""

import os
from pathlib import Path
import subprocess
import sys
import threading

import numpy as np
import pytest

from utterleaf import file_decoder as decoder
from utterleaf.transcript import TranscriptionCancelled


@pytest.fixture
def settings(tmp_path, monkeypatch):
    path = tmp_path / "decoder.json"
    monkeypatch.setattr(decoder, "_settings_path", lambda: path)
    return path


@pytest.fixture
def selected(settings):
    path = settings.parent / ("ffmpeg.exe" if sys.platform == "win32" else "ffmpeg")
    path.write_bytes(b"MZ synthetic executable for identity tests")
    decoder.select_decoder(path)
    return path


def test_selection_never_executes_and_forget_preserves_executable(settings, monkeypatch):
    executable = settings.parent / "ffmpeg.exe"
    executable.write_bytes(b"MZ synthetic executable")
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: pytest.fail("Selection must not run a program"))
    decoder.select_decoder(executable)
    assert decoder.decoder_selection()["path"] == str(executable)
    decoder.forget_decoder()
    assert executable.exists()
    assert decoder.decoder_selection() is None


def test_no_automatic_path_execution_and_changed_binary_requires_reselection(settings, selected, monkeypatch):
    media = settings.parent / "clip.mp3"
    media.write_bytes(b"media")
    selected.write_bytes(b"MZ modified")
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: pytest.fail("Unexpected execution"))
    with pytest.raises(decoder.DecoderSetupError, match="changed"):
        decoder.decode_with_ffmpeg(media, max_bytes=1024, max_seconds=10)
    decoder.forget_decoder()
    monkeypatch.setenv("PATH", str(selected.parent))
    with pytest.raises(decoder.DecoderSetupError, match="More formats"):
        decoder.decode_with_ffmpeg(media, max_bytes=1024, max_seconds=10)


def test_settings_are_bounded_and_invalid_selection_rejected(settings):
    settings.write_bytes(b" " * 16385)
    with pytest.raises(decoder.DecoderSetupError, match="invalid"):
        decoder.decoder_selection()
    with pytest.raises(decoder.DecoderSetupError, match="executable"):
        decoder.select_decoder(settings.parent / "installer.cmd")


def test_command_has_no_shell_or_network_protocols_and_blocks_reference_movies(tmp_path):
    command = decoder._command(tmp_path / "ffmpeg.exe", tmp_path / "a & b.mp4", 600)
    assert command[command.index("-i") + 1] == str(tmp_path / "a & b.mp4")
    assert command[command.index("-protocol_whitelist") + 1] == "file"
    assert command[command.index("-format_whitelist") + 1] == "mov"
    assert command[command.index("-enable_drefs") + 1] == "0"
    assert command[command.index("-use_absolute_path") + 1] == "0"
    assert command[-1] == "pipe:1"
    with pytest.raises(ValueError, match="Choose"):
        decoder._command(tmp_path / "ffmpeg", tmp_path / "playlist.m3u8", 600)


def _standin(selected, monkeypatch, script):
    media = selected.parent / "clip.mp3"
    media.write_bytes(b"media")
    monkeypatch.setattr(decoder, "_command", lambda *args: [sys.executable, "-c", script])
    real_popen = subprocess.Popen
    processes = []
    def launch(*args, **kwargs):
        assert kwargs["shell"] is False
        assert kwargs["stderr"] is subprocess.DEVNULL
        assert "FFREPORT" not in kwargs["env"]
        process = real_popen(*args, **kwargs)
        processes.append(process)
        return process
    monkeypatch.setattr(decoder.subprocess, "Popen", launch)
    return media, processes


def test_process_output_is_bounded_and_child_reaped(selected, monkeypatch):
    media, processes = _standin(selected, monkeypatch, "import sys,time; sys.stdout.buffer.write(bytes(65536)); sys.stdout.flush(); time.sleep(20)")
    with pytest.raises(ValueError, match="10-minute"):
        decoder.decode_with_ffmpeg(media, max_bytes=1024, max_seconds=0.1)
    assert processes[0].poll() is not None


def test_hung_decoder_times_out_and_is_reaped(selected, monkeypatch):
    media, processes = _standin(selected, monkeypatch, "import time; time.sleep(20)")
    monkeypatch.setattr(decoder, "DECODE_TIMEOUT_SECONDS", 0.15)
    with pytest.raises(RuntimeError, match="too long"):
        decoder.decode_with_ffmpeg(media, max_bytes=1024, max_seconds=10)
    assert processes[0].poll() is not None


def test_cancel_kills_native_decoder(selected, monkeypatch):
    media, processes = _standin(selected, monkeypatch, "import time; time.sleep(20)")
    cancel = threading.Event()
    timer = threading.Timer(0.15, cancel.set)
    timer.start()
    try:
        with pytest.raises(TranscriptionCancelled):
            decoder.decode_with_ffmpeg(media, max_bytes=1024, max_seconds=10, cancel=cancel)
    finally:
        timer.cancel()
    assert processes[0].poll() is not None


def test_stderr_does_not_fill_memory_or_create_reports(selected, monkeypatch):
    monkeypatch.setenv("FFREPORT", "file=should-not-exist.log")
    media, processes = _standin(selected, monkeypatch,
        "import sys; sys.stderr.write('private metadata' * 1000000); sys.stdout.buffer.write(bytes(32000))")
    audio = decoder.decode_with_ffmpeg(media, max_bytes=1024, max_seconds=10)
    assert audio.shape == (16000,)
    assert audio.dtype == np.float32
    assert processes[0].returncode == 0
    assert not (selected.parent / "should-not-exist.log").exists()


def test_failed_decoder_never_returns_partial_audio(selected, monkeypatch):
    media, _ = _standin(selected, monkeypatch, "import sys; sys.stdout.buffer.write(bytes(32000)); sys.exit(1)")
    with pytest.raises(RuntimeError, match="could not decode"):
        decoder.decode_with_ffmpeg(media, max_bytes=1024, max_seconds=10)


def test_stream_command_selects_exact_audio_track_without_duration_limit(tmp_path):
    command = decoder._command(tmp_path / "ffmpeg.exe", tmp_path / "stream.mkv", None, 2)
    assert command[command.index("-map") + 1] == "0:a:2"
    assert "-t" not in command
    for track in (-1, 256, True, 1.5):
        with pytest.raises(ValueError, match="audio track"):
            decoder._command(tmp_path / "ffmpeg.exe", tmp_path / "stream.mkv", None, track)


def test_stream_601_seconds_has_bounded_blocks_and_no_total_cap(selected, monkeypatch):
    media, processes = _standin(selected, monkeypatch,
        "import sys\nfor _ in range(601):\n sys.stdout.buffer.write(bytes(32000))\n")
    total = 0
    for audio in decoder.iter_ffmpeg_audio(media):
        assert audio.dtype == np.float32
        assert len(audio) <= decoder.BLOCK_BYTES // 2
        total += len(audio)
    assert total == 601 * 16000
    assert processes[0].returncode == 0


def test_slow_model_consumer_is_not_a_decoder_timeout(selected, monkeypatch):
    from contextlib import closing
    from types import SimpleNamespace
    import time
    media, processes = _standin(selected, monkeypatch,
        "import sys; sys.stdout.buffer.write(bytes(320000))")
    elapsed = [0]
    monkeypatch.setattr(decoder, "time", SimpleNamespace(monotonic=lambda: time.monotonic() + elapsed[0]))
    with closing(decoder.iter_ffmpeg_audio(media)) as audio:
        first = next(audio)
        elapsed[0] = 3600  # Consumer owns the block for an hour; no wall-clock delay.
        assert len(first) + sum(len(x) for x in audio) == 160000
    assert processes[0].returncode == 0


def test_abandoned_stream_kills_and_reaps_decoder(selected, monkeypatch):
    media, processes = _standin(selected, monkeypatch,
        "import sys,time; sys.stdout.buffer.write(bytes(65536)); sys.stdout.flush(); time.sleep(20)")
    stream = decoder.iter_ffmpeg_audio(media)
    assert len(next(stream)) == 32768
    stream.close()
    assert processes[0].poll() is not None


def test_stream_reader_start_failure_still_reaps_child(selected, monkeypatch):
    media, processes = _standin(selected, monkeypatch, "import time; time.sleep(20)")
    def fail(*args):
        raise RuntimeError("No worker available")
    monkeypatch.setattr(threading.Thread, "start", fail)
    with pytest.raises(RuntimeError, match="No worker"):
        list(decoder.iter_ffmpeg_audio(media))
    assert processes[0].poll() is not None


@pytest.mark.parametrize("script,message", [
    ("import sys; sys.stdout.buffer.write(bytes(32000)); sys.exit(1)", "could not decode"),
    ("import sys; sys.stdout.buffer.write(bytes(32001))", "complete decodable audio"),
])
def test_stream_reports_late_failure_instead_of_success(selected, monkeypatch, script, message):
    media, processes = _standin(selected, monkeypatch, script)
    with pytest.raises((ValueError, RuntimeError), match=message):
        list(decoder.iter_ffmpeg_audio(media))
    assert processes[0].poll() is not None


@pytest.mark.parametrize("extension,codec", [("mp3", "libmp3lame"), ("m4a", "aac"), ("aac", "aac"),
    ("flac", "flac"), ("ogg", "libvorbis"), ("opus", "libopus"), ("mp4", "aac"),
    ("mov", "aac"), ("webm", "libopus"), ("mkv", "flac")])
def test_real_ffmpeg_common_formats(settings, extension, codec):
    executable = os.environ.get("UTTERLEAF_TEST_FFMPEG")
    if not executable:
        pytest.skip("Set UTTERLEAF_TEST_FFMPEG to an explicitly verified local binary for real codec tests")
    decoder.select_decoder(executable)
    media = settings.parent / f"sample.{extension}"
    subprocess.run([executable, "-nostdin", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i",
                    "sine=frequency=440:duration=0.25", "-c:a", codec, str(media)],
                   check=True, timeout=20, capture_output=True)
    audio = decoder.decode_with_ffmpeg(media, max_bytes=1024 * 1024, max_seconds=10)
    assert 3000 < len(audio) < 7000
    assert np.max(np.abs(audio)) > 0.01


def test_real_video_audio_track_and_duration_refusal(settings):
    executable = os.environ.get("UTTERLEAF_TEST_FFMPEG")
    if not executable:
        pytest.skip("Set UTTERLEAF_TEST_FFMPEG to an explicitly verified local binary for real codec tests")
    decoder.select_decoder(executable)
    media = settings.parent / "video.mp4"
    subprocess.run([executable, "-nostdin", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i",
                    "color=c=blue:size=32x32:rate=4:duration=0.25", "-f", "lavfi", "-i",
                    "sine=frequency=440:duration=0.25", "-c:v", "mpeg4", "-c:a", "aac", "-shortest", str(media)],
                   check=True, timeout=20, capture_output=True)
    audio = decoder.decode_with_ffmpeg(media, max_bytes=1024 * 1024, max_seconds=10)
    assert 3000 < len(audio) < 7000
    with pytest.raises(ValueError, match="10-minute"):
        decoder.decode_with_ffmpeg(media, max_bytes=1024 * 1024, max_seconds=0.1)
