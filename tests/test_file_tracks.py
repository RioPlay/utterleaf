from fractions import Fraction
import threading

import pytest

from utterleaf.config import Config
from utterleaf.file_inspection import InspectedFile
from utterleaf.file_metadata import MediaAudioTrack, MediaMetadata
from utterleaf.file_tracks import (
    FileTranscripts, TrackTranscript, export_destinations, export_transcripts,
    preview_file_transcripts, transcribe_tracks,
)
from utterleaf.transcript import Segment, Transcript, TranscriptionCancelled


def track(ordinal, title="Audio", start=0):
    return MediaAudioTrack(
        ordinal=ordinal, stream_index=ordinal + 10, codec="pcm_s16le",
        sample_rate=16000, channels=1, layout="mono", title=title,
        language=None, is_default=ordinal == 0, start=Fraction(start),
        time_base=Fraction(1, 16000),
    )


def inspected(*tracks, origin=Fraction(1), origin_kind="container", signature=(1, 2, 3)):
    return InspectedFile(MediaMetadata(origin, origin_kind, tracks), signature)


def install_group(monkeypatch, tmp_path, metadata, recognize=None, **inspect_kwargs):
    path = tmp_path / "tracks.mkv"
    path.write_bytes(b"synthetic local media")
    seen = inspected(*metadata, **inspect_kwargs)
    monkeypatch.setattr("utterleaf.file_inspection.inspect_file", lambda *a, **k: seen)
    monkeypatch.setattr("utterleaf.file_inspection.current_file_signature", lambda *a, **k: seen.signature)
    calls = []

    def fake_transcribe(selected, cfg, **kwargs):
        calls.append(kwargs)
        reporter = kwargs.get("progress")
        if reporter is not None:
            reporter("recognizing", None)
        if recognize is not None:
            return recognize(kwargs)
        return Transcript((Segment(0, 0.2, f"track {kwargs['audio_track']}"),))

    monkeypatch.setattr("utterleaf.file_transcription.transcribe_file", fake_transcribe)
    return path, calls, seen


def test_selected_tracks_use_one_based_sparse_ordinals_and_reject_duplicates(tmp_path, monkeypatch):
    path, calls, seen = install_group(monkeypatch, tmp_path, (track(0, "Mix"), track(2, "Guest")))
    result = transcribe_tracks(path, Config(), audio_tracks=(1, 3), timing="recording")
    assert [item.track.ordinal for item in result.tracks] == [0, 2]
    assert [kwargs["audio_track"] for kwargs in calls] == [0, 2]
    assert [kwargs["_expected_clock"] for kwargs in calls] == [(Fraction(1), "container")] * 2
    relative_calls = []
    monkeypatch.setattr(
        "utterleaf.file_transcription.transcribe_file",
        lambda *a, **kwargs: relative_calls.append(kwargs) or Transcript((Segment(0, 0.2, "rel"),)),
    )
    transcribe_tracks(path, Config(), audio_tracks=(1, 3), timing="relative")
    assert [kwargs["_expected_clock"] for kwargs in relative_calls] == [None, None]
    default_calls = []
    monkeypatch.setattr(
        "utterleaf.file_transcription.transcribe_file",
        lambda *a, **kwargs: default_calls.append(kwargs) or Transcript((Segment(0, 0.2, "def"),)),
    )
    transcribe_tracks(path, Config(), audio_tracks=(1,))
    assert default_calls[0]["timing"] == "relative"
    assert default_calls[0]["_expected_clock"] is None
    recording_single = []
    monkeypatch.setattr(
        "utterleaf.file_transcription.transcribe_file",
        lambda *a, **kwargs: recording_single.append(kwargs) or Transcript((Segment(0, 0.2, "one"),)),
    )
    transcribe_tracks(path, Config(), audio_tracks=(1,), timing="recording")
    assert recording_single[0]["_expected_clock"] is None
    with pytest.raises(ValueError, match="more than once"):
        transcribe_tracks(path, Config(), audio_tracks=(1, 1))
    with pytest.raises(ValueError, match="not present"):
        transcribe_tracks(path, Config(), audio_tracks=(2,))
    with pytest.raises(ValueError, match="at least one"):
        transcribe_tracks(path, Config(), audio_tracks=())


@pytest.mark.parametrize("requested", [None, 1, "1", b"1", object()])
def test_track_selection_rejects_non_sequences(tmp_path, monkeypatch, requested):
    path, _calls, _seen = install_group(monkeypatch, tmp_path, (track(0),))
    with pytest.raises(ValueError, match="1 to 256"):
        transcribe_tracks(path, Config(), audio_tracks=requested)


def test_recording_group_is_all_or_none_and_keeps_shared_clock(tmp_path, monkeypatch):
    calls = []

    def recognize(kwargs):
        calls.append(kwargs["audio_track"])
        if kwargs["audio_track"] == 1:
            raise RuntimeError("second track failed")
        return Transcript((Segment(0.2, 0.4, "first"),))

    path, _recorded, seen = install_group(
        monkeypatch, tmp_path, (track(0), track(1)), recognize=recognize
    )
    with pytest.raises(RuntimeError, match="second track failed"):
        transcribe_tracks(path, Config(), audio_tracks=(1, 2), timing="recording")
    assert calls == [0, 1]
    relative = transcribe_tracks(path, Config(), audio_tracks=(1,), timing="relative")
    assert relative.origin is None and relative.origin_kind == "track-relative"
    assert relative.tracks[0].transcript.segments[0].text == "first"


