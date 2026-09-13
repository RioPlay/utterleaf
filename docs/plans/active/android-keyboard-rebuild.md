# Independent Android keyboard completion

## Goal

Build a complete, comfortable Android keyboard with FUTO-level useful capability,
Utterleaf's own implementation/design and security/privacy by construction.
The [product specification](../../android-keyboard-product-spec.md) defines flows,
reference features and quality gates. Status belongs in the
[mobile roadmap](../../mobile-roadmap.md).

## Area and ownership

Android only: `mobile/android/` source/tests/resources and Android documentation.
One writer owns pointer/layout changes at a time; editor/session changes require
agreed callback contracts. Never edit `DeviceTest.kt` and `PrivacyCoreTest.kt` in
parallel with other Android work. Desktop and shared release infrastructure are
outside this plan. Use the AGENTS.md Aden navigation sequence for each code slice.

## Constraints

- Independent implementation; the LatinIME extraction proposal is superseded.
- Preserve current uncommitted hardening and existing verified speech imports.
- No ambient recording, passive typing collection, automatic clipboard history,
  unchecked model/native add-on loading or expanded network permissions.
- Stable explicit preferences, accessible alternatives, safe cancellation and
  Reset to defaults that preserves models and other user data.
- Design and performance are part of each slice, with physical-device and
  assistive-technology evidence kept separate from emulator tests.

## Work packages and acceptance

| Package | Observable completion | Dependency |
| --- | --- | --- |
| R0 — Product contract | Current FUTO baseline, direct user evidence, independent-foundation decision, task flows and measurable release gates agree across docs | First |
| R1 — Touch and editor foundation | Ordinary two-thumb overlaps preserve intentional input; holds/cancel/delete/modifiers remain deterministic; Unicode/selection/Enter and field changes have focused regressions | Existing hardening retained; implementation can proceed in bounded sub-slices |
| R2 — Daily design and ergonomics | Reviewed Daily/Edit/Voice states, stable geometry and coherent light/dark visuals; reachable one-hand layout, independent sizing, clear settings and tap alternatives pass task/capture review | R1 touch contract; design/prototypes can run alongside R1 |
| R3 — Language and repair | Named reviewed alphabetic layouts, local emoji, explicit vocabulary/snippets and composing-range correction with immediate restore; layout/dictionary/composition/speech matrix | Editor foundation; each resource independently reviewed |
| R4 — Prediction and swipe | Bounded offline engines, mixed-language behavior, candidate repair, licence/provenance review and matched phone latency/error/resource measurements | R3 correction and data contracts |
| R5 — Advanced reach and customization | Split/floating/tablet/orientation profiles, toolbar preferences, bounded custom themes/layouts and additional power keys each pass their own accessibility/editor gates | Stable geometry/session boundaries; independent features need not wait for R4 |
| R6 — Release acceptance | Named physical editor/phone/language/accessibility matrix, performance evidence and signed upgrade preservation; known unsupported cases published | Applies continuously; required before stable-release claims |

Each package needs a bounded implementation contract before edits: exact behavior,
owning files, default/cancel/failure paths, acceptance cases and verification.
Passing one touch improvement does not complete all of R1. Do not enable prediction
or swipe through a placeholder implementation to make a parity checklist look full.

## Verification

- Android tooling: `python -m unittest discover -s mobile/android/tools -p test_*.py`
- In `mobile/android`, with JDK 17 and Android SDK configured:
  `gradlew.bat testDebugUnitTest --no-daemon`
- Changed view/editor behavior: run its named instrumentation classes with
  `gradlew.bat connectedDebugAndroidTest -Pandroid.testInstrumentationRunnerArguments.class=<classes> --no-daemon`
- `gradlew.bat lintDebug --no-daemon` when Android source changes.
- Live-IME captures and physical/assistive-technology task trials for each visual
  or interaction milestone. Record device, OS, build, conditions and limitations.
- Documentation-only changes: inspect the diff, local links and agreement with
  roadmap/source status; do not rebuild native binaries just for prose changes.

## Non-goals

No desktop rewrite, LatinIME/FUTO source port, cloud keyboard, hidden telemetry,
universal language claim or claim of superiority without matched evidence.
No release, version bump or replacement of the installed consumer APK in this
planning/foundation pass. External community research is read-only.

## Stop

