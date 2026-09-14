"""Real Tk workflow checks, with deterministic local recognition substitutes."""

import gc
import threading
import time
import tkinter as tk
import os
from dataclasses import replace
from fractions import Fraction

import pytest

from utterleaf.config import Config
from utterleaf.file_ui import FileWindow
from utterleaf.file_inspection import InspectedFile
from utterleaf.file_metadata import MediaAudioTrack, MediaMetadata
from utterleaf.file_tracks import FileTranscripts, TrackTranscript
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
    app._show_tracks(inspected.metadata.tracks, selected=(0,))
    app._controls()
    yield app
    app.close()


def transcripts_for(window, *texts):
    origin = window.inspected.metadata.origin
    kind = window.inspected.metadata.origin_kind
    timing = "relative" if origin is None else "recording"
    items = []
    for index, text in enumerate(texts):
        items.append(TrackTranscript(
            window.inspected.metadata.tracks[index],
            Transcript((Segment(0, 1, text),)) if text else Transcript(()),
        ))
    return FileTranscripts(timing, origin, "track-relative" if origin is None else kind, tuple(items))


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
        return transcripts_for(window, "private words")
    monkeypatch.setattr("utterleaf.file_ui.transcribe_tracks", recognize)
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
        calls.append(kwargs["audio_tracks"])
        return transcripts_for(window, "selected track")

    monkeypatch.setattr("utterleaf.file_ui.transcribe_tracks", recognize)
    window.path = tmp_path / "multi-track.mkv"
    assert window._selected_track_numbers() == (1,)
    window.start()
    pump(window, lambda: not window.busy)
    window.start()
    pump(window, lambda: not window.busy)
    assert calls == [(1,), (1,)]
    assert str(window.audio_track_input.cget("state")) == "normal"


def test_invalid_audio_track_does_not_start_or_discard_preview(window, monkeypatch, tmp_path):
    called = False

    def recognize(*args, **kwargs):
        nonlocal called
        called = True

    monkeypatch.setattr("utterleaf.file_ui.transcribe_tracks", recognize)
    window.path = tmp_path / "multi-track.mkv"
    window.result = transcripts_for(window, "keep preview")
    window._preview(window.result.text)
    window.audio_track_input.selection_clear(0, "end")
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
        return transcripts_for(window, "")

    monkeypatch.setattr("utterleaf.file_ui.transcribe_tracks", recognize)
    window.path = tmp_path / "multi-track.mkv"
    assert "No duration limit" in window.file_guidance.cget("text")
    assert "not stereo channels" in window.audio_track_hint.cget("text")
    assert "speakers" in window.audio_track_hint.cget("text")
    assert "Shift-click" in window.audio_track_hint.cget("text")
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
    labels = tuple(window.audio_track_input.get(0, "end"))
    assert labels[0].startswith("1: Main")
    assert labels[1].startswith("3: Main")
    assert window._track_ordinals[labels[1]] == 2


def test_cancelled_queued_inspection_cannot_replace_preview(window):
    window.result = transcripts_for(window, "keep")
    window._preview(window.result.text)
    old_inspected = window.inspected
    old_signature = window.inspection_signature
    old_labels = tuple(window.audio_track_input.get(0, "end"))
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
    assert tuple(window.audio_track_input.get(0, "end")) == old_labels
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
    window.result = transcripts_for(window, "keep")
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
    monkeypatch.setattr("utterleaf.file_ui.transcribe_tracks",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("model called")))
    _work("unused", Config(), (1,), cancel, events, (1,))
    assert events.get_nowait() == ("cancelled", None)


def test_changed_before_start_prevents_recognition(window, monkeypatch):
    monkeypatch.setattr("utterleaf.file_ui.current_file_signature", lambda *a, **k: (99,))
    monkeypatch.setattr("utterleaf.file_ui.transcribe_tracks", lambda *a, **k: (_ for _ in ()).throw(AssertionError("called")))
    window.start()
    pump(window, lambda: not window.busy)
    assert window.result is None
    assert "changed" in window.status.get().lower()


