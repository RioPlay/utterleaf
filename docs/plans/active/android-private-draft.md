# Android private draft editor

## Goal

The user requested an editor inside the keyboard on September 12, 2026: type and
revise privately, then deliberately insert the finished text into the receiving
app without routing intermediate edits through the host or system clipboard.
This extends the completion gauntlet after the local emoji slice.

## Area and ownership

Android only: new private buffer/editor/panel and tests; `TypingPanel` capability
gates; `KeyboardIme` entry, insertion and teardown; mobile guide/roadmap. Integrator
owns existing shared files and `DeviceTest.kt`/`PrivacyCoreTest.kt`. A separate
owner may implement the pure bounded buffer and its new JVM tests. No desktop,
model, network, packaging or release changes.

## Status and design

Buffer/editor and restricted keyboard mode are implemented and independently
reviewed: 9 JVM buffer tests and 8 API 35 editor/keyboard tests passed before the
computer restart. The complete draft panel/IME integration is now implemented
and independently reviewed. Current API 35 acceptance passes **17 instrumentation
tests** (5 editor, 3 restricted keyboard, 4 panel, 5 IME), **28 JVM tests** across
the project, **14 tooling tests**, and lint with **0 errors, 54 warnings**.
Six large-label captures cover both themes and Full/Left/Right alignment, with
complete controls and zero panel scrolling. The unchanged seven-test ordinary
typing/emoji/voice regression bundle passes after a controlled emulator cold boot;
earlier repeated-session failures and the remaining uncertainty are recorded below.
These are emulator/source checks.
Physical, landscape, TalkBack/Switch Access, broad-editor and release gates remain.
Desktop continuous transcription is additional active work in its separate plan.

Existing voice transcript
editing demonstrates the local editing pattern, but its full clipboard/terminal
routes are not suitable for a clipboard-free draft. This slice adds an explicit
restricted editing mode. Any migration of the voice editor must preserve its
review, expiry, cancellation and insertion behavior and receive separate focused
regression checks; do not silently describe its current mode as clipboard-free.

- **Private draft** is an explicit keyboard action. Start with an empty buffer;
  never import surrounding/selected host text or clipboard content automatically.
- Show a bounded multiline editable preview and **Insert**, **Clear**, **Discard**.
  Explain that the draft is temporary and clears when the keyboard closes or the
  field changes. Clear empties the buffer in place; Discard returns to typing.
- The keyboard edits only the owned buffer. Preserve letters, symbols, accents,
  emoji, selection/navigation and bounded undo/redo. Use explicit capability gates
  to hide clipboard actions, terminal/modifier shortcuts, voice, Settings, keyboard
  switching and recursive Draft entry inside this mode. Do not leave dead controls.
- Keep an original pure buffer with at most 16,000 UTF-16 units and at most 20
  retained undo/redo snapshots in total. Invalid selections, malformed surrogate
  strings and edits exceeding the limit are rejected without partial insertion.
  Clear/dispose removes current text and history. No persisted text, typing
  analytics, learning, files, diagnostics, clipboard or network dependency.
- The owned editor does not invoke the system soft keyboard. Disable saved state,
  autofill, content capture, assist text, text classification, clipboard/context
  and Process Text actions, drag/receive-content and physical clipboard shortcuts.
  Prevent these paths in the editor itself as well as the visible keyboard.
- Insert captures one snapshot and calls the guarded current host connection once.
  It adds no space/newline and performs no Send/Enter action. Never fall back to
  clipboard or retry automatically. Success disposes the draft before returning
  to typing; stale/double callbacks cannot duplicate it. A refused insertion keeps
  the draft visible with a useful failure state; an uncertain outcome must not be
  presented as a safe automatic retry.
- `KeyboardIme` owns the target/UI generation. Field/subtype changes, input finish,
  hide/lock and service teardown synchronously invalidate callbacks and clear the
  draft, undo history, held actions and emoji search. The old panel cannot act on
  a new field. No cross-app retention in this slice; any later retention requires
  an explicit policy and a newly verified destination before insertion.
- Respect theme, key sizing, Full/Left/Right alignment, insets and accessibility.
  Keep draft actions reachable alongside a useful preview and the typing keys.

## Privacy claim

Intermediate draft edits do not go to the host `InputConnection`, system clipboard
or persisted Utterleaf storage. The receiving app sees the final inserted text.
This is not a claim to conceal visible text from the OS or authorized accessibility
services, or to control what the receiving app does after insertion.

## Acceptance

1. Pure buffer tests cover Unicode/selection replacement, bounded history,
   undo/redo, branch edits, cancellation/clear, invalid inputs and atomic refusal
   at the limit. Buffers and snapshots cannot be mutated through exposed objects.
2. Editor tests show private text never enters clipboard, menus, platform saved
   state, classification, autofill, content capture, assist or content imports.
   Exercise Ctrl+C/X/V, context actions, drag and stale local editor callbacks.
3. Direct panel tests verify local typing/editing/emoji and useful state of
   Insert/Clear/Discard, failed insertion, one-attempt success, reset and teardown.
