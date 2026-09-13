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
real codec fixtures; do not download codecs or access user media for tests.
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
reviewed. They neither discover nor run an executable and are not yet exposed
in the UI. The shared identity helper retains the existing FFmpeg behavior.
The packaged decoder's timing transport, bounded probe runner/metadata parser
and selection UI remain unfinished.

Current focused verification: **149 passed, 12 skipped** with the shared Python:

```powershell
& $py -m pytest tests/test_file_media.py tests/test_file_timeline.py tests/test_file_probe.py tests/test_audio_batching.py tests/test_file_streaming.py tests/test_file_decoder.py tests/test_file_transcription.py tests/test_transcript.py tests/test_privacy.py tests/test_config.py tests/test_repo_boundaries.py -o addopts= -q
```

The 12 skips are 11 existing external-codec fixtures without a selected test
FFmpeg and one Windows symlink-creation restriction. Independent review passed
the original 49 timing/batching tests, then the changed probe/helper and AAC
checks (**31 passed, 12 skipped**). No microphone, user recording, model download,
OBS application, new package or consumer-profile setting was used. Normal
Windows decoding and mutation checks compare each stat API against its own
baseline because Windows creation/change timestamps can differ across APIs.

### Packaged decoder design evidence and next work

The [FFmpeg format reference](https://ffmpeg.org/ffmpeg-formats.html) documents
that raw PCM has no timing and that framehash records packet timing, byte size
and content hash. A candidate cross-platform transport uses a private bounded
framehash journal, then an identical second decode to raw PCM with every packet
verified against that journal. Keeping the original rate during those passes
would allow each accepted contiguous run to be resampled and EOF-flushed
separately. This design is **not implemented or accepted**; double decoding,
bounded storage, process cleanup and real codec timing require verification.

The alternative tee approach avoids double decoding but needs two safely drained
private channels on Windows; mixing timing with arbitrary stderr diagnostics is
not acceptable. NUT requires a bounded audited parser absent from this package.
The [FFmpeg timestamp options](https://ffmpeg.org/ffmpeg.html) warn that preserving
input timestamps does not itself prove muxer output timing. Actual stream
inventory and a common origin need the separately selected
[FFprobe](https://ffmpeg.org/ffprobe.html). Validate retained origin/PTS against
independent synthetic fixtures, including negative starts, gaps and codec trim.

No existing FFmpeg/FFprobe executable was found on PATH, in the local test-tool
inventory or in the installed WSL distribution. Do not turn absent real-runtime
evidence into a packaged alignment claim. The next implementation must resolve
that fixture prerequisite while retaining the explicit-tool trust boundary.

## Non-goals and stop

No diarization, live OBS entry point, plugin distribution, recording automation,
new speech model, or Android work in this package. Keep the full app goal active.
Stop editing this package only when its end-user timing/selection/export behavior,
failure/cleanup checks, documentation and independent review meet acceptance.
