# Continuous desktop transcription and OBS

## Goal

September 12 user direction: remove the two-minute recording countdown; explicitly
started dictation continues until manual stop/cancel or separately enabled
speech-end stopping. Import long recordings without the current 10-minute/256 MiB
restriction. Add an explicitly enabled OBS workflow for the complete stream mix,
with optional separate transcripts where distinct audio tracks are available.
No arbitrary total-duration replacement limit satisfies this request.

## Area and constraints

Desktop capture, recognition, file decoding/review/export, settings and OBS
integration. Keep Android work separate. No ambient microphone capture, process
presence triggering recording, copied OBS code, automatic model/codec installation,
hidden audio upload, automatic paste of live captions or transcript logs.
Bound memory and pending work independently of elapsed duration. Any temporary
audio storage needs an explicit documented privacy/lifecycle design before use;
do not simply accumulate the current Recorder chunk list forever. Preserve all
audio or visibly report an incomplete result, never silently drop queued chunks.

## Acceptance

- Hold/toggle recording has no default countdown or duration cutoff. Explicit
  Stop, Esc, quit, capture failure and optional speech-end behavior remain sound.
- Long capture and file recognition use bounded audio windows, correct global
  timestamps and cancellation. Verify beyond 120/250/600 seconds with synthetic
  data without opening a microphone. Exercise slow recognition, resource failure,
  cleanup and chunk-boundary speech quality; retain exact evidence and limits.
- File review and explicit TXT/SRT/VTT export handle long recordings. Separate
  track selection/export must not confuse stereo channels with distinct tracks,
  duplicate the full mix or imply speaker identity from a mixed waveform.
- OBS connection is local, explicit and authenticated, disabled by default, with
  visible armed/active/paused/error status and immediate manual disarm. Starting
  OBS alone is insufficient. Reconnect must not silently start a fresh capture.
- Stream events and audio transport are separately verified. Live complete mix
  and available isolated tracks must actually arrive; websocket events alone are
  not evidence of audio capture. No OBS credentials in logs or generic backups.
- Persistence/cancellation/reset and app/UI regression checks pass; reset retains
  user recordings, models and exports. Independent review and updated guides
  required. Physical OBS/microphone, other-desktop and release gates stay explicit.

## Current evidence and remaining work

The user explicitly authorized temporary audio files for bounded memory after
this plan was opened. `capture_store.py` now uses stdlib `TemporaryFile`, an
8 MiB pending queue, at most a 1 MiB submitted block, and one disk writer. The
desktop Recorder opts into this store while retaining only its eight-second
preview/endpoint tail; stopped recordings transfer ownership to the recognition
worker. Recognition reads 30-second windows, and completion/cancel/quit/queued
take cancellation closes the owned store. Short writes and disk errors retain
only complete stored samples and mark the result incomplete; incomplete results
use recovery only. No encryption or forensic-erasure claim. Raw float32 storage
uses about 220 MiB/hour at 16 kHz or 660 MiB/hour at 48 kHz. Creation and periodic
writer checks preserve a best-effort 256 MiB free-space reserve; racing writers or
disk failures are still handled as incomplete capture. Remote or unverified temporary
filesystems are refused. More efficient storage remains worth evaluating without weakening
audio fidelity or resource/licensing constraints.