def test_changed_after_recognition_discards_result(window, monkeypatch):
    signatures = iter([window.inspection_signature, (99,)])
    monkeypatch.setattr("utterleaf.file_ui.current_file_signature", lambda *a, **k: next(signatures))
    monkeypatch.setattr("utterleaf.file_ui.transcribe_tracks",
                        lambda *a, **k: transcripts_for(window, "stale"))
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
    window.result = transcripts_for(window, "東京")
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
    window.result = transcripts_for(window, "speech")
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
    window.result = transcripts_for(window, "speech")
    monkeypatch.setattr("utterleaf.file_ui.filedialog.asksaveasfilename", lambda **kwargs: str(alias))
    window.export()
    assert source.read_bytes() == b"original media"
    assert "preserve the original" in window.status.get()


def test_success_preview_stays_unsaved_and_compact_footer_visible(window, monkeypatch, tmp_path):
    monkeypatch.setattr("utterleaf.file_ui.transcribe_tracks", lambda *args, **kwargs: transcripts_for(window, "scratch that 東京"))
    window.path = tmp_path / "speech.wav"
    window.start()
    pump(window, lambda: not window.busy)
    assert window.preview.get("1.0", "end").strip() == "scratch that 東京"
    assert list(tmp_path.iterdir()) == []
    window.root.deiconify()
    window.root.geometry("760x560")
    window.root.update()
    assert window.export_button.winfo_rooty() + window.export_button.winfo_height() <= window.root.winfo_rooty() + window.root.winfo_height()


def test_new_file_defaults_to_recording_clock_and_choice_reaches_job(window, monkeypatch, tmp_path):
    monkeypatch.setattr("utterleaf.file_ui.filedialog.askopenfilename", lambda **kwargs: str(tmp_path / "new.mkv"))
    calls = []
    monkeypatch.setattr("utterleaf.file_ui.transcribe_tracks",
                        lambda *args, **kwargs: calls.append(kwargs["timing"]) or transcripts_for(window, "words"))
    window.choose()
    pump(window, lambda: not window.busy)
    assert window.recording_timestamps.get()
    assert "Keeps track offsets" in window.timing_hint.cget("text")
    window.start()
    pump(window, lambda: not window.busy)
    assert calls == ["recording"]
    window.timing_input.invoke()
    assert not window.recording_timestamps.get()
    assert window.result is None and window.preview.get("1.0", "end").strip() == ""
    assert str(window.export_button.cget("state")) == "disabled"
    assert "gaps are removed" in window.timing_hint.cget("text")
    window.start()
    pump(window, lambda: not window.busy)
    assert calls == ["recording", "relative"]


def test_missing_clock_is_explicit_and_cannot_request_recording_times(window, monkeypatch, tmp_path):
    inspected = replace(window.inspected, metadata=replace(window.inspected.metadata,
                                                          origin=None, origin_kind="unavailable"))
    monkeypatch.setattr("utterleaf.file_ui.inspect_file", lambda *args, **kwargs: inspected)
    monkeypatch.setattr("utterleaf.file_ui.filedialog.askopenfilename", lambda **kwargs: str(tmp_path / "raw.aac"))
    calls = []
    monkeypatch.setattr("utterleaf.file_ui.transcribe_tracks",
                        lambda *args, **kwargs: calls.append(kwargs["timing"]) or transcripts_for(window, ""))
    window.choose()
    pump(window, lambda: not window.busy)
    assert not window.recording_timestamps.get()
    assert str(window.timing_input.cget("state")) == "disabled"
    assert "unavailable" in window.timing_hint.cget("text")
    window.start()
    pump(window, lambda: not window.busy)
    assert calls == ["relative"]
    window.recording_timestamps.set(True)
    window.start()
    assert not window.busy and calls == ["relative"]
    assert "unavailable" in window.status.get()


def test_unchanged_reinspection_preserves_timing_choice_and_preview(window):
    window.recording_timestamps.set(False)
    selected = window._selected_track_numbers()
    window.result = transcripts_for(window, "keep")
    window._preview(window.result.text)
    window.inspect_tracks()
    pump(window, lambda: not window.busy)
    assert not window.recording_timestamps.get()
    assert window._selected_track_numbers() == selected
    assert window.result.text == "keep"


