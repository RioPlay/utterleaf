# Desktop roadmap

[Roadmap hub](roadmap.md) · [Mobile roadmap](mobile-roadmap.md)

Scope: Windows, macOS, and Linux desktop application only.

Updated September 12, 2026. Priorities follow the
[offline STT user research](offline-stt-user-research-2026-09-08.md).
This is an ordered development plan, not a promise of release dates.

See [platform testing](platform-testing.md) for current Windows/WSL results and
the real-device checklist, including macOS testing.

The product goal is simple: press a key, speak, and get dependable text in the
intended field, with understandable local processing and minimal interruption.

## Planned follow-up

### Release priority: Windows 0.4.6 RC1

The [Windows prerelease plan](plans/active/desktop-prerelease.md) prepares the
completed dictation, long-file, speech-end, Markdown and delivery improvements
for an unsigned Windows x64 CPU preview. The candidate version is `0.4.6rc1`;
publication and artifact verification are separate gates. Stable v0.4.5 remains
the default download. Android and live OBS work continue after this bounded release.

Historical source receipts below describe their original verification stage;
they are not claims that this candidate has already shipped. The preview plan
records the final artifact and test evidence.

### Active: continuous recording, long files and OBS

The [continuous transcription plan](plans/active/desktop-continuous-transcription.md)
tracks the September 12 request to remove the recording countdown, transcribe long
recordings and optionally follow OBS streams with combined or separate tracks.
The first continuous microphone path is now in unreleased source: no scheduled
duration cutoff, bounded write queue and preview tail, automatic temporary-file
cleanup and recognition windows of at most 30 seconds. Synthetic checks cover 251-second
capture at three input rates, 601-second storage/recognition, cancellation, queue
pressure, storage failure and recovery-only incomplete results. The first
integrated run passed 245 tests, including affected Settings tests; that capture
phase's full desktop run passed **984 tests with 14 skips**. A native synthetic subprocess
termination check confirms temporary-file cleanup. Free-space checks maintain a
best-effort 256 MiB reserve; normal/compact Settings guidance passed visual review.
Independent review and fixes now enforce filesystem locality instead of checking
only UNC spelling, and report storage-inspection/create/startup failures accurately.
Real microphone, general long-speech quality and release checks remain.
The imported-file source path now streams decoding into bounded recognition
windows without total-duration/file-size limits, carries subtitle times across
batches, and selects actual audio tracks per job. The focused decoder/transcription/
streaming/CLI bundle passed **71 tests, 11 explicit codec-fixture skips**; independent
review and 13 file-UI tests pass, with the compact view inspected. This includes a real 601-second PCM file and
separate synthetic container tracks, not long-speech accuracy or release proof.
Live OBS remains unavailable. Its [design contract](plans/active/obs-audio-design.md)
separates authenticated stream events from actual PCM transport. The first
[protocol and receiver components](plans/active/obs-audio-implementation.md) now
cover consent/order guards, separate-bus temporary storage, timing, cancellation
and incomplete recovery. Reviewed internal components also provide read-only
WebSocket control, mandatory Windows process identity before authentication and
the [native audio pipe client](plans/active/windows-obs-audio-pipe.md). Actual
synthetic Windows peers verify IPv4/IPv6 process attribution, bounded I/O cleanup,
audio delivery after TCP loss and wrong-process rejection with zero secret bytes
received. This checks the originally attributed process and current path/file
identity; it is not historical loaded-image attestation.

There is no app entry point. Actual OBS enrollment, the original server plugin's
restrictive DACL/client authentication, atomic arming/start coordination,
controller/UI, live recognition and streaming-load acceptance remain open.
Installed OBS is
32.2.2; its development headers/import libraries are not prepared. An existing
LLVM-MinGW compiler provides a proposed original C-only plugin build route, with
compile/load proof still required in the [build plan](plans/active/obs-plugin-build.md). The
[control dependency record](desktop-obs-control-resource.md) records the pinned
library, reviewed full license and development-wheel provenance.

