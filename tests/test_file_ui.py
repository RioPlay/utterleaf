"""Real Tk workflow checks, with deterministic local recognition substitutes."""

import gc
import threading
import time
import tkinter as tk
import os
from fractions import Fraction

import pytest

from utterleaf.config import Config
from utterleaf.file_ui import FileWindow
from utterleaf.file_inspection import InspectedFile
from utterleaf.file_metadata import MediaAudioTrack, MediaMetadata
from utterleaf.transcript import Segment, Transcript


@pytest.fixture(scope="module")
def tk_root():
    failure = None
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        failure = str(exc)
    if failure is not None:
        gc.collect()
        pytest.skip(f"Tk needs a working display: {failure}")
    root.withdraw()
    yield root
    root.destroy()
    del root
    gc.collect()


@pytest.fixture
def window(tk_root, monkeypatch, tmp_path):
    root = tk.Toplevel(tk_root)
    root.withdraw()
    app = FileWindow(root, Config())
    track = MediaAudioTrack(ordinal=0, stream_index=4, codec="pcm_s16le", sample_rate=16000,
                            channels=1, layout="mono", title="Audio track", language=None,
                            is_default=True, start=Fraction(0), time_base=Fraction(1, 16000))
    inspected = InspectedFile(MediaMetadata(origin=Fraction(0), origin_kind="container",
                                             tracks=(track,)), (1, 2, 3))
    monkeypatch.setattr("utterleaf.file_ui.inspect_file", lambda *a, **k: inspected)
    monkeypatch.setattr("utterleaf.file_ui.current_file_signature", lambda *a, **k: inspected.signature)
    app.path = tmp_path / "speech.wav"
    app.inspected = inspected
    app.inspection_signature = inspected.signature
    app._track_ordinals = {"1: Audio track (16 kHz, 1 ch)": 0}
    app.audio_track_input.configure(values=tuple(app._track_ordinals))
    app.audio_track.set(tuple(app._track_ordinals)[0])
    app._controls()
    yield app
    app.close()


def pump(window, predicate):
    deadline = time.monotonic() + 3
    while not predicate() and time.monotonic() < deadline:
        window.root.update()
        time.sleep(0.01)
    assert predicate()


def test_cancel_discards_late_success_and_blocks_duplicate_jobs(window, monkeypatch, tmp_path):
    started, release = threading.Event(), threading.Event()
    calls = []
    def recognize(*args, **kwargs):
        calls.append(1)
        started.set()
        release.wait(3)
        return Transcript((Segment(0, 1, "private words"),))
    monkeypatch.setattr("utterleaf.file_ui.transcribe_file", recognize)
    window.path = tmp_path / "voice.wav"
    window.start()
    assert started.wait(1)
    window.start()
    window.cancel()
    release.set()
    pump(window, lambda: not window.busy)
    assert calls == [1]
    assert window.result is None
    assert window.preview.get("1.0", "end").strip() == ""
    assert "Cancelled" in window.status.get()
    assert list(tmp_path.iterdir()) == []


def test_audio_track_is_per_job_one_based_ui_and_zero_based_api(window, monkeypatch, tmp_path):
    calls = []

    def recognize(*args, **kwargs):
        calls.append(kwargs["audio_track"])
        return Transcript((Segment(0, 1, "selected track"),))

    monkeypatch.setattr("utterleaf.file_ui.transcribe_file", recognize)
    window.path = tmp_path / "multi-track.mkv"
    assert window.audio_track.get().startswith("1: ")
    window.start()
    pump(window, lambda: not window.busy)
    window.audio_track.set("1: Audio track (16 kHz, 1 ch)")
    window.start()
    pump(window, lambda: not window.busy)
    assert calls == [0, 0]
    assert str(window.audio_track_input.cget("state")) == "readonly"


@pytest.mark.parametrize("value", ("", "guest"))
def test_invalid_audio_track_does_not_start_or_discard_preview(window, monkeypatch, tmp_path, value):
    called = False

    def recognize(*args, **kwargs):
        nonlocal called
        called = True

    monkeypatch.setattr("utterleaf.file_ui.transcribe_file", recognize)
    window.path = tmp_path / "multi-track.mkv"
    window.result = Transcript((Segment(0, 1, "keep preview"),))
    window._preview(window.result.text)
    window.audio_track.set(value)
    window.start()
    assert not called
    assert not window.busy
    assert window.result.text == "keep preview"
    assert window.preview.get("1.0", "end").strip() == "keep preview"
    assert "inspected audio track" in window.status.get()