def test_track_change_invalidates_previous_export_preview(window):
    extra = MediaAudioTrack(ordinal=1, stream_index=11, codec="pcm_s16le", sample_rate=16000,
                            channels=1, layout="mono", title="Guest", language=None,
                            is_default=False, start=Fraction(1), time_base=Fraction(1, 16000))
    window._show_tracks((window.inspected.metadata.tracks[0], extra), selected=(0,))
    window.result = transcripts_for(window, "previous track")
    window._preview(window.result.text)
    window.audio_track_input.selection_clear(0, "end")
    window.audio_track_input.selection_set(1)
    window.audio_track_input.event_generate("<<ListboxSelect>>")
    window._job_options_changed()
    assert window.result is None
    assert str(window.export_button.cget("state")) == "disabled"


def test_recording_control_is_disabled_during_recognition(window, monkeypatch):
    entered, release = threading.Event(), threading.Event()
    def recognize(*args, **kwargs):
        entered.set()
        release.wait(3)
        return transcripts_for(window, "")
    monkeypatch.setattr("utterleaf.file_ui.transcribe_tracks", recognize)
    window.recording_timestamps.set(True)
    window.start()
    assert entered.wait(1)
    assert str(window.timing_input.cget("state")) == "disabled"
    release.set()
    pump(window, lambda: not window.busy)
    assert str(window.timing_input.cget("state")) == "normal"


def test_grouped_job_selects_sparse_tracks_and_exports_siblings(window, monkeypatch, tmp_path):
    extra = MediaAudioTrack(ordinal=2, stream_index=12, codec="pcm_s16le", sample_rate=16000,
                            channels=1, layout="mono", title="Guest", language=None,
                            is_default=False, start=Fraction(1), time_base=Fraction(1, 16000))
    tracks = (window.inspected.metadata.tracks[0], extra)
    window.inspected = replace(window.inspected, metadata=replace(window.inspected.metadata, tracks=tracks))
    window._show_tracks(tracks, selected=(0, 2))
    calls = []

    def recognize(*args, **kwargs):
        calls.append(kwargs["audio_tracks"])
        return FileTranscripts(
            "recording", Fraction(0), "container",
            (
                TrackTranscript(tracks[0], Transcript((Segment(0, 1, "mix"),))),
                TrackTranscript(tracks[1], Transcript((Segment(0.2, 1.2, "guest"),))),
            ),
        )

    monkeypatch.setattr("utterleaf.file_ui.transcribe_tracks", recognize)
    window.start()
    pump(window, lambda: not window.busy)
    assert calls == [(1, 3)]
    preview = window.preview.get("1.0", "end")
    assert "Track 1 — Audio track" in preview
    assert "Track 3 — Guest" in preview
    destination = tmp_path / "show.vtt"
    window.format.set("VTT")
    monkeypatch.setattr("utterleaf.file_ui.filedialog.asksaveasfilename", lambda **kwargs: str(destination))
    window.export()
    first = tmp_path / "show-track1.vtt"
    second = tmp_path / "show-track3.vtt"
    assert first.is_file() and second.is_file()
    assert "mix" in first.read_text(encoding="utf-8")
    assert "00:00:00.200 --> 00:00:01.200" in second.read_text(encoding="utf-8")
    assert "show-track1.vtt" in window.status.get() and "show-track3.vtt" in window.status.get()
    third = MediaAudioTrack(ordinal=3, stream_index=13, codec="pcm_s16le", sample_rate=16000,
                            channels=1, layout="mono", title="Room", language=None,
                            is_default=False, start=Fraction(2), time_base=Fraction(1, 16000))
    window._show_tracks((tracks[0], extra, third), selected=(0, 2))
    window.root.deiconify()
    window.root.geometry("760x560")
    window.root.update()
    assert int(window.audio_track_input.cget("height")) == 3
    assert window.export_button.winfo_rooty() + window.export_button.winfo_height() <= (
        window.root.winfo_rooty() + window.root.winfo_height()
    )