Stop each implementation slice when its named checks pass, docs match the result
and independent review finds no unresolved regression. Record the next bounded
slice and external acceptance gaps; do not broaden a successful change into the
entire keyboard. This plan remains active until the scoped product gates pass.

## Progress

- September 12: current FUTO reference, independent architecture and UX acceptance
  contract documented. Existing [hardening](android-keyboard-hardening.md) remains
  intact and retains its separate physical/accessibility acceptance work.
- Android tooling baseline: 7 tests passed locally on September 12.
- R1 ordinary-key rollover implemented in `KeyboardSurface.kt`, with gesture
  eligibility in `KeyboardGestures.kt`, registration/reset in `TypingPanel.kt` and
  `TypingRolloverTest.kt`. It preserves pointer-down order through continuous
  two-thumb overlap, cancels slide-off/re-entry and stale geometry/sessions,
  respects active hold/alternate ownership and bounds deferred state to 32 presses.
  Utility keys and space/modifier gestures retain their separate routing.
- Final local verification: 8 JVM and 33 API 35 instrumented tests, zero
  failures/errors/skips; lint passes (0 errors, 48 existing warnings). Command in
  `mobile/android` with JDK 17/SDK configured:
  `gradlew.bat testDebugUnitTest lintDebug connectedDebugAndroidTest -Pandroid.testInstrumentationRunnerArguments.class=org.utterleaf.voice.TypingRolloverTest,org.utterleaf.voice.KeyboardGesturesTest,org.utterleaf.voice.HeldModifiersTest,org.utterleaf.voice.DeleteRepeaterTest,org.utterleaf.voice.AlternatePanelTest,org.utterleaf.voice.KeyboardTuningTest --no-daemon`.
- Independent source review identified and resolved continuous pointer reuse,
  previously opened hold pickers, geometry invalidation and queue-bound gaps.
  The final test XML was inspected separately. No APK was published.

## Next bounded slices

### R1 native editor contract — September 12

`KeyboardEditorContractTest` now uses the debug-only
`KeyboardEditorContractActivity` and actual IME accessibility actions. A fresh
activity per Enter contract avoids reusing prior field metadata. Verification
covers reversed Unicode selection replacement; native backspace for a combining
mark (retaining the base letter), supplementary emoji and family ZWJ sequence;
forward emoji deletion through Keyboard tools; Go/Search/Send/Next/Previous/Done;
None/Unspecified/NO_ENTER_ACTION newline; and raw TYPE_NULL Enter dispatch.

The initial fixture had focus/interactive-window and multiline flag mistakes;
these were corrected rather than changing correct production Enter behavior.
TYPE_NULL is asserted as a raw event, not assumed to insert a newline. Temporary
production metadata hooks were removed during independent review.

With JDK 17/Android SDK configured, the final command in `mobile/android` was
`gradlew.bat connectedDebugAndroidTest -Pandroid.testInstrumentationRunnerArguments.class=org.utterleaf.voice.KeyboardEditorContractTest --no-daemon`:
1 test, 0 failures/errors/skips, 23.481 seconds. Root inspected its result XML.
The preceding combined contract/rollover/gesture/modifier/delete/alternate bundle
passed 31 instrumented tests and 8 JVM tests; lint reported 0 errors and 48 existing
warnings. No model import, microphone capture or release publication was required.

This satisfies the named native EditText cases only. Browser/rich editor behavior,
physical phones, keyboard accessibility and broader Unicode cases remain open.

### Following work

- Broaden R1 acceptance across named browser/rich editors; current native field
  evidence does not establish editor parity or provide glide typing.
- R2 source slices below and the one-hand alignment flow now have named emulator
  and visual evidence. Continue physical reach and accessibility acceptance.
- R3 now includes separately reviewed original letter-layout and local-emoji
  source slices. The [private draft editor](android-private-draft.md) is implemented
  and independently reviewed, with 17 API 35 draft checks and a seven-test ordinary
  IME regression receipt after a controlled emulator cold boot. Its earlier
  repeated-session failures and physical/release gaps remain documented. The
  [Latin Compose slice](android-latin-compose.md) now supplies an original explicit
  mark/letter flow with focused source/emulator checks and independent review.
  Explicit vocabulary/snippets and
  reversible correction remain separate work.
- Physical two-thumb, TalkBack and Switch Access trials remain open. Automated
  event traces cannot establish comfort, typing accuracy or accessible usability.

### R2 first geometry slice — September 12