Current integrated desktop regression: **1,432 passed, 13 skipped in 39.47 seconds**,
including the reviewed OBS control, native identity, pipe and audio handshake.
The combined focused OBS/pipe/privacy/configuration/boundary/packaging bundle
passed 385 tests in 6.29 seconds. The preceding continuous
transcription integration passed 1,068 tests with 13 skips.
Storage failures show Recording interrupted and preserve their actual cause and
recovery message. The shared batcher now prefers quiet pauses near the 30-second
limit, retaining every audio sample exactly once. Both normalized comparisons
of an 88-second public-speech fixture had 176 candidate and 176 reference words,
with zero alignment insertions or deletions; a two-word duplication measured
with fixed boundaries was absent. Substitutions
varied between runs, so this is a narrow boundary check, not a general accuracy
claim. Independent review cleared the integration and cancellation at batch handoff.
A separate one-hour synthetic capture stored 691.2 MB temporarily, retained all
samples through resampling/batching, stayed below the 8 MiB write-queue bound and
removed its temporary file on close. This measures the storage path, not total
process memory, model load or an hour of real-time microphone use.

### Active: dictation boundaries and explicit Markdown

The [dictation completion plan](plans/active/desktop-dictation-completion.md)
addresses reported fused sentences, list continuation and caret-adjacent spacing,
plus a local optional Markdown output mode. Preserve raw/literal input and use
only supported verified editor context. Source changes, installed-build behavior
and browser/macOS/Linux limits must be recorded separately.

**Implemented in unreleased source:** explicit list boundaries, native Windows
Edit insertion-neighbor spacing, and **Vocabulary → Output style → Markdown**.
The preference persists locally, participates in selective backup, resets to Prose
and leaves raw/code input unchanged. Explicit headings and lists have structural
separators. Full desktop pytest reports 763 passed and 18 skipped locally (11
explicit-codec-fixture requirements, 6 file-review Tk setup failures, 1 unavailable
symlink privilege); current Settings captures were
rendered without a microphone and inspected. Browser caret awareness, installed
live-dictation behavior and a new packaged release are not established by this pass.

**Implemented and independently reviewed in unreleased source:** optional local
speech-end stopping with a 0.5–3 second pause, separate default review versus
automatic insertion, and explicit manual start for each take. Hold/toggle,
cancellation remain; the newer continuous-recording work supersedes the duration
cutoff. A visible two-minute review offers
Copy/Insert/Discard; insertion requires the original supported native field/text/
caret. Other editors use Copy. The [speech-endpoint plan](plans/active/desktop-speech-endpoint.md)
records tests, resolved review findings and remaining verification. The final
integrated suite passed 827 tests with 12 skips (11 explicit FFmpeg-fixture
requirements and one unavailable symlink privilege); all Tk/UI tests ran and
passed. Earlier intermittent Tk setup skips were not reproduced in the final
run, but their cause remains undiagnosed. No physical-mic,
packaged-release or installed-app claim follows from these source checks.

The [VAD resource review](desktop-vad-resource.md) records exact local model,
wrapper/runtime identity and full Silero/ONNX Runtime notices. Unknown detector
resources leave manual stopping available; no automatic detector acquisition.

