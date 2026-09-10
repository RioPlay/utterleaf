# Roadmap execution plan

Planning baseline: September 9, 2026, desktop 0.3.8 source and Android keyboard
foundation branch. This document assigns work; it does not change feature or release
status. The [desktop](desktop-roadmap.md), [mobile](mobile-roadmap.md), and
[feature](feature-plan.md) roadmaps remain the status authorities.

## Astra objectives and coordination

1. Close unsafe capture, insertion, import, and retention paths before enabling new modes.
2. Deliver bounded local speech and explicit recovery, with measurable cancellation,
   memory, ordering, and privacy behavior.
3. Expand desktop modes and everyday Android typing through independently reviewable
   packages; verify accessibility alongside each visible change.
4. Establish iOS feasibility and native evidence before promising equivalent integration.

The coordinator assigns one writer per owned file group. Independent packages may
run in parallel; overlapping integration happens serially after contract review.
Reserve `utterleaf/app.py`, `config.py`, `settings.py`, `settings_ui.py`, and
`__main__.py` for the desktop integrator unless explicitly reassigned. Reserve
roadmap status edits and shared CI changes for the coordinator. Package owners may
write isolated tests and evidence notes. Do not revert another agent's work.

Android PR #2 is already in CI: preserve its source and acceptance work until its
result is reviewed. Mobile release, signing, Obtainium, versioning, and publishing
remain exclusively with the coordinator. Do not combine desktop changes into that PR.

## Gates for every package

- **Security:** document new trust boundaries; reject malformed/unbounded input;
  fail closed on stale delivery; review dependency provenance, licenses, and network
  behavior before adoption. Never request extra privileges to bypass platform limits.
- **Privacy:** explicit start/import/export; no transcript or audio logging, automatic
  archives, passive capture, hidden uploads, or disk spooling. Preserve offline and
  clipboard preferences through reset/import. Use synthetic or consented test content.
- **Validation:** run focused behavioral tests, affected platform checks, and the
  integration suite once assembled. Record revision, command, actual result, and
  remaining native checks. A test double validates a contract, not OS behavior.
- **Product:** keyboard and screen-reader access, meaningful visible status,
  cancel/discard, understandable errors, updated guide and actual-app screenshots.
  Apply these to each feature rather than claiming a later accessibility pass suffices.
- **Release:** implemented, verified, merged, and released remain distinct. A release
  needs its immutable artifact, source/version identity, notes, and relevant platform
  evidence. Carry forward unmet acceptance gates explicitly.

## Ordered desktop packages

Numbering gives product priority; dependency-free foundations can proceed alongside
earlier work. Paths not currently present below are proposed new files.

