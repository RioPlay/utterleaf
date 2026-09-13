# Recorded-file timelines and aligned track transcripts

## Goal and area

Continue the recorded-file requirements in [the OBS audio design](obs-audio-design.md)
on `feat/recorded-file-timelines`, from reviewed provenance checkpoint `813cce7`
([PR #41](https://github.com/RioPlay/utterleaf/pull/41), all five desktop source
jobs passed in CI `34780495241`). Preserve that branch and its native receipts.

An explicitly selected recording must keep the common file clock through decode,
bounded recognition and subtitle export. A track starting late must remain late;
an internal timestamp gap must not pull later words earlier. Separate selected
tracks must share one origin, including the complete mix when it is present.
The complete work includes the packaged external-decoder path and useful stream
selection; a source-only decoder or passing internal layer is not completion.

Area: file timeline types/batching, PCM/PyAV/external decoding, track metadata and
selection, file recognition, explicit exports, related UI/CLI and focused tests.
Desktop only; no native OBS plugin or Android changes.

## Constraints

- No audio devices, ambient recording, OBS recording/routing changes, model
  downloads, automatic export or automatic decoder discovery/execution.
- Keep the existing selected-executable identity check and local-only media
  restrictions. An additional executable requires explicit selection and its own
  identity record; selecting FFmpeg does not authorize an unverified sibling.
- No bundled codec/license change. Development PyAV and the packaged external
  decoder are separate capabilities. Missing timing support must be explicit;
  never silently fall back to a zero-based timeline while claiming alignment.
- Keep audio memory bounded, cancellation/early-close cleanup reliable and
  recognition windows at most 30 seconds. Long gaps use timeline offsets, not
  huge silence allocations or model calls over invented audio.
- Use exact rational presentation times and exact consumed sample counts
  internally. Normalize once against a shared origin before creating model
  segments; rendering must not add/subtract that origin again.
- Preserve every decoded sample within an accepted presentation run. Reject
  ambiguous overlap/backward timing visibly. Timestamp granularity, missing PTS,
  pre-roll/codec priming, negative starts and discontinuities need stated policies
  and fixtures; do not guess that every unusual timestamp means silence.
- Do not infer speakers from channels, stream titles or assignment names. Keep
  media paths, audio and arbitrary decoder diagnostics out of ordinary logs.

## Acceptance

1. A common origin is selected once from validated container timing or a
   disclosed presentation-time fallback. Selection does not independently zero
   each track. Raw negative PTS can normalize correctly against a negative origin.
2. Timed decoding retains source PTS/time-base evidence, exact output sample
   counts and leading offsets. Resampler latency and flush samples survive;
   buffered samples cannot move across a timestamp gap into the next run.
3. Batching preserves each accepted sample once and keeps quiet-boundary behavior.
   Gaps flush a run; later segments retain the gap. Overlap, malformed timing,
   source mutation and invalid output cannot create a plausible aligned result.
4. Real synthetic media demonstrates unequal track starts, negative/nonzero
   origins, internal gaps, quantized timestamps, resampling, codec priming and
   missing/discontinuous timing. External decoder output is checked against
   independent timestamp evidence, not assumed correct from command flags.
5. File transcription uses timed batches and produces aligned SRT/VTT. Plain TXT
   keeps its documented plain-text behavior; any timestamped TXT choice must be
   explicit. Exports stay atomic, cancelable before publication where supported,
   and subject to existing overwrite/source-protection controls.
6. Users can inspect actual stream metadata and select the complete mix and
   optional other tracks without guessing from a 1–256 ordinal. Common-origin
   fallback/unsupported timing is visible. UI stays compact and accessible.
7. Existing PCM, decoder selection/forget, file cancellation, model-offline,
   timestamp validation and explicit export checks pass. Documentation separates
   source behavior, packaged behavior and genuine recording/quality acceptance.

## Implementation and verification

Start with decoder-neutral timed blocks and gap-aware batching, then verify the
installed resampler and implement timed decoding. Integrate recognition and
stream selection/export after the decoder contract is tested. Keep all remaining
acceptance open until the full workflow is connected and independently reviewed.

Use the shared virtualenv from this checkout; do not redirect its editable install.
Initial commands (extend for actual integration scope):

```powershell
$py = "C:/Users/unknown/Projects/Mindict/.venv/Scripts/python.exe"
& $py -m pytest tests/test_file_timeline.py tests/test_audio_batching.py -o addopts= -q
& $py -m pytest tests/test_file_streaming.py tests/test_file_decoder.py tests/test_file_transcription.py tests/test_transcript.py -o addopts= -q
```

Run focused UI captures/tests when its controls change. CI owns the full desktop
matrix and package checks. Use only explicitly verified local executables for
real codec fixtures and do not access user media. The initial local/WSL inventory
found no FFmpeg/FFprobe, so the development fixture prerequisite uses a release build from
an FFmpeg-listed Windows publisher, verified against its published checksum
before execution. Keep the tools and retained notices in ignored test tooling,
outside product packages, and use an isolated test selection record. This is
development setup; it does not authorize automatic discovery/downloads in the app
or add redistributed codecs to Utterleaf. Retain only the needed executables and
notices, remove the verified download archive, and record source/individual hashes.
Record exact commands, source hashes, fixture inputs and independent reviews.

## Current state

The old file path clears PyAV frame PTS and derives offsets only from decoded
sample count. The external decoder emits raw PCM without timing. Existing docs
correctly disclose the lack of cross-track synchronization.

A decoder-neutral timed batching layer and a PyAV development adapter are now
implemented internally and independently reviewed. They are not yet used by file transcription and do not establish
aligned-file product behavior. The batching/quiet-boundary checks currently pass
29 tests after fixing a review finding: writable output could previously change
the next batch's timestamp when a consumer resized its array between pulls.
Installed development PyAV is 18.0.0. Synthetic resampling confirmed delayed
output plus flush samples and showed that gap/overlap PTS propagate without
automatic repair; adapters must own discontinuity policy.

The development adapter uses the container origin in microseconds, or the
earliest start across **all** A/V streams only when each stream has valid start
metadata. It discloses this fallback, and fails if that common clock is unknown.
Individual audio frames require valid PTS and a time base no coarser than 1 ms.
Rounding smaller than one timestamp tick follows the run's exact sample count;
forward jumps of at least one tick flush and reset the resampler before admitting
later audio. Very small gaps that overlap after target-sample rounding fail
visibly; the adapter does not move the next run or drop the previous tail to fit.
Backward jumps of at least one tick, changing audio formats/timestamp units and decoded audio before the
common origin fail explicitly. Such pre-roll is not silently discarded. PyAV
applies codec skip/priming before returning frames; real codec fixtures must
verify that boundary rather than assuming packet and audible frame starts match.
The retained AAC/M4A regression has a negative initial encoded packet, origin
zero and first audible decoded PTS zero. It checks resampled duration against
the decoded frames. Final codec padding may remain in those decoded frames;
this is not a guarantee of sample-exact original-input duration for every codec.

Timing and resampler APIs follow the primary [PyAV time documentation](https://pyav.org/docs/stable/api/time.html)
and [audio API](https://pyav.org/docs/stable/api/audio.html); installed-version
synthetic fixtures are the behavioral evidence. Separate explicit FFprobe
selection/forget and hash revalidation APIs are implemented and independently
reviewed. They neither discover nor run an executable. The More formats dialog
now exposes explicit FFmpeg decoding and FFprobe inspection selections; the
shared identity helper retains the existing FFmpeg behavior. Timed decoder
transport, gap-aware resampling/build pairing, original-frame journaling,
aligned transcription and shared-clock export remain unfinished.

The current file window automatically inspects a newly chosen file in a
background worker, presents actual audio-stream metadata while retaining global
container indexes, and passes the selected audio ordinal to the existing
transcription call. PCM WAV inspection uses the standard-library WAV reader
without either external tool. This picker does not claim aligned timestamps:
subtitles remain relative to the selected track until timed decoder and export
integration are complete.

Initial committed-core verification: **149 passed, 12 skipped** with the shared Python:

```powershell
& $py -m pytest tests/test_file_media.py tests/test_file_timeline.py tests/test_file_probe.py tests/test_audio_batching.py tests/test_file_streaming.py tests/test_file_decoder.py tests/test_file_transcription.py tests/test_transcript.py tests/test_privacy.py tests/test_config.py tests/test_repo_boundaries.py -o addopts= -q
```

Those 12 skips were 11 existing external-codec fixtures without a selected test
FFmpeg and one Windows symlink-creation restriction. Independent review passed
the original 49 timing/batching tests, then the changed probe/helper and AAC
checks (**31 passed, 12 skipped**). No microphone, user recording, model download,
OBS application, new package or consumer-profile setting was used. Normal
Windows decoding and mutation checks compare each stat API against its own
baseline because Windows creation/change timestamps can differ across APIs.

### Packaged decoder design evidence and next work

The [FFmpeg format reference](https://ffmpeg.org/ffmpeg-formats.html) documents
that raw PCM has no timing. Real synthetic checks also show why a framehash
journal alone is insufficient: FFmpeg invents missing audio timestamps even
with `-copyts` and without `+genpts`. Timestamp evidence must come from original
decoded-frame PTS exposed by FFprobe with `-fflags +nofillin`, never a
best-effort timestamp fallback.

The current two-pass candidate is **not implemented or accepted**:

1. Explicitly selected FFprobe records original frame PTS and sample counts in
   a bounded private journal, validating stream time base/rate and frame format,
   channels and layout. FFprobe 9 does not expose per-frame sample rate or time
   base; requesting those fields does not make them available.
2. A separately selected, compatible FFmpeg build decodes that stream with
   `-copyts -reinit_filter 0 -xerror` to mono PCM at the original rate. Accept only
   successful exit, unchanged source checks and exactly the first pass's sample
   count. Partition bytes using the journal, then resample and EOF-flush each
   accepted contiguous run separately before recognition.

Real 48→44.1 kHz and mono→stereo ADTS changes fail under that command, but emit
a partial 22,528-byte prefix before failure. All output must therefore remain
provisional until final validation. Default reinitialization silently converts
the rate change. Single-frame or very short runs may not corroborate first-frame
rate metadata; their rejection/unsupported policy remains to be finalized.
Build compatibility, frame-journal limits, per-run resampling, cleanup and
decoder determinism remain implementation/review gates. Exact sample counts
are not a cryptographic binding between the two decoder passes.

Real FFprobe 9 fixtures establish the next frame transport:
`-fflags +nofillin -select_streams a:N -show_frames -show_entries frame=stream_index,pts,nb_samples,sample_fmt,channels,channel_layout:frame_side_data= -of compact=p=0:nk=0:escape=c`.
Keep the existing local-input/protocol restrictions around this output selection.
Rows preserve a nonzero MKV start and a 100 ms gap; M4A encoded priming starts at
packet PTS -1024 while the first decoded frame has PTS 0. Raw AAC explicitly
prints `pts=N/A`. Output field order differs from request order, so the future
bounded parser must use keys, reject duplicates/missing/unknown fields and never
substitute best-effort timestamps. No paths, tags or side-data appeared in these
synthetic rows. The fixture receipt is retained locally as
`.grok/recorded-file-timelines/external-design/compact-frame-receipt.json`.

The alternative tee approach avoids double decoding but needs two safely drained
private channels on Windows; mixing timing with arbitrary stderr diagnostics is
not acceptable. NUT requires a bounded audited parser absent from this package.
The [FFmpeg timestamp options](https://ffmpeg.org/ffmpeg.html) warn that preserving
input timestamps does not itself prove muxer output timing. Actual stream
inventory and a common origin need the separately selected
[FFprobe](https://ffmpeg.org/ffprobe.html). Validate retained origin/PTS against
independent synthetic fixtures, including negative starts, gaps and codec trim.

The development fixture prerequisite is now satisfied by the FFmpeg-listed Gyan
9.0.1 essentials build, verified against its publisher's archive checksum before
execution. Only FFmpeg, FFprobe and their notices remain under ignored `.grok/tools`;
the download archive was removed. This is development evidence, not bundled code,
a publisher signature, or a packaged alignment claim.

The current probe runner limits JSON output to 1 MiB and 256 streams, rejects
nonregular/empty sources before opening, checks ordinary source changes, and
uses a 30-second deadline with cancellation and process cleanup. PCM WAV inspection
needs neither tool and uses an explicitly zero-based sample clock, not BWF time
references. The picker checks the ordinary file signature before and after
recognition and discards a changed result. These pathname checks do not establish
content authenticity or eliminate malicious replacement races; held-source
binding in the full timed workflow remains separate work.

The real-tool affected regression passes **241 tests, 3 skips** (Windows-only
symlink permission, POSIX replacement semantics and FIFO cases). The command uses
both `UTTERLEAF_TEST_FFMPEG` and `UTTERLEAF_TEST_FFPROBE` set only in the test shell:

```powershell
& $py -m pytest tests/test_file_probe.py tests/test_file_metadata.py tests/test_file_inspection.py tests/test_file_decoder.py tests/test_file_media.py tests/test_file_timeline.py tests/test_file_streaming.py tests/test_file_transcription.py tests/test_audio_batching.py tests/test_transcript.py tests/test_obs_transcription.py tests/test_privacy.py tests/test_config.py tests/test_repo_boundaries.py -o addopts= -q
```

The added ten-format inspection matrix caught a raw AAC regression: valid
audio format metadata had no container or stream start. Relative transcription
now explicitly allows a missing common origin as `None`/`unavailable`; it never
invents zero or uses a partial set of stream starts. Probe/parser defaults still
require a common origin for future timed callers. Malformed present timing stays
invalid in both modes. All ten real format fixtures now pass.

CI `34782542414` at `33729f7` passed four desktop jobs and Linux X11 tests, but
failed the forced-Wayland repeat on an existing OBS close assertion. Capture
close is intentionally nonblocking; the test now waits for its actual writer
before asserting the backing file is closed. The complete OBS transcription
test file passes locally. A new source CI run is required after this repair;
the failed run is not described as green.

The UI/CLI regression now passes **45 tests**. Independent review covers 19 file
window cases and the decoder dialog, including queued cancellation,
duplicate jobs, ordinary source changes, stale queues after close, explicit
selection/forget and failed worker startup. Seven synthetic captures from
`tests/capture_file_ui.py` cover default and compact windows. Long executable
paths remain selectable without expanding the dialog beyond its compact bounds.
These are source-level Windows Tk checks; no new package, actual OBS instance,
personal media, microphone or consumer-profile selection was used.

CI `34784668390` at `8e9e9a9` passed Windows and both platform builds. The two
compact-dialog assertions failed on macOS and Linux because native text metrics
clipped controls. Setup text is now shorter and each tool's Choose/Forget actions
share a row. The compact test checks all three platform instruction variants;
its real window bounds assertions are retained. Native CI must be rerun for this
layout correction; local Windows checks do not replace that evidence.
A retained controlled Windows experiment with 12-point body/button text also
fits at 560×500 after reducing excess spacing. This is a narrow layout check,
not arbitrary font-size or native macOS/Linux accessibility acceptance.

## Non-goals and stop

No diarization, live OBS entry point, plugin distribution, recording automation,
new speech model, or Android work in this package. Keep the full app goal active.
Stop editing this package only when its end-user timing/selection/export behavior,
failure/cleanup checks, documentation and independent review meet acceptance.