4. Actual IME tests hold synthetic host text/selection/action/clipboard unchanged
   through every draft operation. Insert replaces the current selection with the
   exact final draft once; it does not submit. Verify immediate field/hide/subtype
   clearing, stale buttons, raw-field behavior, and empty reopening.
5. Owned view captures and geometry checks cover both themes, all alignments and
   large labels. Keep physical, landscape, screen-reader and broad editor limits
   explicit. Run affected typing, emoji and voice regressions after integration.

## Verification and stop

September 12 current-code receipts (dedicated `UtterleafFoundation35`, API 35,
`emulator-5554`; JDK 17 and the configured Android SDK):

```powershell
cd mobile/android
.\gradlew.bat compileDebugAndroidTestKotlin installDebug installDebugAndroidTest
adb shell am force-stop org.utterleaf.voice
adb shell am instrument -w -r -e class org.utterleaf.voice.PrivateDraftEditorTest,org.utterleaf.voice.PrivateTypingPanelTest,org.utterleaf.voice.PrivateDraftPanelTest,org.utterleaf.voice.PrivateDraftImeTest org.utterleaf.voice.test/androidx.test.runner.AndroidJUnitRunner
.\gradlew.bat lintDebug
.\gradlew.bat testDebugUnitTest
```

Instrumentation: **17 passed, no failures/skips, 122.286 seconds**. JVM XML:
**28 passed, no failures/errors/skips**, five suites. Lint: **0 errors, 54 warnings**.
From the repo root, `python -m unittest discover -s mobile/android/tools -p 'test_*.py'`
passed **14 tests**. Owned captures are in
`artifacts/screenshots/android-private-draft/`; the
[user guide](../../android-private-draft.md) includes a synthetic owned view.

Lint found and resolved an API-29 guard around API-30 content-capture methods.
The corrected guard and test use API 30; the structure callback still redacts
provided text. The saved-state override has a narrow documented MissingSuperCall
suppression: calling TextView's implementation can construct a state object with
private text/selection. This view returns EMPTY_STATE and blocks hierarchy state
dispatch. Independent re-review confirmed both choices against the official
[Android View API](https://developer.android.com/reference/android/view/View).
The live-IME fixture explicitly restarts its fresh input connection before showing
the keyboard; the combined 17-test rerun passes after correcting that test setup.

Independent review found no remaining panel/IME insertion or lifecycle blocker.
False/throwing insertion outcomes are covered by direct-panel tests; injecting
those outcomes or a reentrant field switch during a real host commit remains a
broader native-editor acceptance gap. No real-device claim follows from this pass.

### Ordinary IME regression and emulator-session investigation

The post-integration bundle ran these classes/cases with synthetic editors and
fake voice input; it did not open a microphone:

```powershell
adb shell am force-stop org.utterleaf.voice
adb shell am instrument -w -r -e class org.utterleaf.voice.EmojiImeTest,org.utterleaf.voice.KeyboardEditorContractTest,org.utterleaf.voice.VoicePanelControlsTest#primaryControlAndLocalEditingInsertExactlyOnce,org.utterleaf.voice.VoicePanelControlsTest#rejectedAutomaticInsertKeepsEditableReview,org.utterleaf.voice.DeviceTest#realPanelRejectsLateSpeechAndInsertsOnlyOnce org.utterleaf.voice.test/androidx.test.runner.AndroidJUnitRunner
```

The long-lived emulator initially passed 6/7: the repeated-activity emoji geometry
test failed because the typing IME never appeared. An isolated run passed, but
that did not resolve the regression. Two bounded fixture changes (explicit input
restart, then waiting for activity destruction) still produced session failures
and were reverted exactly. No sleep, retry workaround or weakened assertion was
retained. Logs showed invalid IME visibility tokens, stale WindowManager sessions
and launcher resume/pause timeouts while the test activity was displayed.

A discriminating run verified the dedicated `UtterleafFoundation35` AVD identity,
shut down only that emulator and restarted it with `-no-snapshot-load
-no-snapshot-save -no-boot-anim`, without wiping data. After boot and API/AVD
identity checks, `gradlew installDebugAndroidTest` installed the reverted original
fixture. The exact seven-test bundle above then passed **7/7 in 49.887 seconds**.
The production source was unchanged during this investigation.

This supports an accumulated emulator/system-session explanation, but one cold
boot does not establish that a longer fixture or app lifecycle sequence cannot
trigger it again. The named regression has a passing current-source receipt;
long-session reliability remains an explicit investigation gap, not a resolved
product defect or evidence of physical-phone behavior.

Run the new JVM buffer tests, Android tooling, affected instrumentation classes
and lint with the configured JDK/SDK. Record exact commands and counts as the
interfaces land. Independent review reads source, contract and actual evidence.
Fix findings and rerun affected checks; update user docs and platform status.
Stop this slice when the named checks pass, not merely when it compiles.

No clipboard import/export/history, host text scraping, cross-field retained
drafts, file saving, cloud rewriting, dictation-mode redesign or release is part
of this slice. Broader product gates remain active in the mobile roadmap.