| ID / dependency | Objective and exclusive ownership | Measurable acceptance and security gate |
| --- | --- | --- |
| D1 / now | Safe clipboard transaction: `utterleaf/inject.py`, new `clipboard.py`, `tests/test_inject.py`, new `test_clipboard.py` | Preserve supported rich formats; refuse unsafe restoration when snapshot is incomplete. A newer clipboard owner/version, including a copy of identical text, is never overwritten. Test focus changes, unreadable/busy clipboard, failed sends, unsupported formats, and delayed consumers. Keep content in memory only. Report shortcut sent separately from observed insertion. Native clipboard/editor matrix remains required. |
| D2 / now; integrate serially | Detect capture interruption: `utterleaf/audio.py`, `tests/test_audio.py`; integrator owns app/status wiring | Stopped stream and absent callbacks terminate capture with recoverable buffered speech; callbacks containing silence do not trigger failure. Test device disappearance, callback cessation, retry bounds, cancellation, and reconnect with exact selected input. No automatic substitute microphone. Record chosen watchdog threshold and native hotplug/permission evidence. |
| D3 / D1 integration | Readiness and safe first run: `models.py`, `hardware.py`, relevant focused tests; integrator owns settings/app | Missing weights cannot start a hidden download; approval is explicit and scoped to the requested download. Interrupted download remains non-ready and retries safely. Offline relaunch and model switching use installed weights; accelerator failure reports actual CPU fallback. Validate a clean packaged profile with denied network and microphone access. Review model identity/integrity and partial-download boundaries. |
| D4 / now | Structured recognition: `utterleaf/transcribe.py`, new `segments.py`, `tests/test_transcribe.py`, new `test_segments.py` | Add typed timestamped segments plus existing string compatibility. Test lazy engine output, Unicode, empty/silent output, non-finite/reversed timestamps, GPU fallback, and cancellation between segments. Engines lacking timestamps report that capability explicitly; never invent subtitle timing. Existing dictation output and inference serialization remain compatible. |
| D5 / D2 + D4 | Bounded long sessions: new `streaming.py`, `tests/test_streaming.py`; audio owner and integrator merge dependent wiring | Specify chunk duration/overlap and a hard sample/queue byte cap before coding. Simulate one hour including decoder slower than capture; retained audio stays within the declared cap and output is ordered. Test repeated words and punctuation across overlap, cancel at every boundary, queue saturation, and final tail. Backpressure stops safely with explanation rather than dropping speech or spilling audio to disk. Remove hold cutoff only after integration proves these invariants. Toggle limits remain optional and visible. |
| D6 / now, integrate after D3 | Selective backup/vocabulary helper: new `backup.py`, `tests/test_backup.py`; read-only use of `Config` and vocabulary format | Versioned allowlist export with preview; exclude audio, transcripts, logs, credentials/control tokens and device paths/identity. Reject oversized, unknown-version, malformed and invalid-value imports before mutation. Import cannot enable network or weaken clipboard protection implicitly. Test Unicode vocabulary, explicit replace/merge decisions, cancellation, and atomic rollback of affected files. UI/CLI wiring belongs to integrator. No surrounding-text or clipboard scanning. |
| D7 / D3 + D4 | Explain speed choices: `scripts/benchmark_dictation.py`, new benchmark tests/evidence; integrator owns UI choices | User-requested local measurements report named model, engine, actual device, language, CPU/RAM, cold start, time to listening, and end-to-delivery p50/p95. Public/consented corpus covers names, numbers, negation, accents, multilingual speech, noise and silence. Record sample count and failures; derive Faster/Balanced/More accurate defaults from real measurements, not synthetic timing. No speech upload. |
| D8 / D4 + D5 | Local file transcription and export: new `file_transcription.py`, `subtitles.py`, respective tests; integrator owns entry points | First ship a declared supported decoder/format set; review decoder licenses, size, hostile-media handling and packaged availability before widening it. Explicit file selection, progress, cancel/discard and TXT/SRT/VTT export. Test malformed/truncated input, long-file bounded memory, Unicode, timestamp ordering/rounding, and output overwrite failure. Captured words such as “scratch that” remain transcript text. No automatic model/media downloads. |
| D9 / D5 + D8 | Windows live captions then platform adapters: new `system_audio.py`, `captions.py`, respective tests | Explicit audio-source selection and start/stop; overlay never starts at launch. Distinguish provisional/final text; test revisions, clock continuity, cancellation and bounded memory. Native tests measure caption latency and prove source routing. macOS/Linux adapters require separate permission/native evidence; desktop shortcut registration alone proves neither capture nor delivery. |
| D10 / D9 | Meeting sessions: new `meeting.py`, `tests/test_meeting.py` | Explicit microphone/system-audio selection, pause, bookmarks, export/discard. One-hour capture keeps declared memory bounds and source-clock drift/echo/duplicate speech within recorded acceptance budgets. No calendar/bot access or automatic saving. Validate native audio routing and interruptions. |
| D11 / D10 | Speaker labels: new `speakers.py`, tests, dependency decision note | Evaluate licensing, access requirements, offline behavior and resource use before selecting a model. Speaker 1/2 plus manual naming; keep available source tracks separate. Measure overlap, short turns and label instability on consented audio; support correction/refinement. No persistent voice identity. |
| D12 / D9 + model review | Translation: new `translation.py`, tests; integrator owns explicit language/model selection | Show original and translated text together; verify supported languages/tasks and explicit model download requirements. Measure latency, names, negation and switching. Unsupported target fails clearly; no network translation fallback. |
| D13 / D10; evaluation only | Optional local summaries: isolated experiment and decision note before runtime integration | User starts generation with a separately approved local model. Every proposed action/claim links to source timestamps and remains editable; evaluate unsupported claims and omission. No silently bundled language model. A go/no-go decision satisfies the evaluation milestone; it does not establish a shipped summary feature. |
| D14 / continuous | Accessibility, Wayland and native delivery evidence: `docs/platform-testing.md`, `docs/product-quality.md`; coordinator assigns `host.py`, `hotkey.py`, `edit_target.py` only when needed | Real Tk checks run in CI without unexplained display skips. Keyboard-only setup/recovery, screen readers, high scaling, and status without sound/color. Native Windows/macOS/X11/GNOME/KDE/wlroots matrix covers browser, native/rich editor, terminal, elevated apps, Unicode, selection, held modifiers and repeated takes. Portal integration must prove correctly targeted insertion, or retain an actionable manual fallback. Shell replacement requires measured evidence. |

D4 may add pure export formatting tests while D8 decoder selection is pending, but
that must not be described as a usable file-transcription feature. D6 can land its
pure validation/preview API independently; the milestone requires its visible flow.

## Ordered Android packages

All runtime paths below are under `mobile/android/app/src/main/java/org/utterleaf/voice/`.
Reserve existing shared `DeviceTest.kt` and `PrivacyCoreTest.kt` for one integrator;
new focused test classes avoid parallel edit conflicts.

