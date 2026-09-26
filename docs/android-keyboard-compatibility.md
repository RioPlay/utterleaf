# Android keyboard compatibility and performance evidence

[Mobile roadmap](mobile-roadmap.md) ·
[Capability and experience plan](plans/active/android-experience-refresh.md)

This is the Milestone B evidence record. It is not a blanket compatibility claim.
Every target and metric starts `Not run`; update a result only after recording
the exact environment and evidence below. Routine Android progress and preview
releases do not require a new physical-phone, live third-party-editor or
assistive-technology campaign. The completed matrix, performance comparison and
accessibility review are required before calling the redesign complete, and
unperformed rows continue to limit claims.

## Result rules

Use only these states:

- **Not run** — no qualifying evidence has been recorded.
- **Pass** — observed behavior matched the stated expectation, with evidence.
- **Partial** — only part of the action or environment was exercised.
- **Fail** — observed behavior did not match the expectation.
- **Unsupported** — the host/platform cannot support the action; record why.
- **Blocked** — the run could not start or finish; record the blocker.

A compile, direct-panel test or different host application is not evidence for a
named target. Emulator evidence must remain labeled emulator evidence. Never use
real credentials, valuable terminal sessions or private message content; synthetic
non-sensitive text is sufficient.

Each changed cell needs:

- Utterleaf revision/version and APK type;
- application/package and version, field kind and screen;
- Android version, device or emulator, input/navigation mode and orientation;
- relevant Utterleaf preferences and speech model;
- expected behavior, observed behavior and recovery result;
- date, operator and evidence link or exact command/artifact;
- limitations, skips, retries and whether text could have been exposed.

## Compatibility matrix

Abbreviations: `Bksp` is Backspace; `Act` is Enter/editor action; `Dict` is
dictation; `Sug` is suggestions; `Reset` is Tools/session reset. `NR` means
**Not run**. Replace each cell independently; do not promote a whole row from one
successful action. For Next/Done forms, `Act` passes only when both transitions
have their own observation.

| Target | Type | Bksp | Hold | Cursor | Select | Copy | Cut | Paste | Act | Dict | Sug | Reset |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Standard Android field | Partial | NR | NR | NR | NR | NR | NR | NR | Pass | NR | Pass | Partial |
| Chrome | NR | NR | NR | NR | NR | NR | NR | NR | NR | NR | NR | NR |
| Firefox | NR | NR | NR | NR | NR | NR | NR | NR | NR | NR | NR | NR |
| Signal | NR | NR | NR | NR | NR | NR | NR | NR | NR | NR | NR | NR |
| Google Messages | NR | NR | NR | NR | NR | NR | NR | NR | NR | NR | NR | NR |
| Gmail | NR | NR | NR | NR | NR | NR | NR | NR | NR | NR | NR | NR |
| Google Docs | NR | NR | NR | NR | NR | NR | NR | NR | NR | NR | NR | NR |
| Termux | NR | NR | NR | NR | NR | NR | NR | NR | NR | NR | NR | NR |
| WebView | NR | NR | NR | NR | NR | NR | NR | NR | NR | NR | NR | NR |
| Password manager | NR | NR | NR | NR | NR | NR | NR | NR | NR | NR | NR | NR |
| Numeric input | NR | NR | NR | NR | NR | NR | NR | NR | NR | NR | NR | NR |
| Email input | Partial | NR | NR | NR | NR | NR | NR | NR | NR | NR | Pass | Partial |
| URL input | Partial | NR | NR | NR | NR | NR | NR | NR | NR | NR | Pass | Partial |
| Search field | NR | NR | NR | NR | NR | NR | NR | NR | Pass | NR | NR | NR |
| Multiline text | NR | NR | NR | NR | NR | NR | NR | NR | Pass | NR | NR | NR |
| Next/Done form fields | NR | NR | NR | NR | NR | NR | NR | NR | Partial | NR | NR | NR |

For every target, `Type` covers ordinary typing and visible key feedback; `Hold`
covers configured long-press and repeat behavior; cursor and selection cover both
successful movement and boundaries; Copy/Cut/Paste record disabled or unsupported
behavior as well as success. `Reset` verifies that Tools, modifiers, selection,
pending holds, suggestions and dictation do not leak after the applicable field,
application, hide/show or sensitive transition.

### Native editor run N1 — September 26, 2026

N1 supports only the changed cells above. No third-party row is promoted.
The same named checks subsequently passed in the final 228/228 run (303.121 test
seconds, zero failures/errors/skips), archived in
`.grok/validation/model-trust-20260926/full-final-run`, APK SHA-256
`728f27dc28c7e7868795d4a586ab45df5118b588de4ea3e8baca25adfa394bd8` (the P1 candidate).
Their environment, scope and limitations below are unchanged.