def test_audio_track_control_and_guidance_are_explicit(window, monkeypatch, tmp_path):
    started, release = threading.Event(), threading.Event()

    def recognize(*args, **kwargs):
        started.set()
        release.wait(3)
        return Transcript(())

    monkeypatch.setattr("utterleaf.file_ui.transcribe_file", recognize)
    window.path = tmp_path / "multi-track.mkv"
    assert "No duration limit" in window.file_guidance.cget("text")
    assert "not a stereo channel" in window.audio_track_hint.cget("text")
    assert "does not identify speakers" in window.audio_track_hint.cget("text")
    assert int(window.audio_track_label.cget("underline")) == 0
    window.start()
    assert started.wait(1)
    window.root.update()
    assert str(window.audio_track_input.cget("state")) == "disabled"
    release.set()
    pump(window, lambda: not window.busy)


def test_choose_inspects_file_and_maps_sparse_audio_ordinals(window, monkeypatch, tmp_path):
    tracks = tuple(MediaAudioTrack(ordinal=ordinal, stream_index=ordinal + 10,
                                   codec="pcm_s16le", sample_rate=48000, channels=2,
                                   layout="stereo", title=title, language=None,
                                   is_default=(ordinal == 0), start=Fraction(0),
                                   time_base=Fraction(1, 48000))
                   for ordinal, title in ((0, "Main"), (2, "Main")))
    inspected = InspectedFile(MediaMetadata(Fraction(0), "container", tracks), (8, 9, 10))
    monkeypatch.setattr("utterleaf.file_ui.filedialog.askopenfilename",
                        lambda **kwargs: str(tmp_path / "clip.mkv"))
    monkeypatch.setattr("utterleaf.file_ui.inspect_file", lambda *a, **k: inspected)
    window.choose()
    pump(window, lambda: not window.busy)
    labels = tuple(window.audio_track_input.cget("values"))
    assert labels[0].startswith("1: Main")
    assert labels[1].startswith("3: Main")
    assert window._track_ordinals[labels[1]] == 2


def test_cancelled_queued_inspection_cannot_replace_preview(window):
    window.result = Transcript((Segment(0, 1, "keep"),))
    window._preview(window.result.text)
    old_inspected = window.inspected
    old_signature = window.inspection_signature
    old_labels = tuple(window.audio_track_input.cget("values"))
    replacement = InspectedFile(MediaMetadata(Fraction(9), "container", (
        MediaAudioTrack(ordinal=2, stream_index=99, codec="aac", sample_rate=44100,
                        channels=2, layout="stereo", title="replacement", language=None,
                        is_default=False, start=Fraction(9), time_base=Fraction(1, 44100)),)),
        (77, 88))
    window.busy = True
    window.operation = "inspection"
    window.cancel_event = threading.Event()
    window.events.put(("inspection", replacement))
    window.cancel()
    window.poll_id = None
    window.poll()
    assert window.result.text == "keep"
    assert window.inspected is old_inspected
    assert window.inspection_signature == old_signature
    assert tuple(window.audio_track_input.cget("values")) == old_labels
    assert "Existing preview preserved" in window.status.get()


def test_inspection_blocks_duplicate_jobs_and_cancel_preserves_preview(window, monkeypatch):
    entered, release = threading.Event(), threading.Event()
    calls = []
    def inspect(*args, **kwargs):
        calls.append(1)
        entered.set()
        release.wait(2)
        return window.inspected
    monkeypatch.setattr("utterleaf.file_ui.inspect_file", inspect)
    window.result = Transcript((Segment(0, 1, "keep"),))
    window._preview(window.result.text)
    window.inspect_tracks()
    assert entered.wait(1)
    window.inspect_tracks()
    assert calls == [1]
    window.cancel()
    release.set()
    pump(window, lambda: not window.busy)
    assert window.result.text == "keep"
    assert calls == [1]


def test_inspection_start_failure_resets_state(window, monkeypatch):
    class BrokenThread:
        def __init__(self, *args, **kwargs):
            raise RuntimeError("private detail")
    monkeypatch.setattr("utterleaf.file_ui.threading.Thread", BrokenThread)
    window.inspect_tracks()
    assert not window.busy
    assert window.operation is None
    assert window.status.get() == "Could not start inspection."


def test_close_discards_old_inspection_queue(window):
    old_events = window.events
    old_events.put(("inspection", window.inspected))
    window.close()
    old_events.put(("inspection", window.inspected))
    window.poll()
    assert window.closed
    assert window.events.empty()


def test_early_cancelled_work_skips_signature_and_model(monkeypatch):
    from utterleaf.file_ui import _work
    cancel = threading.Event()
    cancel.set()
    events = __import__("queue").Queue()
    monkeypatch.setattr("utterleaf.file_ui.current_file_signature",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("signature called")))
    monkeypatch.setattr("utterleaf.file_ui.transcribe_file",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("model called")))
    _work("unused", Config(), 0, cancel, events, (1,))
    assert events.get_nowait() == ("cancelled", None)


