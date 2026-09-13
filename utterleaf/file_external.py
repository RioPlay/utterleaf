"""Original presentation timing through explicitly selected local media tools."""

from __future__ import annotations

from contextlib import closing, contextmanager
from dataclasses import dataclass
from fractions import Fraction
import os
from pathlib import Path
import stat
import threading

import numpy as np

from utterleaf.file_decoder import DecoderSetupError, FORMATS, decoder_selection, executable_identity
from utterleaf.file_frame_journal import FrameTimingJournal
from utterleaf.file_frame_metadata import parse_compact_audio_frame
from utterleaf.file_media import AudioTrack, TimedMedia
from utterleaf.file_metadata import MAX_PAYLOAD_BYTES, parse_media_metadata
from utterleaf.file_probe import _probe_command, probe_selection
from utterleaf.file_timeline import TimelineAudioBlock, SAMPLE_RATE
from utterleaf.local_filesystem import require_local_filesystem
from utterleaf.media_process import collect_tool_output, iter_tool_output
from utterleaf.media_tool_pair import compare_tool_pair, parse_tool_version
from utterleaf.transcript import TranscriptionCancelled


def _check_cancel(cancel, abort):
    if cancel is not None and cancel.is_set():
        raise TranscriptionCancelled("File transcription cancelled")
    if abort.is_set():
        raise RuntimeError("Media processing stopped before completion")


def _stamp(info):
    return (info.st_dev, info.st_ino, stat.S_IFMT(info.st_mode), info.st_size,
            info.st_mtime_ns, info.st_ctime_ns)


class _HeldSource:
    """Hold a regular source and detect ordinary changes across all passes.

    Each stat API has its own timestamp baseline on Windows. This does not
    eliminate pathname launch races or authenticate maliciously restored bytes.
    """

    def __init__(self, path):
        self.path = require_local_filesystem(path)
        self.file = None

    def __enter__(self):
        try:
            before = self.path.stat()
            if not stat.S_ISREG(before.st_mode) or before.st_size <= 0:
                raise ValueError("Select a nonempty regular local media file")
            self.file = self.path.open("rb")
            handle, pathname = os.fstat(self.file.fileno()), self.path.stat()
            self._handle_stamp, self._path_stamp = _stamp(handle), _stamp(pathname)
            if _stamp(before) != self._path_stamp or self._handle_stamp[:5] != self._path_stamp[:5]:
                raise ValueError("The selected file changed before decoding")
        except Exception:
            if self.file is not None:
                self.file.close()
            raise ValueError("The selected media file could not be held unchanged") from None
        return self

    def check(self):
        try:
            unchanged = (_stamp(os.fstat(self.file.fileno())) == self._handle_stamp
                         and _stamp(self.path.stat()) == self._path_stamp)
        except (OSError, ValueError):
            unchanged = False
        if not unchanged:
            raise ValueError("The selected media file changed during decoding")

    def __exit__(self, *_args):
        self.file.close()


@dataclass(frozen=True)
class _SelectedTool:
    program: str
    path: Path
    sha256: str

    def check(self):
        if executable_identity(self.path, program=self.program) != self.sha256:
            raise DecoderSetupError("A selected media tool changed. Select the updated installation again.")


@dataclass(frozen=True)
class _ToolPair:
    decoder: _SelectedTool
    probe: _SelectedTool

    def check(self):
        self.decoder.check()
        self.probe.check()


def _verified_pair(cancel, abort):
    selected_decoder, selected_probe = decoder_selection(), probe_selection()
    if selected_decoder is None or selected_probe is None:
        raise DecoderSetupError("Aligned files need matching FFmpeg and FFprobe installations. Select both in More formats.")
    pair = _ToolPair(
        _SelectedTool("ffmpeg", Path(selected_decoder["path"]), selected_decoder["sha256"]),
        _SelectedTool("ffprobe", Path(selected_probe["path"]), selected_probe["sha256"]),
    )
    builds = []
    for tool in (pair.decoder, pair.probe):
        payload = collect_tool_output(
            tool.path, ["-version"], check_identity=tool.check, cancel=cancel,
            abort=abort, max_bytes=65536, wall_timeout=10, reject_stderr=True,
        )
        builds.append(parse_tool_version(payload, program=tool.program))
    compare_tool_pair(*builds)
    pair.check()
    return pair


def _local_input(path: Path):
    media_format = FORMATS.get(path.suffix.lower())
    if media_format is None:
        raise ValueError("Choose a supported local audio or video file")
    arguments = ["-max_alloc", "67108864", "-probesize", "8388608",
                 "-analyzeduration", "5000000", "-protocol_whitelist", "file",
                 "-format_whitelist", media_format, "-f", media_format]
    if media_format == "mov":
        arguments += ["-enable_drefs", "0", "-use_absolute_path", "0"]
    return arguments


def _frame_arguments(path, ordinal):
    return ["-v", "error", *_local_input(path), "-fflags", "+nofillin",
            "-threads:a", "1", "-flags:a", "+bitexact", "-select_streams", f"a:{ordinal}",
            "-show_frames", "-show_entries",
            "frame=stream_index,pts,nb_samples,sample_fmt,channels,channel_layout:frame_side_data=",
            "-of", "compact=p=0:nk=0:escape=c", "-i", str(path)]