| Field | Recorded value |
| --- | --- |
| Date/operator | September 26, 2026; Codex-operated instrumentation, independently source-reviewed |
| Product | Local dirty `codex/android-polish-alpha20`, debug 0.1.0-alpha20 (20), `org.utterleaf.voice` |
| APK SHA-256 | `9656da86113da153f9023a73d95bef55552eecbfaf29cadac933c46a7912ec92` |
| Environment | `UtterleafFoundation35`, Android 15/API 35, x86_64 emulator, software renderer, no audio; fingerprint `google/sdk_gphone64_x86_64/emu64xa:15/AE3A.240806.043/12960925:userdebug/dev-keys` |
| Host | Debug-only `.KeyboardEditorContractActivity`: one synthetic native EditText; reset case uses `.KeyboardTestActivity`, first field `Synthetic keyboard test` |
| Input/orientation/navigation | Soft IME actions via accessibility clicks. Rotation case explicitly portrait → landscape → portrait with reopen. Other named cases do not assert orientation; navigation mode unknown. |
| Preferences | Suggestion cases save defaults and restore the prior snapshot: QWERTY/full alignment/system theme, suggestions/extra keys/number row/secondary hints/delete and arrow repeat/auto-capitalization/borders enabled, 320 ms hold, automatic key height, zero extra bottom padding, no large/light/haptics/repeat guard/split landscape. Action and rotation cases force extra keys only; other options inherited, not independently recorded. |
| Model/privacy | Model not used; no microphone, speech, real credentials or private text. Only synthetic fixture text. |
| Command | From `mobile/android`: `.\gradlew.bat testDebugUnitTest lintDebug connectedDebugAndroidTest --no-daemon` |
| Result/archive | 228/228 ordinary emulator tests, zero failures/errors/skips, 309.344 test seconds. `.grok/validation/model-trust-20260926/full-first-run` contains connected XML/logs, APK, JVM XML and lint. Prior IME restored to Gboard. |

Observed expectations and limits:

- `SuggestionStripTest.stripCompletesTheComposingWordThroughTheEditor` types
  `hel`, renders a real candidate and commits completion plus spacing. Standard
  suggestions pass; typing remains partial because this case does not observe
  pressed-key drawing.
- `sameEditorMetadataRestartsGateHostManagedSuggestionsWithoutBlockingTyping`
  restarts the same native editor with email, web-email and URI metadata. Stale
  candidates disappear, literal `hel` still commits, and ordinary prose restores
  real candidates. Email/URI suggestion suppression passes; typing is partial
  (no press-feedback observation) and reset is partial (suggestion substate only).
- `KeyboardEditorContractTest.freshSessionsReplaceSelectionDeleteUnicodeAndDispatchEnter`
  separately observes Go/Search/Send/Next/Previous/Done callbacks and newline for
  multiline NONE/UNSPECIFIED/NO_ENTER_ACTION. Native standard/search/multiline
  dispatch passes. Next/Done forms remain **partial**: both callbacks are observed,
  but the single-field fixture does not establish actual multi-field focus movement
  or Done-driven dismissal.
- `KeyboardLifecycleTest.portraitLandscapePortraitRebuildsImeAndClearsTransientTools`
  observes old controls detached, the daily layer restored, Ctrl cleared and fresh
  typing after each explicit reopen. Standard reset is partial: this method does
  not establish every selection/hold/suggestion/dictation reset in the matrix.
- JVM capability tables and direct-panel tests are policy/component evidence,
  not native numeric typing or live search-suggestion evidence. Those cells remain
  unrun. Other actions may have component tests, but are not promoted here without
  their own complete per-target record.

## Per-run record

| Field | Recorded value |
| --- | --- |
| Target and action | Not run |
| Date and operator | Not run |
| Utterleaf revision/version/APK | Not run |
| App/package/version and field | Not run |
| Android/device/emulator | Not run |
| Navigation/orientation/input mode | Not run |
| Preferences/model | Not run |
| Expected | Not run |
| Observed and recovery | Not run |
| Result | Not run |
| Command/artifact/link | Not run |
| Limitations/privacy notes | Not run |

## Performance baseline and comparison

Record raw samples or a machine-readable artifact, sample count, warm/cold state,
device/emulator, Android build, orientation, model, Utterleaf revision and method.
Report at least median and p95 for latency metrics; do not compare unmatched
environments. A faster emulator run is not a physical-device responsiveness claim.