Goal: terminal controls respect the independent number-row preference, and a
rejected key/action reports failure without changing the keyboard's measured
height or reachable key positions. The Android owner edits `TypingPanel.kt`, a
dedicated `KeyboardGeometryTest.kt`, and the two existing failure-status assertions
in editor/terminal tests. The integrator owns documentation and independent review.

Render digits only when the number-row preference is enabled. Preserve existing
Fn/symbol exclusions and terminal controls. Replace only generic post-action
`Key unavailable` layout text with a transient native Toast and the existing
accessibility announcement; alternate-picker instructions remain intact. No
new preference, permission, permanent status spacer or custom overlay.

Acceptance: compare actual live-IME and panel bounds before/after failures; assert
number-row presence for each terminal/number preference combination, unchanged
failed-action editor contents and preserved utility-key reach. Capture normal,
number-row, terminal and failure states, including compact/large-label and theme
cases where the emulator supports them. Restore preferences and IME test state.
Run the focused instrumentation classes, JVM tests and `lintDebug`; inspect XML
and captures. This does not establish physical-phone comfort or TalkBack usability.

Non-goals: one-hand/split/floating layouts, layer-height redesign, voice capture
or release publication. This slice passed independent review and its final checks.
The subsequent [one-hand alignment slice](android-one-hand.md) implements the
Settings/Tools/layout flow and records its separate review and test evidence.
The next [letter-layout slice](android-letter-layouts.md) implements original
QWERTY/QWERTZ/AZERTY letter positions, positional hints and local Settings/Tools
preferences. Its source review, 50-test regression and final three-test live
matrix pass; 12 JVM tests, 7 tooling tests and lint are recorded separately.
Eighteen layout/Tools captures plus empty Settings passed visual review.
This starts R3 without claiming complete languages, dictionaries or speech
switching. Physical, external-editor and release gates remain open.

The subsequent [local emoji slice](android-local-emoji.md) adds a reviewed
3,944-entry fully-qualified Emoji 17 catalog, nine categories, local CLDR 48
English search and explicit variants. Exact insertion passed the native IME
fixture, and transient query state has lifecycle checks. Seventy-five distinct
API 35 instrumentation tests, 19 JVM tests, 14 tooling tests, lint and all 18
owned picker captures passed their recorded checks. This is unreleased
source/emulator evidence; physical, landscape, assistive-technology and broad
host-editor acceptance remain open.

Final evidence on `UtterleafFoundation35`, API 35, 1080 × 2400 at density 420:

- `gradlew.bat testDebugUnitTest lintDebug installDebug installDebugAndroidTest --no-daemon`:
  8 JVM tests passed; lint 0 errors, 47 warnings.
- `adb -s emulator-5554 shell am instrument -w -r -e class org.utterleaf.voice.KeyboardGeometryTest,org.utterleaf.voice.KeyboardTuningTest,org.utterleaf.voice.EditorActionsTest,org.utterleaf.voice.TerminalInputTest,org.utterleaf.voice.TypingRolloverTest -e r2Screenshots r2 org.utterleaf.voice.test/androidx.test.runner.AndroidJUnitRunner`:
  29 tests passed, 0 failures/errors/skips, 36.409 seconds. The runner output was
  inspected separately. The explicit install/instrument path keeps optional
  capture files available for inspection before Gradle's usual uninstall.
- Six states were rendered from the actual attached keyboard view: normal,
  protected-field failure, number row, terminal, large dark and large light.
  Local artifacts: `artifacts/screenshots/android-r2/r2/*-keyboard.png`.
  Renders exclude editor text and system Toasts. The test separately verifies
  the accessibility failure event and unchanged selected synthetic protected text.
  Independent review also added cancellation of old Toasts after new actions,
  and the voice icon now follows theme/focus text color for legibility.

An early node read returned off-screen positions while the IME was appearing.
The harness now waits, with a deadline, for stable in-display bounds; no production
ScrollView change was needed. System screenshots intentionally mask the secure
IME. Optional API 29+ view captures use the public
[WindowInspector](https://developer.android.com/reference/android/view/inspector/WindowInspector)
API to locate only this process's live keyboard, without changing `FLAG_SECURE`.
The test writes to the target app's own external-files directory, accepts only a
bounded simple directory name, and restores preferences/IME/automation flags.
An older API receives an explicit unsupported-capture error when capture is requested.
These are emulator/source checks, not physical accessibility or timing acceptance.
