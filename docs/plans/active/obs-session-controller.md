# OBS session controls and live local transcription

## Goal and area

Connect the authenticated OBS control and audio transports to a responsive,
explicit session workflow and bounded local transcription while capture is still
running. Preserve the complete requirements and release gates in
[OBS audio design](obs-audio-design.md). Work starts on
`feat/obs-session-controller` from reviewed Disarm checkpoint `663d3be` (draft
PR #39; all five desktop CI jobs passed).

Area: a desktop controller, incremental temporary-audio reads, local recognition
and transcript ownership, a narrow read-only plugin compatibility request, and
the visible session adapter. Desktop and Android source/releases remain separate.

## Constraints

- Disabled at startup. Connecting and checking compatibility never prepare a
  session or capture audio. Only deliberate Arm while authenticated OBS is idle
  can create one session; no reconnect, rearm, startup or already-live capture.
- Retain the authenticated process lease before one-use Prepare. Native Arm
  remains the authority for a stream-start race after the idle observation.
- One worker owns pipe I/O and receiver mutation; a separate worker handles
  serialized control events. A pipe read deadline is terminal, not a polling API.
  Native Start carries the authenticated one-use session identifier and is sent
  only after the full Arm reply and a subsequent native frontend start. It is the
  epoch authority. Untagged WebSocket lifecycle events can arrive late and must
  neither authorize nor stop a different native session. No cross-channel wait
  or unbounded frame queue is needed.
- Only ordinary control disconnection may degrade an already active healthy
  audio session. Identity, authentication, malformed protocol and OBS exit remain
  terminal. Disarm and hard cancellation remain available without WebSocket.
- Incremental reads expose only committed file samples. The audio callback never
  waits on disk; recognition never blocks pipe capture. Audio windows, preview
  text and worker queues have fixed bounds, with per-bus source timestamps intact.
- A storage or audio gap yields a visibly incomplete contiguous prefix. Cancel
  discards owned temporary data. No automatic paste, export, recording changes,
  model download, credentials in backups, or microphone capture in this mode.

## Acceptance and verification

1. Repeated compatibility checks are inert, strictly versioned, and cannot consume
   authorization or Arm. Unknown/malformed replies fail closed.
2. Full idle/connect/Arm/start/audio/End and no-audio Disarm work through the
   production controller in deterministic fixtures. Tests exercise both channel
   orderings, queued Start plus PCM, stale events, duplicate commands, cleanup,
   cancellation and terminal races.
3. A healthy active audio pipe survives ordinary control loss with visible
   degraded status. Identity/protocol failures and pre-start loss stop safely.
4. Reads and local recognition occur before End, preserve separate bus offsets,
   drain a final partial window, and remain bounded during a long or slow take.
   A late storage failure cannot promote a prefix to a complete transcript.
5. UI controls expose connection, Arm, waiting, active, stopping, complete,
   incomplete and error states with a clear cancel/discard path. UI calls never
   perform native I/O or wait for recognition; stale workers cannot update a new
   session. Verify the rendered layout and keyboard/focus behavior.

Run focused Python tests for each new module, then the affected OBS, capture-store,
continuous-dictation and transport suites. Native compatibility changes require
the existing strict native fixtures, linked build, canonical test driver and
headless refusal smoke. Record exact commands and final evidence here. Independent
review examines contracts, source, tests and actual output.

## Authority correction found during review

An OBS WebSocket event revision is assigned when the message is parsed; it cannot
prove the event was emitted after native Arm. A complete older lifecycle can be
queued while preparation and Arm run. The native runtime already supplies the
missing proof: it sends the entire accepted Arm reply before capture scheduling,
requires ordered subsequent native STARTING/STARTED, and sends Start with that
same session only after attachment and aligned first PCM blocks. Independent
source review confirmed those paths in `plugin_state.c` and `audio_stream.c`.
The controller therefore uses the authenticated native Start/End for this epoch;
WebSocket remains mandatory for initial authentication/idle observation and for
detecting identity, protocol and OBS Exit failures. This replaces the earlier
proposed gate based on an untagged WebSocket STARTED message.

## Recognition and view review

Independent recognition review corrected a forced-CPU default and output limits
that originally ran only after the model generator had been exhausted. The
default adapter now honors the saved device on an offline configuration and
enforces segment count, per-segment bytes and total text bytes during iteration.
It closes the iterator before releasing the inference lock on every exit.
Cancellation starts at most one journal-cleanup worker; a slow close or active
reader keeps `wait()` false until the requested cleanup finishes.
If cleanup cannot start or closing storage fails, completion reports a sanitized
failure instead of claiming the data was discarded. Repeated cancellation cannot
overwrite that failure, and discarded or empty preview states cannot export.

The view forwards explicit actions to an injected adapter. It performs no
capture, model loading, pairing import or export itself. Password fields clear
after submission and on closure; selecting preview text does not export the X11
PRIMARY selection. Review corrected premature authentication wording, hidden
focus targets and a transcript squeezed out by inactive controls. Capture
controls collapse after Arm, and terminal states retain readable preview,
export intent and discard controls. Screenshot helpers reject unmapped, empty
or incorrectly sized captures rather than treating them as visual evidence.

## Verified checkpoint

Final local verification passes **647** focused backend tests, **41** real Tk
tests, all **51** canonical native verification commands, the **24**-command
linked build and headless refusal smoke. Independent implementation review is
clear, including the final cleanup-failure path. The receipt audit matches all
**443** recorded source, SDK, tool, runtime, generated-file, artifact and log
hash comparisons. It is development provenance, not a fully pinned build claim.

The UI was rendered and inspected in nine synthetic states: disabled, ready,
armed, active, control-disconnected and incomplete at 840×720, plus disabled,
active and control-disconnected at 560×520. Normal active/degraded/incomplete
previews retain at least 140 pixels of height; compact previews retain at least
100 pixels. Tests also cover the macOS-clamped 840×645 capture states and
the actual Connect-to-terminal transition as well as direct state fixtures.
These are native Tk view checks with injected actions, not actual OBS use.

Commands from the owning worktree (existing local toolchain and pinned headers):

```powershell
$py = "C:/Users/unknown/Projects/Mindict/.venv/Scripts/python.exe"
$toolchain = "C:/Users/unknown/.local/llvm-mingw-20260616-ucrt-x86_64"
$obsBin = "C:/Program Files/obs-studio/bin/64bit"
$headers = "C:/Users/unknown/Projects/Mindict/.grok/obs-native-build/headers"
$output = "C:/Users/unknown/Projects/Mindict/.grok/obs-session-controller"
& $py native/obs-plugin/tools/build.py --toolchain $toolchain --obs-bin $obsBin --headers $headers --output "$output/build"
& $py native/obs-plugin/tools/smoke.py --build "$output/build"
& $py native/obs-plugin/tools/test_native.py --toolchain $toolchain --build "$output/build" --headers $headers --output "$output/verification"
& $py -m pytest tests/test_obs_session_ui.py -o addopts= -q
& $py tests/capture_obs_session.py --output "$output/ui"
```

Local evidence is under `.grok/obs-session-controller/`: the build and smoke
receipts in `build/`, canonical `verification/test-receipt.json`,
`hash-audit.json`, `ui-verification.json`, and nine `ui/*.png` captures. The
draft PR runs the broader desktop CI. No consumer OBS profile, pairing state,
microphone or model was accessed during this verification.

Initial CI at `ce25987` passed Windows and both Linux/macOS package builds.
Linux tests exposed a reader fixture's unscheduled retry loop; the corrected
fixture uses events to hold one read, prove the other returns unavailable, then
verify both absolute offsets after release. macOS tests exposed assumptions
about requested window size despite display clamping. The second CI run passed
Linux tests but exposed a 645-pixel-high macOS window between the previous compact
threshold and the space required by the full layout. Configure events and refresh
now share idempotent layout synchronization against actual dimensions. The full
layout starts at 720 pixels; shorter windows use the compact layout, and changing
density preserves state-dependent control visibility. Assertions use actual
geometry and preserve the normal and compact transcript readability requirements.
No platform skips or lowered readability requirements were added.

## Remaining product gates and stop

This work must not describe post-End decoding as live transcription. The complete
workflow still needs accurate primary/additional-mix metadata and routing-change
boundaries, recorded-file timeline handling, actual OBS frontend/audio and load
acceptance, and the separate native distribution review. Synthetic tests and a
render do not establish those gates. Do not publish a plugin or expose a live
capture entry point before its complete capture contract is satisfied.

Stop editing this package when its implemented acceptance checks and independent
review pass and the roadmap matches the verified scope. Keep the full desktop and
original Android completion goal active until their actual release gates pass.
