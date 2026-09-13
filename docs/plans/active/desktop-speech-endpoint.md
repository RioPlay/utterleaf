# Optional desktop speech-end stopping

## Goal

Offer optional local speech-end stopping during an explicitly started dictation,
with an adjustable pause and a separate choice to review or insert automatically.
Hold-to-talk and toggle recording remain available. No ambient listening or
automatic rearming follows a completed take.

## Area

Desktop `audio.py`, `audio_owner.py`, `app.py`, local configuration/Settings and
focused capture/session/settings tests. Android remains a separate implementation.
The [dictation formatting pass](desktop-dictation-completion.md) is preserved.

## Current evidence and decision

Before this implementation the recorder tracked callback liveness and the capture
bound, without live speech-end detection. The CTranslate transcription path already
applied faster-whisper VAD after capture for sufficiently long takes; that separate
filter does not provide live stopping.

The inspected local faster-whisper 1.2.1 installation contains
`silero_vad_v6.onnx` (1,245,151 bytes) and uses onnxruntime 1.28.0. Its local CPU
session uses one thread. Desktop packaging already collects faster-whisper data
and runtime notices. These observations establish a possible reuse path, not a
verified streaming interface, complete model provenance audit or new feature.
The [upstream VAD documentation](https://github.com/SYSTRAN/faster-whisper)
describes filtering with Silero; [Silero's documentation](https://github.com/snakers4/silero-vad)
describes its runtime and licensing. The exact installed identity, notices and
bounded checks are recorded in the [resource review](../../desktop-vad-resource.md).

Prefer a bounded worker using the existing local VAD to a volume threshold
marketed as speech recognition. The inspected model wrapper batches 512-sample
frames and resets recurrent state per call; design and test its endpoint adapter
explicitly. Do not assume OpenVINO has the same path. Missing/unsupported detector
availability must leave manual stopping usable, never download or silently switch
to a weaker detector.

## Constraints and acceptance

- Disabled by default; explicit start for each bounded take. No microphone open
  while idle, no periodic background audio scanning and no automatic restart.
- Separate **stop after speech** and **insert after automatic stop** choices.
  Default automatic-stop action is review. Explain the pause threshold and provide
  manual stop/cancel throughout. Thinking pauses, quiet speech, noise and other
  speakers need named-device evidence; no detector promises perfect intent.
- Off the audio callback: bounded recent samples, one coalescing worker, bounded
  inference cadence and per-session state. Never retain raw audio as telemetry.
- Silence before speech must not manufacture a take. Require validated speech
  onset, then a sustained speech-free interval. Keep the existing hard capture cap.
- Snapshot settings at session start. Release, toggle stop, Esc, quit, permission
  or device loss and target changes cancel pending endpoint work. Delayed callbacks
  cannot finish a later recording. Auto-stop must reset hotkey/toggle state so the
  next deliberate press works immediately.
- Review performs no paste or edit command. Reuse temporary recovery only if its
  UI provides a clear review/insert/discard path; do not label hidden retained text
  a finished review experience.
- Automatic insertion uses normal target/clipboard/receipt guards. No Send/Enter,
  automatic command execution or speculative delivery after a target mismatch.
- Save/reopen/restart, cancellation and Reset to defaults preserve user data.
  Display unavailable/error state without blocking ordinary manual dictation.

## Verification

Use synthetic/public fixed audio and a stub detector for deterministic lifecycle
tests. Check speech onset/quiet interval, pause reversal, no-speech sessions,
worker bounds, delayed callbacks, cancellation/races, manual/toggle state, review
without edits and guarded insertion. Add actual local-model fixture tests without
microphone capture, then focused config/Settings persistence/reset checks and
required desktop checks. Physical latency/noise/accent acceptance is separate.

## Non-goals and stop

No continuous hands-free assistant, cloud VAD, new arbitrary model loader,
permission expansion or claim of Android support. Stop the first implementation
slice after its exact session, review and cancellation contracts pass independent
review; defer additional detectors/backends to separate measured work.

## Status

Implementation resumed September 12 after the user's explicit continuation.
The adapter verifies the reviewed asset, analyzes at most eight seconds of recent
audio outside the callback and uses captured sample counts for pause timing.
Four consecutive speech frames establish onset. Recorder snapshots return a
matching tail/count without concatenating the whole take.

The Settings/lifecycle/review integration is implemented in source and has passed
independent review. Automatic insertion uses the original supported native field,
text and caret; unsupported or changed fields require visible review and Copy.
Review retains the existing two-minute recovery limit and has explicit
Copy/Insert/Discard controls. Parent/child IPC carries no transcript in arguments,
files or logs; startup is bounded and child failure leaves recovery available.

Independent review found and verified fixes for delivery cancellation guards,
recovery-generation races, obsolete review controls, and child/loader startup
failures. Its final focused run passed 223 app, review, interruption, Settings,
configuration, backup and hotkey tests. Review-child EOF and conflicting CLI
actions fail closed; Settings and review windows were captured and inspected.

The final integrated command `.\.venv\Scripts\python -m pytest -ra` passed
827 tests with 12 skips in 30.40 seconds: eleven explicit FFmpeg-fixture
requirements and one unavailable Windows symlink privilege. All Tk/UI checks ran
and passed in this final run. An earlier run had three intermittent Tk setup
skips; their cause remains undiagnosed and should be investigated if they recur.
These checks establish the named source behavior, not physical-microphone
acceptance, a frozen binary or an installed-app upgrade. The broader delivery
timeout/cancellation work remains a separate follow-up in the desktop roadmap.