def test_changed_before_start_prevents_recognition(window, monkeypatch):
    monkeypatch.setattr("utterleaf.file_ui.current_file_signature", lambda *a, **k: (99,))
    monkeypatch.setattr("utterleaf.file_ui.transcribe_file", lambda *a, **k: (_ for _ in ()).throw(AssertionError("called")))
    window.start()
    pump(window, lambda: not window.busy)
    assert window.result is None
    assert "changed" in window.status.get().lower()


def test_changed_after_recognition_discards_result(window, monkeypatch):
    signatures = iter([window.inspection_signature, (99,)])
    monkeypatch.setattr("utterleaf.file_ui.current_file_signature", lambda *a, **k: next(signatures))
    monkeypatch.setattr("utterleaf.file_ui.transcribe_file",
                        lambda *a, **k: Transcript((Segment(0, 1, "stale"),)))
    window.start()
    pump(window, lambda: not window.busy)
    assert window.result is None
    assert "changed" in window.status.get().lower()


def test_worker_start_failure_resets_busy_and_uses_generic_status(window, monkeypatch):
    class BrokenThread:
        def __init__(self, *args, **kwargs):
            raise RuntimeError("private detail")
    monkeypatch.setattr("utterleaf.file_ui.threading.Thread", BrokenThread)
    window.start()
    assert not window.busy
    assert window.operation is None
    assert window.status.get() == "Could not start recognition."


def test_close_discards_queued_result_without_widget_callbacks(window):
    result = Transcript((Segment(0, 1, "private words"),))
    old_events = window.events
    old_events.put(("result", result))
    window.close()
    old_events.put(("result", result))
    window.poll()
    assert window.result is None
    assert window.events.empty()
    assert window.cancel_event.is_set()


def test_export_needs_explicit_replace_and_preserves_preview(window, monkeypatch, tmp_path):
    path = tmp_path / "字幕.vtt"
    path.write_text("keep", encoding="utf-8")
    window.result = Transcript((Segment(0, 1, "東京"),))
    window.format.set("VTT")
    monkeypatch.setattr("utterleaf.file_ui.filedialog.asksaveasfilename", lambda **kwargs: str(path))
    monkeypatch.setattr("utterleaf.file_ui.messagebox.askyesno", lambda *args, **kwargs: False)
    window.export()
    assert path.read_text(encoding="utf-8") == "keep"
    monkeypatch.setattr("utterleaf.file_ui.messagebox.askyesno", lambda *args, **kwargs: True)
    window.export()
    assert path.read_text(encoding="utf-8").startswith("WEBVTT\n\n")
    assert "東京" in path.read_text(encoding="utf-8")
    assert window.result.text == "東京"
    window.discard()
    assert window.result is None
    assert path.exists()


def test_export_never_replaces_selected_media(window, monkeypatch, tmp_path):
    path = tmp_path / "speech.wav"
    path.write_bytes(b"original media")
    window.path = path
    window.result = Transcript((Segment(0, 1, "speech"),))
    monkeypatch.setattr("utterleaf.file_ui.filedialog.asksaveasfilename", lambda **kwargs: str(path))
    window.export()
    assert path.read_bytes() == b"original media"
    assert "preserve the original" in window.status.get()


def test_export_never_replaces_media_hardlink(window, monkeypatch, tmp_path):
    source = tmp_path / "speech.wav"
    source.write_bytes(b"original media")
    alias = tmp_path / "alias.txt"
    os.link(source, alias)
    window.path = source
    window.result = Transcript((Segment(0, 1, "speech"),))
    monkeypatch.setattr("utterleaf.file_ui.filedialog.asksaveasfilename", lambda **kwargs: str(alias))
    window.export()
    assert source.read_bytes() == b"original media"
    assert "preserve the original" in window.status.get()


def test_success_preview_stays_unsaved_and_compact_footer_visible(window, monkeypatch, tmp_path):
    monkeypatch.setattr("utterleaf.file_ui.transcribe_file", lambda *args, **kwargs: Transcript((Segment(0, 1, "scratch that 東京"),)))
    window.path = tmp_path / "speech.wav"
    window.start()
    pump(window, lambda: not window.busy)
    assert window.preview.get("1.0", "end").strip() == "scratch that 東京"
    assert list(tmp_path.iterdir()) == []
    window.root.deiconify()
    window.root.geometry("760x560")
    window.root.update()
    assert window.export_button.winfo_rooty() + window.export_button.winfo_height() <= window.root.winfo_rooty() + window.root.winfo_height()
