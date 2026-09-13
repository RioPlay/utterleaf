# Desktop roadmap

[Roadmap hub](roadmap.md) · [Mobile roadmap](mobile-roadmap.md)

Scope: Windows, macOS, and Linux desktop application only.

Updated September 13, 2026. Priorities follow the
[offline STT user research](offline-stt-user-research-2026-09-08.md).
This is an ordered development plan, not a promise of release dates.

See [platform testing](platform-testing.md) for current Windows/WSL results and
the real-device checklist, including macOS testing.

The product goal is simple: press a key, speak, and get dependable text in the
intended field, with understandable local processing and minimal interruption.

## Planned follow-up

### Published preview: Windows 0.4.6 RC2

The [Windows prerelease plan](plans/active/desktop-prerelease.md) records the
completed dictation, long-file, speech-end, Markdown and delivery improvements
in the [published unsigned Windows x64 CPU preview](https://github.com/RioPlay/utterleaf/releases/tag/desktop-v0.4.6-rc.2).
Version `0.4.6rc2` was published on September 13 from immutable tag revision
`90d2e147c6c84af2639317b427a2f5135b3ff997`. Stable v0.4.5 remains
the default download. Android and live OBS work continue after this bounded release.

RC2 runtime notice enforcement passes 23 focused tests and a fresh local CPU
build. Following test-only Tk lifetime cleanup, the final local desktop suite
passes 1,445 tests with 14 explicit skips; frozen diagnostics and an offline
88-second file transcription also pass. [Exact-tag CI](https://github.com/RioPlay/utterleaf/actions/runs/34740809768)
passed **1,446 tests with 13 skips**. Independent verification of the downloaded
artifact passed archive, executable, dependency and retained-notice checks,
frozen diagnostics and offline 88-second transcription. See the
[runtime notice record](plans/active/desktop-runtime-notices.md), the
[completed CI integration plan](plans/completed/desktop-ci-platform-integration.md),
and the [completed backup compact-layout plan](plans/completed/desktop-backup-compact.md).

Historical source receipts below describe their original verification stage;
references to unreleased source or pending packaging describe those earlier
checks. The preview plan records final artifact and publication evidence.
Live-microphone endurance, broad editor and accessibility acceptance, other
desktop binaries and live OBS remain unverified or unavailable as documented.

Final RC2 integration evidence is recorded in receipt
`.grok/release/ci-rc2/release-review-34746938663.json`: exact-head CI run
[34746938663](https://github.com/RioPlay/utterleaf/actions/runs/34746938663)
from `3f1bd6c5c3200d01ee0d4121ffb34d636b6530d8` passed Windows **1,459 passed,
13 skipped**, macOS **1,440 passed, 32 skipped**, and both Linux X11 and forced
Wayland suites at **1,440 passed, 32 skipped**. All three platform builds,
notice collection, frozen smoke checks and independent native-payload inventory
verification passed. RC2 remains the published immutable tag; this evidence
does not extend to stable desktop release status or unverified physical/editor
acceptance. PR #26 merged into main at `bf4dfda`.

### Integrated source: compact Dictation settings

The [compact Dictation plan](plans/active/desktop-dictation-layout.md) groups
shortcut, activation and microphone controls near the top, moves Output style
to Dictation, and places speech-end stopping before secondary recording options.
The two input groups stack when text needs more width. This is a source follow-up
to RC2; the published preview keeps Output style under Vocabulary. All **50**
focused settings/configuration tests pass with no skips, including resize, focus,
validation, microphone Test/Stop/retry, and save/discard/reset checks. Default and
compact captures and controlled larger-font checks pass. Independent review is clear.
[Exact-source CI](https://github.com/RioPlay/utterleaf/actions/runs/34750749369)
passed all five desktop jobs at `76f448c`; PR #31 merged at `03a1c9b`. The macOS
layout loop and a native-foreground dependency in a simulated clipboard test
were corrected before integration. Physical display-scaling and assistive-technology
behavior remain separate.

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

There is no live-capture app entry point. The component checkpoints below record
enrollment, native client authentication, atomic arming and PCM work. The current
session-controller increment connects those components to local recognition and
an isolated view; actual OBS enrollment, frontend/audio and streaming-load
acceptance remain open.
The original C-only [development module](../native/obs-plugin/README.md) first
established the inert build/load prerequisite through PR #32 at `e61c7dd`.
The current linked module builds against 42 pinned OBS/frontend/vendor public
resources and deliberately refuses headless initialization before opening its
pairing store. The isolated fixture starts no OBS application or audio sources.
The separate [native session components](plans/active/obs-native-session.md) now
pass fixed Hello/ACK and CNG-failure checks, 11 actual child-process transport
tests, current-logon DACL/noninheritance checks and 64 create/destroy handle
balance cycles. A focused desktop boundary/pipe regression passes 54 tests.
Independent admission source/test/evidence review is clear; PR #33 merged at
`006d482` after all five exact-source desktop CI jobs passed. The next
[enrollment step](plans/active/obs-native-enrollment.md) accounts for the public
vendor API's lack of caller authentication context. That earlier increment kept
the session components separate; the current linked increment is described below.
The enrollment branch implements independent capability
proof and native admission ownership: 30 client tests, 10 native child-process
cases and six state/fault groups pass, including expiry, replay, revocation and
concurrent preparation. The focused desktop regression passes 177 tests; final
independent source/evidence review is clear. These historical component checks
precede the native pairing/vendor integration described below.
PR #34 merged at `9260e6b` after all five
[exact-source desktop CI jobs](https://github.com/RioPlay/utterleaf/actions/runs/34754090586)
passed at `d44126a`. The `feat/obs-pairing-store` increment, merged through
PR #35 at `3bd072d` from exact source head `c7f86f6`, now implements the
selected CurrentUser DPAPI package, separate native/desktop stores, native export,
explicit desktop import/replacement and separate forget behavior. The first
local regression passes 292 tests, including 48 pairing cases, plus 22 native
verification commands, 57 source/artifact hashes, five interop cases and five
store state/fault groups, including an actual junction. Exact-head CI
[34755748029](https://github.com/RioPlay/utterleaf/actions/runs/34755748029)
passes all five desktop jobs; release publication was skipped. Independent
source/test and final receipt review is clear. Three known warnings remain
isolated to the test heap shim.
The enrollment plan distinguishes these
storage results from pending UI, live revocation, vendor and audio integration.
Cross-user/logon, remote clients, forced PID reuse and kernel
completion failure are not established by these fixtures. The installed toolchain
is not fully pinned and native redistribution review remains open; no plugin
binary is included in desktop or Android releases. The
[build plan](plans/active/obs-plugin-build.md) retains the complete native gates. The
[control dependency record](desktop-obs-control-resource.md) records the pinned
library, reviewed full license and development-wheel provenance.

Pairing setup remains in draft PR #36 on `feat/obs-enrollment-flow`; the separate
Arm increment continues on `feat/obs-session-arm`. The desktop controller, PCM and
live recognition remain later gates. No live-capture app entry point, audio endpoint, plugin binary
publication or OBS capture integration exists yet.

The linked native pairing Tools flow, exclusive per-user owner and strict
vendor Issue/Prepare dispatch are now present in the development module.
All 28 native driver commands pass, including lifecycle/dispatch races, actual
owner competition, shimmed bridge lifecycle and six real-libobs parser cases.
The linked DLL builds and headless refusal passes with unchanged fixed-store
metadata. Frontend UI interaction and real OBS acceptance remain unverified.
The typed desktop adapter sends only the defined Utterleaf Issue/Prepare
requests after explicit invocation, verifies challenge binding and the OBS peer
before proof, and rejects concurrent operations. The focused bundle passes
**341 tests with no skips**, including **66** enrollment tests and an ephemeral
loopback exchange. Independent source review is clear; native identity is stubbed
in that new exchange fixture. This prepares a session ID and does not connect
the audio pipe or arm capture. Native owner/UI/vendor integration remains
unverified for real OBS/device acceptance.

The [desktop pairing dialog](plans/active/obs-desktop-pairing-ui.md) now opens from
Speech & privacy on Windows, with explicit import/replace/forget, a separate
per-user store owner and asynchronous cancellation/teardown. Saved status never
claims an OBS connection. The related bundle passes 204 tests; all 23 UI cases
pass after the final status-card adjustment. Native TaskDialog activation,
Escape, modal cleanup and zero-mutation checks also pass in an isolated fixture;
all 29 native driver commands pass with `--ui`. Normal/compact/enlarged desktop
renders were inspected. Independent final desktop setup review is clear, with
29 focused and 187 related tests rerun on the final source. All five exact-source
CI jobs pass at `e71b627` in [34760760046](https://github.com/RioPlay/utterleaf/actions/runs/34760760046).
No existing release changes. Earlier linked checkpoint `15e1c77` passed
all five desktop CI jobs in [34758907354](https://github.com/RioPlay/utterleaf/actions/runs/34758907354).

The separate [Arm integration](plans/active/obs-session-arm.md) is active on
`feat/obs-session-arm`. It adds a fixed authenticated-pipe command, guarded
frontend consent, bounded native I/O and an explicit desktop Arm operation.
The 199-test affected desktop bundle and all 34 native build/test commands pass,
along with the linked build and headless refusal smoke. Independent source review
is clear. Startup/started/stopping states remain busy even when public activity
flags are false; a failed start without STOPPED requires a later actual STOPPED
or OBS restart before fresh Arm. Visible failure/recovery controls and real OBS
acceptance remain pending with the controller/PCM work. This is source work,
not live OBS support or a new release. All five desktop jobs for Arm source
`073bb99` passed in [CI 34763204298](https://github.com/RioPlay/utterleaf/actions/runs/34763204298).

The active [native PCM plan](plans/active/obs-pcm-stream.md) now has an original
wire encoder, bounded planar copy queue and worker-only libobs stereo conversion
in the development DLL. All 42 canonical native commands and headless smoke pass;
synthetic conversion covers all six supported rates and seven OBS speaker layouts.
The thread fixture forces queue loss and slot reuse. Current source
integration connects the armed session to frontend capture and worker transport,
with aligned bus starts, explicit loss, bounded normal-stop draining and an End
receipt before disconnect. All 24 linked-build commands, 51 native verification
commands (including 84 Python pipe tests) and headless smoke pass. Independent
final review is clear. Visible control, local
recognition and real OBS frontend/audio acceptance remain open. The 42-command
receipt above belongs to the preceding component checkpoint, not this integration.
The integrated PCM source is preserved in draft PR #38 at `c3c4fe5`; all five
desktop jobs passed in [CI 34768051105](https://github.com/RioPlay/utterleaf/actions/runs/34768051105).

The separate [manual Disarm increment](plans/active/obs-session-disarm.md) on
`feat/obs-session-disarm` adds an explicit pipe stop without changing the OBS
stream. Armed waiting has no duration cutoff; active/partial-message stalls and
stop completion remain bounded. A stop before accepted PCM produces no audio
stores. If attachment wins the stop race, aligned queued audio is preserved;
partial first-bus data remains incomplete. The native worker waits for frontend
detach before a clean Disarmed End. All 249 focused desktop tests, 51 native
verification commands, the 24-command linked build and headless refusal pass.
Independent final review is clear, and 383 recorded hash comparisons match the
final inputs and outputs. This remains development source, with no live-capture
app entry point or new release; visible control, local recognition and real OBS
acceptance remain open.

The [session-controller increment](plans/active/obs-session-controller.md) now
implements one explicit connect/Arm session, manual Stop, cancellation and
committed-window local recognition before capture ends. A narrow `GetStatus`
request checks compatibility without consuming authorization. The authenticated
native session identifier binds Start and End to the current Arm; late untagged
WebSocket events cannot start or stop another session. Ordinary control loss
after accepted PCM leaves healthy audio capture running, with visible degraded
status. Identity/protocol failures remain terminal.

Recognition honors the saved accelerator with networking disabled, preserves
per-bus timing, bounds model segments/text while consuming them and retains a
4,000-character preview over a private temporary journal. Cancel is nonblocking;
completion waits for audio, recognition and requested journal cleanup. The
compact Tk view receives snapshots and forwards explicit actions. It has no
application entry point, pairing-key ownership, export implementation or live
OBS acceptance yet. Accurate mix/routing metadata, recorded-file timelines and
separate native distribution review remain product gates. All 647 focused backend
tests, 37 Tk tests, 51 native verification commands, the 24-command linked build
and headless smoke pass. Eight synthetic UI renders were inspected; independent
source review is clear. Its active plan records exact commands and remaining
acceptance limits.

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
caret. Other editors use Copy. The [speech-endpoint plan](plans/completed/desktop-speech-endpoint.md)
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