def _decode_arguments(path, track):
    return ["-nostdin", "-hide_banner", "-loglevel", "error", "-xerror",
            "-filter_threads", "1", "-copyts", *_local_input(path),
            "-fflags", "+nofillin", "-threads:a", "1", "-flags:a", "+bitexact",
            "-reinit_filter", "0", "-i", str(path), "-map", f"0:a:{track.ordinal}",
            "-vn", "-sn", "-dn", "-ar", str(track.sample_rate), "-ac", "1",
            "-c:a", "pcm_s16le", "-f", "s16le", "pipe:1"]


def _resample_arguments(rate):
    return ["-nostdin", "-hide_banner", "-loglevel", "error", "-xerror",
            "-filter_threads", "1", "-protocol_whitelist", "pipe", "-format_whitelist", "s16le",
            "-f", "s16le", "-ar", str(rate), "-ac", "1", "-i", "pipe:0",
            "-map", "0:a:0", "-ar", str(SAMPLE_RATE), "-ac", "1",
            "-c:a", "pcm_s16le", "-f", "s16le", "pipe:1"]


def _frame_lines(chunks):
    pending = b""
    for chunk in chunks:
        if not isinstance(chunk, bytes) or len(chunk) > 65536:
            raise ValueError("Invalid media timing output")
        data = pending + chunk
        start = 0
        while True:
            end = data.find(b"\n", start)
            if end < 0:
                break
            if end + 1 - start > 512:
                raise ValueError("Media timing row exceeds its safe size")
            yield data[start:end + 1]
            start = end + 1
        pending = data[start:]
        if len(pending) > 512:
            raise ValueError("Media timing row exceeds its safe size")
    if pending:
        yield pending


def _inspect_frames(source, pair, track, origin, cancel, abort, progress):
    journal = FrameTimingJournal(sample_rate=track.sample_rate, time_base=track.time_base,
                                 origin=origin, stream_index=track.stream_index)
    def check():
        source.check()
        pair.check()
    try:
        with closing(iter_tool_output(pair.probe.path, _frame_arguments(source.path, track.ordinal),
                                      check_identity=check, cancel=cancel, abort=abort,
                                      reject_stderr=True)) as chunks:
            for row in _frame_lines(chunks):
                _check_cancel(cancel, abort)
                frame = parse_compact_audio_frame(row, sample_rate=track.sample_rate,
                                                  expected_stream_index=track.stream_index)
                if frame.channels != track.channels:
                    raise ValueError("Decoded channels disagree with the selected track metadata")
                journal.append(frame)
                if progress is not None:
                    progress("timing", None)
        check()
        _check_cancel(cancel, abort)
        journal.seal()
        return journal
    except BaseException:
        journal.close()
        raise


# These uncompressed formats declare their rate in the container header. Other
# codecs need observable PTS progression within every accepted presentation run.
_HEADER_PCM = frozenset({
    "pcm_u8", "pcm_s8", "pcm_s16le", "pcm_s16be", "pcm_s24le", "pcm_s24be",
    "pcm_s32le", "pcm_s32be", "pcm_s64le", "pcm_s64be",
    "pcm_f32le", "pcm_f32be", "pcm_f64le", "pcm_f64be",
})


class _RawRuns:
    """Partition one raw decoder iterator with one timing-entry lookahead.

    Only the current resampler's stdin worker consumes ``run_input``. Its joined
    successful EOF hands ownership back to the calling thread for the next run.
    No frame-sized audio buffer or whole-file PCM copy is retained.
    """

    def __init__(self, raw, entries, track, cancel, abort):
        self.raw, self.entries, self.track = raw, entries, track
        self.cancel, self.abort = cancel, abort
        self.pending = b""
        self.entry = next(entries, None)
        self.run_samples = 0
        self.run_finished = False
        self.finished = False
        self.failure = None

    def _take(self, remaining):
        while remaining:
            _check_cancel(self.cancel, self.abort)
            if not self.pending:
                self.pending = next(self.raw, b"")
                if not self.pending:
                    raise ValueError("Decoded audio ended before its original frame timing")
                if type(self.pending) is not bytes or len(self.pending) > 65536:
                    raise ValueError("The decoder returned invalid audio output")
            size = min(remaining, len(self.pending))
            block, self.pending = self.pending[:size], self.pending[size:]
            remaining -= size
            yield block

    def run_input(self):
        try:
            yield from self._consume_run()
        except Exception as exc:
            # These are local validated timing/transport errors, never raw tool
            # diagnostics. The owner can restore them after the stdin worker is
            # joined instead of losing the useful reason at that thread boundary.
            self.failure = exc
            raise

    def _consume_run(self):
        if self.entry is None or not self.entry.run_start:
            raise ValueError("The original audio run is missing")
        self.run_samples, self.run_finished = 0, False
        first_pts, last_pts, frames = self.entry.pts, self.entry.pts, 0
        while self.entry is not None:
            current = self.entry
            self.run_samples += current.nb_samples
            frames += 1
            last_pts = current.pts
            yield from self._take(current.nb_samples * 2)
            # Exhaustion also validates the journal digest; a yielded prefix is
            # never sufficient evidence for a completed transcription.
            self.entry = next(self.entries, None)
            if self.entry is None or self.entry.run_start:
                break
        if self.track.codec not in _HEADER_PCM and (frames < 2 or last_pts <= first_pts):
            raise ValueError("This compressed audio run is too short to verify its original timing")
        if self.entry is None:
            if self.pending or next(self.raw, None) is not None:
                raise ValueError("Decoded audio exceeds its original frame timing")
            self.finished = True
        self.run_finished = True