| Metric | Baseline | After change | Evidence/conditions |
| --- | --- | --- | --- |
| Keyboard show latency | First observed 626.96 ms (n=1); warm 94.86 / 129.53 ms (n=30) | Not run | P1, first-draw proxy |
| Key press to visible feedback | 31.80 / 48.77 ms (n=30) | Not run | P1, DOWN → pressed-key first draw, not physical presentation |
| Key press to text commit | 3.95 / 7.46 ms (n=30) | Not run | P1, UP → exact synthetic native host text |
| Candidate generation latency | 0.234 / 0.494 ms (n=30) | Not run | P1, shipped dictionary/repository worker |
| Candidate rendering latency | 14.73 / 16.35 ms (n=30) | Not run | P1, attached panel first-draw proxy |
| Tools-layer switching | 33.98 / 36.09 ms (n=30) | Not run | P1, injected opening touch; unmeasured direct close reset |
| Dictation startup | 64.31 / 84.36 ms (n=30) | Not run | P1, real capture Listening callback, emulator audio disabled |
| Speech processing | First 5.673 s (n=1); follow-up 5.549 / 5.829 s (n=5) | Not run | P1, tiny.en/JFK; every decode initializes native model |
| Result insertion | Local proxy 4.19 / 18.94 ms (n=30); host insertion Not run | Not run | P1, VoicePanel callback → unattached local EditText |
| Memory usage | Total PSS 82,806 KiB IME-visible idle; 84,668 after typing; 98,898 after voice; sampled decode peak 226,674 KiB | Not run | P1; decode sampling n=129; Java/native checkpoints also archived |
| Sustained-typing frame behavior | 17.78 / 34.13 ms total frame time (n=440); 322 over refresh period; zero callback drops | Not run | P1, 200 keys targeting 10 Hz; 199 intervals median 100.05 / p95 104.83 ms |

### Performance run P1 — accepted pre-visual baseline

Values separated by `/` above are median / nearest-rank p95. This is a measured
baseline, **not** a responsiveness pass threshold. In particular, 322/440 software
emulator frames exceeded the approximately 16.67 ms refresh period; do not describe
this as smooth physical-phone typing. A later matched comparison is still required.

- September 26, 2026, Codex-operated `UtterleafFoundation35`, Android 15/API 35,
  x86_64, software renderer, portrait, 1080×2400 at 420 dpi, en-US, approximately
  60 Hz. Same fingerprint as N1; emulator launched without audio or snapshots.
- Debug 0.1.0-alpha20 (20), dirty revision
  `4458fed65838d69d1f03bb2f3a866e8414d3be84`; exact product APK SHA-256
  `728f27dc28c7e7868795d4a586ab45df5118b588de4ea3e8baca25adfa394bd8`.
  This includes the unconditional native-result byte cleanup after N1.
- Effective keyboard options: defaults except auto-capitalization and suggestions
  disabled for the typing measurements; full QWERTY, extra keys/number row enabled,
  320 ms hold, system theme, no split landscape/haptics. The separate candidate
  measurements exercise the actual repository and an attached suggestion panel;
  that panel explicitly overrides `suggestions=true`. The canonical options in
  metadata describe the live-IME typing phase, not this per-metric override.
  Voice hold-to-insert is disabled. Full options are archived, not inferred.
- Verified tiny.en: 77,704,715 bytes, SHA-256
  `921e4cf8686fddf993dcd081a5da5b6c365bfde1162e72b08d75ac75289920b1f`.
  Public JFK fixture SHA-256
  `59dfb9a4acb36fe2a2affc14bacbee2920ff435cb13cc314a08c13f66ba7860e`.
  Dictionary: 98,252 bytes / 10,989 words, SHA-256
  `515c8ed9e32da7caf104570855990777b8ef9bfdc07bb8a71167ed5a550d2445`.
- Command: `.\gradlew.bat connectedDebugAndroidTest -PutterleafPerformance=true --no-daemon`.
  The single isolated test passed (91.387 test seconds), zero failures/errors/skips.
  Parser validation confirmed one run, complete body/cleanup, all sample counts
  and matching APK/device provenance. Raw logs, APK, pre-visual source snapshot,
  test source, full metadata, raw JSONL and summaries are in
  `.grok/validation/performance-20260926/baseline`.
- Timings use `elapsedRealtimeNanos`; unmeasured setup waits for settled geometry.
  Key-feedback cancellation has a 200 ms safety bound before alternate-key hold,
  not a performance acceptance limit. Decode has zero warmups; first/follow-up
  labels describe order/cache only. Other inexpensive phases use five warmups.
  Capture uses temporary shell microphone identity with emulator audio disabled.
  Cleanup restores prior options/input methods/model state and drops that identity.
- First draw is not physical display presentation. Local result insertion is not
  a host InputConnection measurement. This records no user speech or field text,
  adds no production diagnostics, and establishes no phone thermal/battery,
  one-handed, third-party editor or final redesign-completion claim.
- Independent evidence review recomputed all 25 metrics from 1,026 samples and
  matched the log, declared counts, timing arithmetic and summary exactly. Idle
  memory is measured with the IME already visible after show sampling, not a
  no-keyboard process. The instrumentation APK was captured afterward from the
  unchanged build output (Gradle reported its packaging up-to-date through P1
  and the following ordinary run); it is supplemental provenance, not a test-APK
  hash recorded by the original parser or cryptographic execution attestation.
  Its SHA-256 is `581faaa333961095a6504a35cca487882757ebc172930be4a3cd8ab2f96c9ddd`.

## Final accessibility audit record

Record screen-reader names/state, pressed/selected/toggle semantics, touch targets,
font scaling, contrast, non-color cues, reduced motion, portrait, landscape and
one-handed layouts. Separate automated/emulator, physical-phone and live
assistive-technology evidence. Unperformed checks remain `Not run`; do not infer
TalkBack, Switch Access or physical comfort from view bounds or screenshots.
