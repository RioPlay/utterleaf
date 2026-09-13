# Android one-hand alignment

## Goal and area

Provide explicit Full width, Left hand and Right hand layouts for the original
typing keyboard, with a visible way to return to Full width. Full width remains
the default. The Android owner edits `KeyboardOptions.kt`, `TypingPanel.kt`,
`KeyboardSettingsActivity.kt` and focused Android tests. Documentation and
independent review belong to the integrator. Keep desktop and releases separate.

## Behavior and constraints

- Persist one local alignment preference; loading an unknown value falls back to
  Full width. Settings and the existing Tools panel expose the same choice and
  selected state. Reset returns to Full width and preserves models/user data.
- Full width keeps current sizing. A side-aligned column targets 82% of available
  width, bounded to 320–360 dp and never wider than its actual parent. Narrow
  displays use the available full width. These are starting design choices for
  review, not a measured physical comfort claim or an existing layout minimum.
- Keep all toolbar, typing, symbols, editing and terminal controls in the same
  column. Essential controls cannot disappear, clip or overlap. Preserve existing
  independent key height/label sizing, number row, themes and feedback preferences.
- Use explicit physical left/right alignment. Apply parent/system insets and
  bound touch coordinates to actual key rectangles. Cancel holds, repeats,
  rollover and modifier ownership whenever geometry changes; stale controls
  cannot deliver input after a preference or editor/session change.
- No hidden gestures, new permissions, passive collection or copied keyboard code.
  Do not change the voice-panel workflow or advertise tablet/split/floating modes.

## Acceptance and verification

Verify Full/Left/Right placement at narrow and wider widths; all essential keys
remain reachable in normal, number, symbol, terminal, Tools and Edit states.
Check Settings save/reopen and reset, live quick-toggle persistence, unsupported
stored values, large labels and both themes. Reset must preserve model files and
other user data. Add geometry-change regressions for pending touch/hold/repeat
ownership, not only preference serialization tests.

Use the Android tooling tests, JVM tests, `lintDebug` and the named one-hand,
geometry, tuning and rollover instrumentation classes. Inspect actual result
files and render the live IME view in synthetic editors using the existing optional
API 29+ capture harness. Preserve `FLAG_SECURE`, original preferences and IME state.
Record physical-phone and TalkBack/Switch Access trials separately as open gates.

## Non-goals and stop

No arbitrary drag/resize, split/floating keyboard, orientation profiles, new
language/prediction engine, dependency or release publication. Stop editing after
the complete Settings/Tools/layout flow, focused checks, visual review and
independent review pass. Update the mobile roadmap before advancing to the next
capability. The first task is implementation of this bounded layout prototype;
refine measured problems before broadening customization.

## Status

September 12: contract approved for source implementation after the first R2
geometry/feedback slice passed review and its named checks.

Source now implements the local alignment preference, Settings radio controls
and selected Tools choices. Full width is the default and reset value. Width is
resolved during the content's first measurement; applying it only after layout
failed the narrow/wide regression and was replaced. Parent resizes and quick
alignment changes cancel pending touch, rollover, deletion and modifiers.

The source slice passed implementation and independent review. Initial
verification found a first-measure width defect and test synchronization gaps;
these were fixed before the final checks. The unused strip now follows the
keyboard's light/dark surface color. No production screenshot protection changed.

## Final verification — September 12, 2026

Environment: `UtterleafFoundation35`, Android API 35, 1080 × 2400, density 420,
JDK 17. These are local debug/emulator checks, not a signed release or physical
phone/accessibility acceptance.

- `python -m unittest discover -s mobile/android/tools -p 'test_*.py'`: 7 passed.
- `gradlew.bat testDebugUnitTest`: 8 passed, no failures/errors/skips.
- `gradlew.bat lintDebug`: 0 errors, 47 existing warnings.
- `adb -s emulator-5554 shell am instrument -w -r -e class org.utterleaf.voice.TypingRolloverTest,org.utterleaf.voice.KeyboardGesturesTest,org.utterleaf.voice.HeldModifiersTest,org.utterleaf.voice.DeleteRepeaterTest,org.utterleaf.voice.EditorActionsTest,org.utterleaf.voice.TerminalInputTest,org.utterleaf.voice.OneHandLayoutTest,org.utterleaf.voice.KeyboardTuningTest,org.utterleaf.voice.PersistenceTest org.utterleaf.voice.test/androidx.test.runner.AndroidJUnitRunner`:
  49 passed, no failures/errors/skips, 74.103 seconds. This includes Settings
  reopen and Reset Cancel/Reset, unknown-value fallback, preference/model
  preservation, first-measure bounds, withheld rollover cancellation and stopping
  an active held-delete repeat during parent resize.
- After the final surface-color-only change, `gradlew.bat installDebug lintDebug`
  passed, followed by
  `adb -s emulator-5554 shell am instrument -w -r -e class org.utterleaf.voice.KeyboardGeometryTest -e r2Screenshots one-hand-verified org.utterleaf.voice.test/androidx.test.runner.AndroidJUnitRunner`:
  3 passed, no failures/errors/skips, 22.726 seconds. Total named instrumentation
  coverage is 52 tests across these two runs. The color-only change did not alter
  input behavior; geometry and visual checks were repeated for that final source.

The live IME test verifies actual width and physical alignment, every visible
key's column/display bounds, pairwise overlap, both symbol pages, function keys,
Tools and Edit, selected alignment, and quick Full-width persistence/restoration.
The capture harness waits for old IME removal and settled new-field geometry.
Settings dialog checks use platform button IDs and restore automation flags.

Twenty-four keyboard states and one Settings view were rendered from owned live
views, with no display/notification/editor capture or disabled `FLAG_SECURE`.
Settings assertions verify empty practice text, visible alignment controls and
Full selected before rendering. Final local artifacts are in
`artifacts/screenshots/android-one-hand/one-hand-verified/` (about 2.2 MB).
Source, test and one-hand/Settings visual review are complete with no remaining
blocker for this bounded slice. Physical reach/typing comfort, landscape sessions, TalkBack
and Switch Access remain open product gates.