def _external_blocks(source, pair, track, journal, cancel, abort, progress):
    def check():
        source.check()
        pair.check()

    with closing(journal.entries()) as entries, closing(iter_tool_output(
        pair.decoder.path, _decode_arguments(source.path, track),
        check_identity=check, cancel=cancel, abort=abort, reject_stderr=True,
    )) as raw:
        runs = _RawRuns(raw, entries, track, cancel, abort)
        previous_end = None
        while runs.entry is not None:
            _check_cancel(cancel, abort)
            start = runs.entry.pts * track.time_base
            if previous_end is not None and start < previous_end:
                raise ValueError("The timestamp gap is too small to preserve after resampling")
            emitted, pending = 0, b""
            with closing(runs.run_input()) as input_chunks:
                # Native-rate PCM needs no extra process and preserves even a
                # one-sample uncompressed run without a resampler's filter delay.
                output = input_chunks if track.sample_rate == SAMPLE_RATE else iter_tool_output(
                    pair.decoder.path, _resample_arguments(track.sample_rate),
                    check_identity=check, cancel=cancel, abort=abort, input_chunks=input_chunks,
                    reject_stderr=True,
                )
                try:
                    with closing(output) as chunks:
                        for chunk in chunks:
                            _check_cancel(cancel, abort)
                            data = pending + chunk
                            end = len(data) - len(data) % 2
                            pending = data[end:]
                            if not end:
                                continue
                            samples = np.frombuffer(data[:end], dtype="<i2").astype(np.float32) / 32768.0
                            block_start = start + Fraction(emitted, SAMPLE_RATE)
                            # Record length before consumers receive writable arrays.
                            emitted += samples.size
                            yield TimelineAudioBlock(block_start, samples)
                            if progress is not None:
                                progress("decoding", None)
                except Exception:
                    if cancel is not None and cancel.is_set():
                        raise TranscriptionCancelled("File transcription cancelled") from None
                    if runs.failure is not None:
                        raise runs.failure from None
                    raise
            _check_cancel(cancel, abort)
            if pending or not emitted or not runs.run_finished:
                raise ValueError("The audio run did not finish with complete samples")
            if abs(Fraction(emitted, SAMPLE_RATE) - Fraction(runs.run_samples, track.sample_rate)) > Fraction(1, SAMPLE_RATE):
                raise ValueError("The resampler did not preserve the audio run duration")
            previous_end = start + Fraction(emitted, SAMPLE_RATE)
        if not runs.finished:
            raise ValueError("The original audio timing contains no complete runs")
        check()
        _check_cancel(cancel, abort)


@contextmanager
def open_ffmpeg_timeline(path, *, audio_track=0, cancel=None, progress=None):
    """Open an explicitly selected pair's original-time, bounded audio stream.

    All blocks are provisional until successful iterator exhaustion. Callers
    must discard recognition/export results on any late error. Context exit
    owns the source, private timing journal and every media process.
    """
    if type(audio_track) is not int or not 0 <= audio_track < 256:
        raise ValueError("Choose a valid audio track")
    abort = threading.Event()
    _check_cancel(cancel, abort)
    with _HeldSource(path) as source:
        pair = _verified_pair(cancel, abort)
        def check():
            source.check()
            pair.check()
        # Use the already captured compatible probe, not a fresh selection lookup
        # that could switch builds halfway through the operation.
        metadata = parse_media_metadata(collect_tool_output(
            pair.probe.path, _probe_command(pair.probe.path, source.path)[1:],
            check_identity=check, cancel=cancel, abort=abort,
            max_bytes=MAX_PAYLOAD_BYTES, wall_timeout=30, reject_stderr=True,
        ))
        source.check()
        pair.check()
        if metadata.origin is None:
            raise ValueError("The file has no shared presentation clock")
        if audio_track >= len(metadata.tracks):
            raise ValueError("The selected audio track is not present in this file")
        track = metadata.tracks[audio_track]
        with _inspect_frames(source, pair, track, metadata.origin, cancel, abort, progress) as journal:
            with closing(_external_blocks(source, pair, track, journal, cancel, abort, progress)) as blocks:
                try:
                    yield TimedMedia(
                        metadata.origin, metadata.origin_kind,
                        tuple(AudioTrack(t.ordinal, t.stream_index, t.codec, t.channels,
                                         t.sample_rate, t.start) for t in metadata.tracks), blocks,
                    )
                finally:
                    abort.set()