The app no longer schedules a capture deadline, including with legacy positive
`max_seconds` values. That field remains for config compatibility, defaults to 0,
and does not control the continuous path. Explicit stop/cancel and optional
speech-end handling remain. The first integrated check passed **245 tests in
19.17 seconds**:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_capture_store.py tests/test_continuous_capture.py tests/test_audio.py tests/test_app.py tests/test_speech_end_app.py tests/test_delivery_cancellation.py tests/test_audio_interruption.py tests/test_app_interruption.py tests/test_settings_ui.py
```

Capture-phase checks after config/cancellation-lock/free-space changes:

- Full desktop `.\.venv\Scripts\python.exe -m pytest`: **984 passed, 14 skipped
  in 65.34 seconds**. Skipped cases do not establish device/codec acceptance.
- Focused capture/app/interruption/endpoint/cancellation bundle: **214 passed**.
- A native harmless subprocess with synthetic audio passed abrupt-termination
  cleanup; the Windows temporary recording was absent after the child exited.
- `.\.venv\Scripts\python.exe tests/capture_settings.py` completed without a
  microphone or user-config writes. Normal and compact Dictation views inspected:
  the new guidance wraps, controls remain reachable, no clipping found.
- `git diff --check` passes.

Independent capture review identified an incomplete locality check: UNC spelling
does not detect mapped drives or mounted network filesystems. The corrected reusable
guard checks Windows drive type, macOS `MNT_LOCAL` with architecture-specific ABI,
and Linux owning-mount metadata against a conservative native-filesystem allowlist,
before and after path resolution. Ambiguous overmounts, unknown types, FUSE and
overlay are refused. Inspection/create/writer-start errors now produce storage
guidance, and created handles close if writer startup fails. Independent re-review
also corrected Intel versus Apple Silicon symbols and portable/mount-stack tests.
Focused capture/locality/continuous tests pass **42 cases**. Native macOS/Linux
mounts and a concurrent OS mount replacement remain outside this Windows evidence.

API sources: [Windows drive type](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-getdrivetypew),
[Apple filesystem layout](https://github.com/apple-oss-distributions/xnu/blob/main/bsd/sys/mount.h),
[Apple symbol selection](https://github.com/apple-oss-distributions/xnu/blob/main/bsd/sys/cdefs.h),
[Linux mount metadata](https://www.kernel.org/doc/Documentation/filesystems/proc.txt).

These are synthetic capture and mocked recognition checks, not physical
microphone, word-accuracy, OBS or packaged-release claims. Further stress testing,
long-speech word accuracy at batch boundaries and device/resource stress remain.
In particular, a 30-second
waveform window can split an utterance; count/timestamp tests are not evidence of
word-perfect boundary recognition. Recognition currently follows explicit stop;
live incremental recognition/export is additional work.

### File streaming increment

The unreleased file workflow now decodes incrementally and recognizes windows of
at most 30 seconds, with no total file-size or duration cap. PCM WAV uses one-second native
blocks; selected FFmpeg output uses a bounded pipe queue; source PyAV emits bounded
resampled frames. All early exits close their iterator and owned decoder process.
FFmpeg's 120-second limit now measures decoder inactivity and excludes consumer
recognition time. The legacy array-returning helpers retain their prior limits for
compatibility; the app no longer uses those helpers.

`transcribe_file` offsets subtitle segments by consumed sample count. A model end
time beyond the current batch is clipped to its actual duration without dropping
the text; a start at or beyond the batch end, or otherwise invalid timing, fails
the job. Decoder/model
failure discards the job rather than returning a complete-looking prefix. The
audio buffer is bounded; transcript text and subtitle segments grow with output.
CLI/UI track selection is per job, using actual audio stream ordinals; this is
not automatic speaker separation or a shared container timeline. Container offsets
and discontinuities remain unsupported and explicitly documented.

Focused decoder/transcription/streaming/CLI checks: **71 passed, 11 skipped in
2.73 seconds** (`tests/test_file_decoder.py tests/test_file_transcription.py
tests/test_file_streaming.py tests/test_file_cli.py`). Evidence includes a real
601-second PCM file, bounded producer/recognizer interleaving, subtitle timestamp
carry, early/late failure, a harmless native PCM-producing subprocess, and two
distinct PyAV FLAC tracks. The 11 skips require an explicitly selected FFmpeg
codec fixture. These
checks do not establish long-speech accuracy or a packaged release. Independent
source review found no remaining file-pipeline blockers. Per-job track selection
in the native Tk file window passed **13 UI tests**; the compact 760×560 synthetic
window was inspected with all guidance, preview and footer controls visible.

Pre-batching integrated `.\.venv\Scripts\python.exe -m pytest`: **1,046 passed, 13 skipped
in 79.61 seconds**. A later status-only fix uses Recording interrupted for both
storage and device interruptions, preserving the actual cause and recovery hint
and removing unconditional microphone-reconnect advice. Its app/continuous/
interruption/indicator bundle passed **98 tests in 3.90 seconds**. This small
follow-up did not change capture, inference or delivery control flow. Independent
review confirmed the new badge's tray, IPC and native/Tk indicator routing.

### Speech boundary evaluation

An offline CPU/int8 evaluation used the already installed `base.en` CTranslate2
model (local revision `3d3d5dee26484f91867d81cb899cfcf72b96be6c`) and the pinned
public whisper.cpp JFK fixture (`artifacts/media-formats-ci/fixture-provenance.json`;
WAV SHA-256 `59dfb9a4acb36fe2a2affc14bacbee2920ff435cb13cc314a08c13f66ba7860e`).
Eight repetitions produce 88 seconds and 1,408,000 mono 16 kHz samples. No model
or fixture was downloaded, no microphone opened, and networking remained disabled.

The fixed-window path retained all samples in `[480000, 480000, 448000]` windows
and had zero deletions in the normalized comparison. It did repeat two words,
“for you”, just before 30 seconds; the normalized alignment showed no insertion
or deletion at the 60-second sentence split. Normalized
word edit distance was 7/176 (0.03977) for streaming versus 11/176 (0.0625) for
whole-waveform recognition, largely because of `ask`/`asked` substitutions. Better
aggregate distance is not proof that fixed boundaries are harmless. All 16
streamed segments were ordered and within the 88-second input.

Reproducible local scratch: `.grok/evaluate_file_boundaries.py` and
`.grok/boundary-quality/` evidence/alignment JSON. This single repeated male-speech
fixture and one model do not establish general quality, multilingual behavior or
real-time performance.

The shared quiet-boundary batcher is now integrated in both stopped-capture and
file recognition. Its 30-second working buffer searches the final five seconds
for the latest run of at least 120 ms with RMS at most 0.01, measured in 20 ms
frames. Without a qualifying pause it uses the 30-second limit. It preserves
every sample exactly once, including the remainder after a quiet boundary, and
never deletes or deduplicates transcript words. It accepts bounded, finite mono
float32 blocks; audio input buffering does not grow with the audio duration.
Transcript text and subtitle metadata still grow with output.

Two integrated production-route runs used the same offline fixture/model above.
Both consumed windows `[430400, 454720, 425280, 97600]` with boundaries at
26.90, 55.32 and 81.90 seconds, totaling all 1,408,000 samples. Both produced
176 normalized words against the 176-word reference with zero insertions or
deletions: the earlier repeated “for you” was absent. Run 1 had seven substitutions
(edit distance 0.03977),
and run 2 had three (0.01705); both differed only in `ask`/`asked`. Timestamp
segments were ordered, non-overlapping and within the 88-second input. The
different substitution counts show native model variation; no general accuracy
improvement is claimed. Original fixed-boundary evidence is preserved alongside
both runs in `.grok/boundary-quality/`; the current harness is
`.grok/evaluate_integrated_batching.py`.

The evaluation also exposed native model end padding (27 seconds for a 26.58-second
batch). The reviewed timing policy above clips such ends without inventing audio
or discarding words. Tests cover that case, invalid starts, exact quiet-boundary
sample retention and global timestamp offsets. A pre-inference cancellation
check prevents starting the next model call when cancellation arrives with a
yielded batch; an active native inference call must still return before stopping.
The focused batching/file/continuous/interruption bundle passed **87 tests in
2.32 seconds** after this integration.

Final integrated `.\.venv\Scripts\python.exe -m pytest`: **1,068 passed, 13 skipped
in 41.99 seconds**. Independent re-review cleared the batching/timestamp integration
and the cancellation handoff test; it found no remaining blocker in this increment.
The skips remain unverified cases, not passing codec/device evidence.

### One-hour synthetic storage and batching check

`.\.venv\Scripts\python.exe .grok/evaluate_one_hour_capture.py` exercised the
current `CaptureStore` and shared batcher using 14,400 amplitude-coded blocks of
12,000 float32 samples at 48 kHz. The 3,600-second input used a real 691,200,000-byte
temporary file. The producer waited for the writer when its queue exceeded 4 MiB;
peak observed queued data was 4,224,000 bytes, below the 8 MiB bound. No storage
error occurred. Free space before the run exceeded the file size plus the 256 MiB
reserve.

Incremental read/resampling produced exactly 57,600,000 mono 16 kHz samples in 120
windows of at most 30 seconds. Every amplitude-coded block stayed in order; the
maximum measured interior amplitude error was 1.19e-7. The harness discarded each
window after checking it. Explicit `store.close()` closed the handle and removed
the temporary path. The app uses this method in its `finally` path; iterator
exhaustion alone does not close an owned store. Small aggregate evidence is
retained in `.grok/one-hour-capture-evidence.json`.

This was accelerated synthetic storage/resampling/batching, not an hour of live
microphone recording or model execution. No RSS measurement was collected because
the optional measurement dependency was absent; bounded queue/sample counts are
not a measurement of total process memory. Real-time load, native model memory,
physical microphone behavior and longer-session stress remain open.

The [OBS design contract](obs-audio-design.md) records official API evidence and
an original plugin/audio transport proposal. Live OBS integration remains
unimplemented; stream events alone do not deliver PCM audio.

OBS's official [remote-control guide](https://obsproject.com/kb/remote-control-guide)
documents built-in websocket control since OBS 28. The official
[protocol](https://github.com/obsproject/obs-websocket/blob/master/docs/generated/protocol.md)
provides stream-state events and authentication. Its
[multiple-track guide](https://obsproject.com/kb/multiple-audio-track-recording-guide)
documents recording audio tracks. Live audio transport and original integration
remain to be implemented and verified. Speaker separation from one mixed track is
a different, unimplemented capability.

## Verification and stop

Run affected capture/app/config/settings tests for continuous dictation; decoder,
file transcription, UI, CLI and export tests for long files; new synthetic OBS
protocol/audio/session tests and explicit device acceptance for OBS. Record exact
commands and actual outcomes as each increment lands. Stop editing an increment
only after its named acceptance checks and review pass; this plan remains active
until all three requested workflows meet their requirements.
