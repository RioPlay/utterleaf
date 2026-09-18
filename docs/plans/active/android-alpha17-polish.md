# Android alpha17 everyday typing stabilization

## Goal

Resolve the reported typing stalls, unexplained keyboard gaps and inconsistent
word completions in the shipping keyboard before adding more features. Baseline:
alpha17, Android checkout at `cd0a0f1`; work branch `fix/android-alpha17-polish`.
The mixed checkpoint and experimental keyboard implementations are not targets.
Reported device: Pixel 8 Pro, current stable GrapheneOS (exact build not yet
recorded). Symptoms occur across apps and in the internal scratch pad, so shared
local touch/render behavior must be checked as well as editor communication.

## Area and ownership

- Typing package: `KeyboardIme.kt`, `TypingPanel.kt`, suggestion engine/repository
  and focused suggestion tests. A Luna implementation owner investigates synchronous
  editor reads, refresh timing, stale completion admission and view churn.
- Geometry package: inset/layout helpers and focused geometry tests, assigned to
  a second Luna owner after diagnosis. Changes to the shared IME/panel files go
  through the typing owner so each file has one writer.
- Shared touch package: `ModifierChords.kt` and a focused dispatch regression;
  a separate Luna owner addresses redundant modifier-state notifications on
  ordinary key down. Preserve existing held-modifier and rollover behavior.
- Integrator: this plan, mobile roadmap, verification and independent diff review.
  Do not edit `DeviceTest.kt` or `PrivacyCoreTest.kt` in parallel.

## Constraints

Preserve explicit local preferences and staged Apply/Cancel/reset behavior. Reset
must retain models. No new permissions, ambient capture, typing history, telemetry,
learning, network services or unverified models. Retain password/raw-field gates,
session invalidation, literal terminal input and accessible tap alternatives.
Navigation safety insets and intentional user bottom spacing are not arbitrary
blank space to delete. Keep Android independent of desktop and experimental cores.

## Acceptance

1. Ordinary typing does not synchronously fetch suggestion context or load the
   dictionary on every key event. Deferred work is bounded and stale work cannot
   update a new field or detached panel. Slow-editor tests establish that key
   dispatch remains usable while suggestions are pending.
2. Completions follow committed text, external cursor/selection updates, deletion,
   punctuation and editor/panel changes. A chip may only replace the exact current
   word from its own valid session; same-length different words and selected text
   fail closed. Unsupported editor reads clear suggestions without breaking typing.
3. An empty completion state does not create a decorative blank band or move key
   targets as candidates appear/disappear. Symbols, letters, password/raw fields,
   hide/reopen and panel transitions have explicit geometry expectations.
4. Insets are applied exactly once to the region that needs them. Default and
   customized bottom spacing remain distinguishable and testable. Verify portrait,
   landscape and gesture/three-button navigation where available; mark untested
   combinations rather than extrapolating from one emulator.
5. Focused regressions, tooling tests, JVM tests, Kotlin test compilation and lint
   pass. Review actual rendered keyboard states and record evidence separately
   from physical-phone acceptance.

## Verification

From the owning checkout:

- `python -m unittest discover -s mobile/android/tools -p 'test_*.py'`
- In `mobile/android`: `gradlew.bat testDebugUnitTest lintDebug assembleDebug assembleDebugAndroidTest --no-daemon --console=plain`
- The final 79-test emulator run used the direct instrumentation command below
  so owned-view captures remain available after the run. Gradle's connected
  runner removes these APKs and their external files during cleanup.
- Independent reviewer reads this contract, final diff and test output. Resolve
  correctness, privacy, lifecycle and regression findings before handing off.

From the checkout root, after building the APKs (PowerShell):

```powershell
$adb = "$env:LOCALAPPDATA\Android\Sdk\platform-tools\adb.exe"
& $adb install -r mobile/android/app/build/outputs/apk/debug/app-debug.apk
& $adb install -r -t mobile/android/app/build/outputs/apk/androidTest/debug/app-debug-androidTest.apk
$names = @('SuggestionStripTest','KeyboardSpacingTest','KeyboardSurfaceLatencyTest',
    'KeyboardGeometryTest','HeldModifiersTest','TypingRolloverTest','KeyboardGesturesTest',
    'KeyboardEditorContractTest','KeyboardTuningTest','PersistenceTest','PrivateTypingPanelTest',
    'PrivateDraftPanelTest','PrivateDraftEditorTest','BackspaceSelectionTest','ComposeImeTest')
$classes = ($names | ForEach-Object { "org.utterleaf.voice.$_" }) -join ','
& $adb shell am instrument -w -r -e class $classes -e r2Screenshots alpha17-polish-final org.utterleaf.voice.test/androidx.test.runner.AndroidJUnitRunner
```

Require the runner's `OK (79 tests)` summary; adb's exit status alone does not
establish a passing test run.

## Finishing gates

First finish this bounded stabilization patch. Then run exact-revision Android CI
and the signed alpha install/upgrade process for a release candidate. Before calling
the keyboard stable, verify the reported behavior on the user's phone and named
editors, plus accessibility, landscape, interruptions and update retention gates
already listed in the mobile roadmap. A green emulator run is not phone proof.