def test_missing_clock_cannot_use_recording_group(tmp_path, monkeypatch):
    path, _calls, _seen = install_group(
        monkeypatch, tmp_path, (track(0),), origin=None, origin_kind="unavailable"
    )
    with pytest.raises(ValueError, match="no common recording clock"):
        transcribe_tracks(path, Config(), audio_tracks=(1,), timing="recording")


def test_cancel_before_second_track_returns_no_group(tmp_path, monkeypatch):
    cancel = threading.Event()

    def recognize(kwargs):
        cancel.set()
        return Transcript((Segment(0, 0.2, "first"),))

    path, _calls, _seen = install_group(
        monkeypatch, tmp_path, (track(0), track(1)), recognize=recognize
    )
    with pytest.raises(TranscriptionCancelled):
        transcribe_tracks(path, Config(), audio_tracks=(1, 2), cancel=cancel)
    progress = []
    transcribe_tracks(
        path, Config(), audio_tracks=(1,),
        progress=lambda *item: progress.append(item),
    )
    assert progress[0][:2] == (1, 1)


def test_source_change_before_recognition_is_visible(tmp_path, monkeypatch):
    path, _calls, seen = install_group(monkeypatch, tmp_path, (track(0),))
    with pytest.raises(ValueError, match="changed"):
        transcribe_tracks(path, Config(), audio_tracks=(1,), expected_signature=(9, 9))


def test_grouped_export_is_atomic_and_names_one_based_siblings(tmp_path):
    results = FileTranscripts(
        "recording", Fraction(1), "container",
        (
            TrackTranscript(track(0, "Mix"), Transcript((Segment(0, 1, "mix"),))),
            TrackTranscript(track(2, "Guest"), Transcript((Segment(0.2, 1.2, "guest"),))),
        ),
    )
    destination = tmp_path / "show.vtt"
    existing = tmp_path / "show-track1.vtt"
    existing.write_text("keep", encoding="utf-8")
    assert export_destinations(destination, (1, 3)) == (
        tmp_path / "show-track1.vtt", tmp_path / "show-track3.vtt",
    )
    with pytest.raises(FileExistsError):
        export_transcripts(results, destination)
    assert existing.read_text(encoding="utf-8") == "keep"
    assert not (tmp_path / "show-track3.vtt").exists()
    written = export_transcripts(results, destination, overwrite=True)
    assert [path.name for path in written] == ["show-track1.vtt", "show-track3.vtt"]
    assert "00:00:00.000 --> 00:00:01.000" in written[0].read_text(encoding="utf-8")
    assert "00:00:00.200 --> 00:00:01.200" in written[1].read_text(encoding="utf-8")
    leftover = [path for path in tmp_path.iterdir() if path.suffix != ".vtt"]
    assert leftover == []


def test_single_track_export_keeps_exact_destination(tmp_path):
    results = FileTranscripts(
        "relative", None, "track-relative",
        (TrackTranscript(track(1), Transcript((Segment(0, 1, "only"),))),),
    )
    path = tmp_path / "only.txt"
    written = export_transcripts(results, path)
    assert written == (path,)
    assert path.read_text(encoding="utf-8") == "only\n"


def test_grouped_export_rolls_back_if_later_destination_cannot_publish(tmp_path, monkeypatch):
    results = FileTranscripts(
        "recording", Fraction(0), "pcm-sample-clock",
        (
            TrackTranscript(track(0), Transcript((Segment(0, 1, "one"),))),
            TrackTranscript(track(1), Transcript((Segment(0, 1, "two"),))),
        ),
    )
    destination = tmp_path / "pair.srt"
    first = tmp_path / "pair-track1.srt"
    second = tmp_path / "pair-track2.srt"
    original = os_link = __import__("os").link
    calls = []

    def flaky(source, dest):
        calls.append(dest)
        if len(calls) == 2:
            raise OSError("no sibling publication")
        original(source, dest)

    monkeypatch.setattr("utterleaf.file_tracks.os.link", flaky)
    with pytest.raises(OSError, match="sibling"):
        export_transcripts(results, destination)
    assert not first.exists() and not second.exists()
    leftover = list(tmp_path.iterdir())
    assert leftover == []


def test_preview_labels_multiple_tracks_and_keeps_single_track_plain():
    single = FileTranscripts(
        "recording", Fraction(0), "container",
        (TrackTranscript(track(0, "Mix"), Transcript((Segment(0, 1, "hello"),))),),
    )
    grouped = FileTranscripts(
        "recording", Fraction(0), "container",
        (
            TrackTranscript(track(0, "Mix"), Transcript((Segment(0, 1, "hello"),))),
            TrackTranscript(track(1, "Guest"), Transcript((Segment(0.2, 1, "there"),))),
        ),
    )
    assert preview_file_transcripts(single) == "hello"
    assert "Track 1 — Mix\nhello" in preview_file_transcripts(grouped)
    assert "Track 2 — Guest\nthere" in preview_file_transcripts(grouped)
    empty = FileTranscripts(
        "recording", Fraction(0), "container",
        (
            TrackTranscript(track(0, "Mix"), Transcript(())),
            TrackTranscript(track(1, "Guest"), Transcript(())),
        ),
    )
    assert preview_file_transcripts(empty) == ""