Wispr Flow's [documented features](https://wisprflow.ai/features) and
[formatting behavior](https://docs.wisprflow.ai/articles/5373093536-how-do-i-use-smart-formatting-and-backtrack)
provide workflow references: punctuation, lists, spoken corrections, dictionary
and snippets. Their existence is not evidence of Utterleaf parity. Prioritize
reliable local dictation and repair; explicit recap/rewrite remains a separate
future action with preview, not an automatic interpretation of dictated questions.

### Planned: reviewed resources and optional providers

Follow the [model/component policy](model-resource-policy.md) for reviewed local
models, explicit user acquisition and separately enabled speech/text endpoints.
Local processing stays the default. No unchecked repository code, hidden remote
fallback or assumption that a download button resolves license compatibility.
Existing model download controls remain; arbitrary providers and a complete
component compliance audit are not claimed as implemented.

### Later: optional on-screen keyboard

User-requested exploration, lower priority than current dictation reliability and
Android usability. Provide a comfortable touch keyboard with local dictation,
editing/navigation utilities, optional terminal modifiers and accessible controls.
Keep advanced controls out of everyday typing and preserve native OS keyboards.
Evaluate Windows, macOS and Linux separately for secure-field behavior, input
delivery, focus, screen readers, switch access and touch sizing. Reuse product
principles and assets; do not assume Android input code is portable or request
broad permissions merely for convenience. No desktop on-screen keyboard is
implemented or promised as part of the current Android release.

### Responsiveness audit follow-up — September 10–12

A scoped Aden/source review on September 10 confirmed that settings work and IPC
dispatch run outside the UI event loop. It identified unbounded macOS/Linux paste
subprocesses and cancellation that did not reach final delivery.

**Implemented and independently reviewed in unreleased source on September 12:**
per-job Esc/quit cancellation now reaches final delivery without waiting for the
capture lock. Owned macOS/Linux paste helpers have bounded waits and cleanup, and
a launched helper is never retried after failure, timeout or cancellation. A
partial Windows `SendInput` result is uncertain rather than failed and releases
possibly held modifier keys without sending a second paste. Final target and
clipboard-ownership checks remain in place. The app reports uncertain delivery
visibly and asks the user to check the original field before using recovery,
because insertion may already have occurred. The independent focused suite passed
167 tests; the final desktop suite passed 860 tests with 12 expected/environmental
skips (11 explicit FFmpeg-fixture checks and one Windows symlink-privilege check),
and all Tk/UI tests ran. See the
[delivery cancellation plan](plans/active/desktop-delivery-cancellation.md) for
the remaining synchronous-call limits. Native platform/editor acceptance and a
packaged release remain open.

**Windows clipboard follow-up implemented and independently reviewed in source:**
reads and writes
run in a private one-shot child. Restoration uses a sequence check and replacement
while the clipboard is exclusively open; a normal delivery reads previous text
at most once. Copy/recovery uses the same bounded write path. Windows job ownership
must succeed before the child receives a request. The full suite passed 936 tests
with the same 12 environment skips; the final focused suite passed 231 tests,
including harmless native checks for job close and abrupt parent exit. See the
[clipboard plan](plans/active/desktop-clipboard-bounds.md) for native metadata,
hostile-owner and frozen-startup acceptance gaps.

The [names-only isolation probe](plans/active/windows-isolated-clipboard-acceptance.md)
passed source review and mocked checks. This Windows session denies permission to
create the required private station (error 5); the parent station/desktop remained
unchanged and no clipboard operation ran. Isolated ordinary/stalled-owner tests
remain open for an environment that permits the reviewed boundary.

## Foundation implemented

- Local recognition and cleanup, with an option to preserve model output.
- One-key toggle recording; microphone released between takes.
- Bounded recording and queued takes, with explicit cancellation.
- Two-minute in-memory recovery, explicit forgetting, and recovery CLI commands.
- Conservative native-field editing and manual fallback when edits cannot be verified.
- Clearer settings, shortcut validation, and partial-save error reporting.
- Dark Settings, optional overlay with countdown, tray-only defaults, and all seven Utterlings in normal UI use (v0.3.3).
- Multiword list fixes and local timing diagnostics (v0.3.3).

## Current delivery status

**Version 0.4.1:** model installation status and explicit download/repair, grouped
speech/privacy controls, common audio/video decoding through a selected FFmpeg,
existing-window activation, separators between completed dictation takes, and
paused “scratch that” with verified replacement. Windows GPU setup gives
platform-specific runtime instructions. Automatic correction still requires a
supported native Windows Edit field; browsers and other unsupported fields use
manual recovery. See the [user guide](user-guide.md) for the exact behavior.

**September 12, 2026 bounded Settings pass:** source-level Tk checks reproduce
the compact 770 × 655 layout and verify that the first shortcut-combobox click
does not scroll the canvas or detach its popup. Focus reveal now ignores Tk
`FocusIn` propagation through container frames while retaining off-screen
control reveal. Focused settings tests and the no-microphone screenshot capture
pass; the current source screenshot shows the vocabulary explanatory labels
fully rendered at the compact size. This is source evidence, not a packaged
release claim.

Installed downloaded CPU-build observations are recorded separately: all five
main pages opened; microphone checking produced both low-audio and
audio-detected feedback; staging the floating indicator enabled Save; Close
opened the discard dialog; choosing No retained edits; returning to Tray icon
cleared the dirty state; and the CPU device report completed with GPU-runtime
unavailable guidance. No personal preference was saved. Windows UI Automation
exposed nearly all settings controls as unnamed panes, so control naming and
screen-reader acceptance remain open. Live dictation, paste delivery,
persistence across relaunch, reset, and screen-reader behavior were not
verified in that build. Microphone feedback is not transcription proof.


**Version 0.3.7 usability audit:** direct task headings, compact decorative art,
visible selection/focus marks, responsive footer messages, readable hardware
choices, and validation that returns to the invalid field. The
[quality audit](product-quality.md) records evidence and outstanding platform,
accessibility, and display-scaling checks.
The same release authenticates local control commands and preserves offline and
clipboard preferences during defaults recovery. Security first, privacy second, and convenience third guide
remaining work; all three matter. These priorities take precedence over speed of delivery for remaining roadmap decisions.

**Version 0.3.6 interface and documentation refresh:** grouped Settings controls,
charcoal surfaces, the approved sidebar wordmark, recovery-first Help, and updated
screenshots. A [documentation index](README.md) separates current guides from
historical investigations. [Interface guidelines](interface.md) keep future work consistent.

**Version 0.3.5 changes:** one Settings window per configuration, staged defaults
recovery under Help, and a current Help screenshot. Wayland fixes exclude misleading X11 paste
fallbacks, avoid stale XWayland focus queries, and explain missing desktop setup
in diagnostics. [Wayland setup](wayland.md) documents current limitations.
Native GNOME/KDE/wlroots delivery validation and portal integration remain needed.

**Microphone recovery release:** [v0.3.4](https://github.com/RioPlay/utterleaf/releases/tag/v0.3.4).
Included: Windows shared microphone selection, a bounded retry for
temporary device-unavailable errors, and resetting toggle state after a failed
microphone start. These are included in v0.3.4, not v0.3.3.

**Version 0.4.0:** timestamped file transcription
with a review/export window and explicit TXT/SRT/VTT output, selective preference
and vocabulary backup, clipboard change-identity checks, and microphone interruption
recovery. These changes are not included in older v0.3.8 downloads.
See [file transcription](desktop-file-transcription.md) and
[backup and import](desktop-backup.md) for supported scope and remaining gates.

**Planned, not implemented:** system-audio captions, meetings, speaker
labels, and translation. See the [feature plan](feature-plan.md) for dependencies
and acceptance criteria, and [microphone troubleshooting](microphone-troubleshooting.md)
for current behavior and limits. Continuous dictation without the fixed cutoff
is implemented in unreleased source as recorded above; installed releases retain
their separately documented behavior.

These are implemented capabilities, not proof of end-to-end quality on every platform.

## Privacy-first convenience milestones

**Next planned desktop milestone:** [GitHub update checks and safe staged updates](desktop-updates.md).
Start with manual checks and opt-in daily/weekly checks; authenticated downloads
and explicit Windows replacement follow separate trust and recovery gates, then
macOS/Linux validation. This updater is not implemented or included in v0.4.1.

Mobile keyboard development has its own [roadmap](mobile-roadmap.md),
build system, dependencies, acceptance gates, and release versions.

Each milestone must preserve explicit capture, bounded retention, offline use,
and actionable recovery. No accounts, passive listening, automatic transcript
archives, or background reading of other apps are required.

| Order | Deliverable | Acceptance gate |
| --- | --- | --- |
| 1 — active | Microphone recovery, safe delivery, clear readiness | Missing named inputs never open a substitute; reconnect/permission errors offer recovery. Test native device loss and editor delivery before broader reliability claims. Show loading/download/ready states and require explicit download approval. |
| 2 | Comfortable long dictation | Bounded RAM and queued processing, ordered text across chunk boundaries, cancel/discard and elapsed time. Authorized temporary audio supports long takes; no automatic permanent recording archive. |
| 3 | Understandable speed choices | Local, user-requested measurements inform Faster/Balanced/More accurate choices; show actual engine/device and explain fallback. Never upload benchmark speech. |
| 4 | Vocabulary helper and selective backup | Explicit local vocabulary additions; preview exported preferences/vocabulary. Exclude recordings, transcripts, device-specific control tokens, and secrets. No contacts or clipboard-history scanning. |
| 5 | Local file transcription | Explicit file selection, text/SRT/VTT export and discard; handle missing models and media support without unexpected downloads. |
| Later | Captions, meetings, speaker labels, translation | Follow the [feature plan](feature-plan.md), with explicit session start, source selection, retention and export controls. |

Wayland desktop-managed shortcuts and safe insertion belong to milestone 1;
shortcut registration does not establish successful or correctly targeted paste.
Keep frequent actions in the tray, preferences in Settings, and repair tools in
Help. Use Utterlings for helpful status and recovery guidance without new popups.

First implementation in v0.3.8: exact saved microphone selection,
failure before capture when it is missing, and refresh guidance that preserves
the selection. Native hotplug recovery and device identity remain open work.

## 1. Reliable delivery — active

Implemented in unreleased source: check focus after the shortcut-settling delay;
verify clipboard ownership before sending paste. If focus moved, leave dictation
on the clipboard. If final clipboard ownership cannot be verified, cancel
delivery and retain the existing recovery path. Windows data operations now use
bounded children, with conditional writes guarding a user's intervening copy.
Esc and quit signal each delivery job independently of the capture lock. Owned
macOS/Linux helper processes have bounded waits and cleanup; after any possible
dispatch, timeout, cancellation or failure is reported as uncertain without a
fallback retry. Windows partial native dispatch receives the same treatment and
releases possibly held paste keys. Uncertain delivery remains recoverable and
tells the user to check the original field before copying the result again. See
the [delivery cancellation plan](plans/active/desktop-delivery-cancellation.md).

Remaining work:

- Preserve rich clipboard formats, not only plain text.
- Investigate restoration timing in slow applications.
- Complete Windows clipboard native/packaged acceptance;
  address synchronous macOS/Linux clipboard backends separately without a
  detached worker that could mutate the clipboard after cancellation.
- Assess synchronous native `edit_target.replace` calls; cancellation cannot
  interrupt or retract an edit after the native operation is dispatched.
- Distinguish sending a paste shortcut from observing successful insertion.
- Test browser fields, native and rich-text editors, terminals, and elevated apps.
- Test window and field changes, held modifiers, busy clipboards, and fast repeated takes.

Completion evidence: a documented OS/editor matrix with observed delivery and
recovery results, including Unicode and selected-text replacement. No unexpected
typing or loss of a newer clipboard copy in the tested scenarios. The final
focus check reduces a race; it cannot make desktop input atomic or detect every
field change inside the same window.

## 2. Effortless first run — next

- Make model availability and download requirements clear before recording.
- Verify interrupted-download retry and model changes after offline initialization.
- Exercise missing microphone permission, unplugged devices, and default-device changes.
- Verify useful CPU fallback when an accelerator cannot initialize.
- Check packaged first launch on a clean user profile without developer tools.

Completion evidence: a new user can reach a successful first dictation using the
visible UI; each failure above offers an actionable recovery without editing config
files. Test denied network access and offline relaunch with installed weights.

## 3. Measured speech quality and speed

- Measure cold start, time until listening, and end-of-speech-to-delivery p50/p95.
- Record CPU, RAM, model, engine, language, and audio conditions for each result.
- Include names, numbers, negation, accents, multilingual text, quiet speech,
  background noise, and silence in a consented or public evaluation set.
- Choose defaults from measured accuracy, responsiveness, and resource use.

Completion evidence: reproducible results on named ordinary CPU hardware, with
explicit accuracy/latency tradeoffs. Set performance budgets from that baseline.

## 4. Accessibility and desktop polish

- Test keyboard-only setup and recovery, screen readers, and high display scaling.
- Verify recording status and errors without relying on sound or color alone.
- Keep real Tk checks running in CI; investigate any unexpected display-related skips.
- Evaluate a different desktop shell only if measured usability, accessibility,
  startup, or packaging limits justify it. Keep the Python speech pipeline unless
  evidence identifies it as the constraint.

Completion evidence: documented accessibility results and release checks that run
reliably in the supported environments.

## Scope discipline

The new user-requested expansion is optional **Transcribe**, **Captions**, and
**Meeting** modes. These share the local speech engine while keeping ordinary
dictation quiet and lightweight. Meeting capture requires a deliberate session
start, clear capture state, and explicit save/discard behavior.

Cloud accounts, bundled chat, team workspaces, engagement statistics, and
automatic permanent recording history remain outside the plan. Optional models
should be installed only for features the user enables.

Live microphones, external editor delivery, clean-install packaging, and speech
benchmarks still require direct validation. Automated unit tests do not substitute
for those checks.