| ID / dependency | Objective and ownership | Measurable acceptance and security gate |
| --- | --- | --- |
| A1 / PR #2 CI review | Close M1 foundation record and review M2 lifecycle: `docs/mobile-security.md`; assigned Android integrator owns `KeyboardIme.kt`, `VoiceIme.kt`, `TakeGate.kt`, `VoicePanel.kt` | Record origin/license/notices for every imported asset/dependency. Test late speech callbacks after field replacement, same-field restart, hide, lock and destruction: zero unintended commits. Password/numeric-password/visible-password typing remains available while speech and future learning/read-back stay disabled. Verify no surrounding-text collection or input in logs/preferences. |
| A2 / A1 | Complete everyday M2 typing: `TypingPanel.kt` plus isolated typing tests; integrator owns IME editor wiring | Exercise letters/numbers/symbols, shift/caps, Unicode deletion, selected-text replacement, cursor movement and every Enter action. Type → dictate → correct → type in native/browser editors without switching IMEs. Test absent/closed input connection and rejected operations without stale retries. |
| A3 / A2 contracts | M3 accessibility/customization: `KeyboardOptions.kt`, `KeyboardSettingsActivity.kt`, layout-specific tests; serialize `TypingPanel.kt` changes after A2 | Adjustable key/label sizing, contrast, reachable/one-handed layout and independent feedback. Repeat filtering retains intended repeated letters. Essential actions have visible taps; full flow works in landscape/large fonts with no clipped or unreachable controls. TalkBack, Switch Access, external keyboard/braille workflows and actual assistive-technology users are native acceptance requirements. Announcements do not unexpectedly read private text. Reset preserves security choices. |
| A4 / A1 + A3 | M4 speech usability: `VoiceSession.kt`, `VoicePanel.kt` plus focused session tests; integrated serially | Explicit tap start/stop, optional hold, clear loading/error/elapsed state, preview warning/extension and correction. Define sample/queue bounds before extending the current 120-second allocation. Test cancel, pause/silence, permission revocation and lifecycle races; no audio persists. Measure quality, end-to-preview p50/p95, RAM, battery and thermal behavior on named physical hardware. |
| A5 / A2 + A3 + provenance decision | M5 language/editing: new reviewed layout/composition/suggestion modules and isolated tests | Explicitly supported multilingual layouts, accents, emoji, shortcuts, suggestions/correction and correction rejection. Bounded local learning with inspect/delete/off controls; no passwords, sensitive fields or clipboard history. Review dictionary/engine/model licenses and context needs before importing. Swipe remains a separate engine/data/resource decision with its own gate. |
| A6 / each candidate; coordinator owned | M6 compatibility/distribution: mobile build, CI, signing/release tooling and Obtainium docs | APK/version/source/checksum/signer match; protected stable identity, install/update and rollback-policy evidence. Test declared Android/API/ABI support and low/mid/high devices, multiple manufacturers, small/large displays, Bluetooth/calls/revocation/contention and low memory. No inferred 32-bit support. Actual Obtainium updates and offline key backup remain separate external gates. |

## iOS packages and external gates

| ID / dependency | Objective and ownership | Acceptance / blocker |
| --- | --- | --- |
| I1 / now, research only | Dated feasibility/design note, future `docs/mobile-ios.md` | Recheck current primary Apple keyboard-extension, microphone, app-handoff, App Store and distribution rules before design approval. Specify foreground speech, secure-field behavior, explicit copy/share and bounded shared-data lifetime. No private API or background-mic workaround. This planning pass does not revalidate those rules. |
| I2 / I1 | Separate native project under `mobile/ios/` | Foreground local speech app and native typing extension with explicit permissions; implement only handoff proved supported by I1. Isolated inference/dependency review, bounded data sharing, deletion and lifecycle tests. Build/test verification requires an Apple toolchain; current Windows environment cannot supply that evidence. |
| I3 / I2 | Physical acceptance, separate iOS CI/signing/distribution | Physical iPhone tests: VoiceOver, Switch Control, large text, secure-field system keyboard, external input, permission denial/interruption and containing-app handoff. Apple signing/team/distribution setup and supported-version matrix are external prerequisites. No released iOS claim before an installable verified artifact. |

Physical Android devices/assistive-technology participants, native macOS/Linux
sessions, microphones/Bluetooth/call scenarios, clean packaged profiles, and
consented speech benchmarks are evidence requirements, not reasons to stop isolated
implementation. Mark each unavailable check **external evidence pending**, identify
the needed device/person/environment, and leave its milestone incomplete. Similarly,
do not claim offline signing backup from CI or emulator success.

## First parallel assignments

1. **D1 — clipboard safety:** highest-priority security work; isolated injection and
   clipboard modules/tests. Deliver a reviewed transaction contract and adversarial
   tests before native format integration.
2. **D4 — structured recognition:** isolated transcription/segment modules/tests;
   unlocks bounded sessions, file export and later modes without touching capture UI.
3. **D6 — selective backup core:** isolated new module/tests; explicit allowlist,
   preview, bounded validation and preservation of privacy settings. Hand its API to
   the integrator for the visible flow after review.

These assignments do not overlap each other, Android PR #2, or mobile release work.
The coordinator then schedules D2/D3 integration, followed by D5 and D8, and opens
Android A1–A4 only after the foundation CI result is accounted for. Reassess ordering
whenever a security test exposes a blocker; never trade a failed security gate for
roadmap throughput.