| Gate | Observable check | Status |
| --- | --- | --- |
| Typing correctness | Rapid synthetic text with repeated letters, deletion, punctuation, cursor repositioning and completion produces exactly the expected text | Scoped emulator regressions pass; real-editor/phone acceptance open |
| Responsiveness | Slow suggestion reads do not block key dispatch; on reference phones measure touch-to-text P50/P95 against the existing proposed 50 ms P95 target, without storing personal text | Blocked-reader and bounded-worker regressions pass; phone measurement open |
| Geometry | Compare empty, matching and unmatched words; space/delete; symbols return; hide/reopen; default and nonzero bottom spacing | Scoped portrait/gesture-navigation emulator checks and owned-view captures pass; landscape/three-button/phone checks open |
| Editor compatibility | Repeat the journey in the app practice field, private draft, a messaging editor, browser text field, password field and raw terminal; record app/OS versions and unsupported behavior | Pixel 8 Pro/current stable GrapheneOS reported; exact build and external editor versions open |
| Accessibility | Suggestions, empty states, toolbar and correction reachable with TalkBack/Switch Access; large text and landscape stay usable | Physical assistive testing open |
| Release candidate | Exact-revision CI, signed APK continuity, install/upgrade with model/preferences retained, reviewed screenshots and accurate known limits | Exact-revision CI passed and merged; signed upgrade not started; alpha17 remains published |

For manual reproduction, type `hello world`, move the caret back into the first
word, select a range, return to the end, delete and retype, then type an unmatched
word such as `zzzzq`. Repeat after switching symbols, hiding/reopening the IME and
changing fields. Check that letters stay under the finger and suggestions follow
the current collapsed caret. Use only synthetic text for captured evidence.

## Non-goals and stop

No new prediction engine, autocorrection, swipe, languages, redesign, foundation
migration, desktop work or automatic stable-release declaration. Stop editing when
the bounded acceptance checks pass and review is clean; list remaining device and
release gates explicitly. Do not turn a usability report into broad feature work.

## Evidence and progress

- September 17, 2026: clean alpha17 baseline verified; GitHub release metadata
  confirms publication. Baseline: 14 tooling tests, 40 JVM tests (cached Gradle
  result verified in XML), and 5 live suggestion/geometry tests passed on API 35,
  1080 x 2400 at 420 dpi with gesture navigation. No physical device connected.
- Source inspection found synchronous before-cursor reads in the suggestion
  refresh path, no refresh from `onUpdateSelection`, and completion revalidation
  checking trailing length without comparing the actual word. These are concrete
  correction targets, not proof of the cause of every reported phone delay.
- Geometry audit found a 1 px empty spacer versus 40 dp candidate row. The fix
  keeps a 40 dp row with truthful empty states and reuses candidate views. No
  evidence supports removing system navigation padding; focused tests cover
  non-accumulating insets and explicit bottom spacing, including private drafts.
- Final production build: 14 tooling tests, 40 JVM tests, lint, debug APK and
  test APK compilation pass. The combined API 35 run passed **79/79**, with no
  failures or skips. Its raw local receipt is
  `.grok/alpha17-polish-final-instrumentation.txt`. An earlier broader run caught
  two new test defects and a Ctrl-release regression; those were corrected
  before the successful rerun (earlier receipt retained locally).
- Final review strengthened the selected-range test to reject before any editor
  read and to use the matching before-selection word in the live case. The test
  APK rebuilt and `SuggestionStripTest#completionRejectsSelectedText` passed
  separately; receipt: `.grok/alpha17-polish-selected-guard.txt`.
- 46 owned-view captures are in
  `artifacts/screenshots/android-alpha17-polish/alpha17-polish-final/`.
  Representative normal, one-hand letter/symbol, empty/candidate and explicit
  dark-theme states were inspected. The stale legacy light/dark test flag was
  replaced with explicit `ThemeMode` selection. These are emulator/app-view
  captures, not physical phone or navigation-bar screenshot evidence.
- Shared local audit found an unnecessary `ModifierChords.abort()` notification
  on every ordinary key DOWN, triggering `TypingPanel.updateCase()` before the
  child receives the event. The fix tracks notified modifier state and preserves
  reset after the last held finger leaves. Held-modifier, rollover, cancellation
  and ordinary-touch tests pass. Its phone latency effect remains unmeasured.
- Independent review found no remaining production blocker after the release
  regression correction. Stronger exact-word/selection checks, rollback after
  failed insertion, 20-request coalescing, stale-work invalidation, external caret
  refresh and preference restoration are covered by the suggestion tests.

## Remaining limits

The bounded worker cannot interrupt an in-flight synchronous editor read. A stuck
old editor can delay suggestions for a later session until that read returns or
the platform times it out; ordinary typing remains independent. Keep the single
worker bound rather than spawning replacement threads on every timeout. Chip taps
still re-read the bounded word before any destructive edit and can wait for a
slow editor. Arbitrary same-position external text changes without an editor
selection notification are not continuously monitored.

This patch merged to main as PR #52 (`80bec1b`, source `d768067`). Exact-revision
Android CI run 35290270474 on that source passed **173/173** instrumentation
tests with 0 skips and 0 failures, plus 14 tooling tests and successful JVM/lint
builds. Signed upgrade, Pixel 8 Pro/GrapheneOS, named editors, landscape,
three-button navigation and assistive-technology acceptance remain open. No
stable-readiness claim follows from this patch or the emulator count.
