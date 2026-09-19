# Android keyboard interactions and discovery — completed alpha19

## Goal and area

Fix the alpha18 report: a sustained Backspace hold should repeat, and a later
left swipe should take over to preview deletion from the remaining caret.
Own DeleteRepeater, its TypingPanel binding and focused Android instrumentation.
The requested design review also covers direct Settings from emoji hold, a visible
Tools entry, Settings search/category discovery and the malformed Cut icon.

## Constraints and acceptance

- Stop the repeat timer before beginning selection. Already repeated deletions
  stay committed; reversing/cancelling restores only the new selection's caret.
- Release deletes the confirmed selection once. Rejected selection, vertical
  cancellation, multiple pointers, session changes and detach cannot resume
  repeat or fall back to a tap.
- Ordinary capitalization must not turn Backspace into a single modified delete.
  Preserve explicit Extra keys modifiers, repeat-off/repeat-guard preferences,
  password/raw restrictions, editor confirmation and Unicode navigation.
- Emoji tap opens Emoji; hold opens full Settings. Tools remains reachable by tap
  with Extra keys off. Private draft retains its restricted local Tools.
- Settings search finds control names regardless of current values. Backspace
  controls belong under Holds & gestures; staged Apply/Cancel/reset remain intact.
- No new permissions, text collection, dependencies or desktop work. Defer broad
  Setup restructuring and toolbar rearrangement to a separately verified pass.

## Verification and stop

Reproduce with focused API 35 tests before editing production. Run
BackspaceSelectionTest, DeleteRepeaterTest, HeldModifiersTest, KeyboardTuningTest
and relevant typing/terminal regressions; run Android tooling/JVM/lint/builds.
Canonical CI owns the full emulator run. Review the diff and record exact
candidate/signing evidence before publishing the next signed preview. Stop after
the bounded fix, verified release and accurate roadmap; phone confirmation stays
open until the user retests the reported gesture.

## Evidence so far

Two tests reproduced the alpha18 failures before production edits: late swipe
never began selection, and a hold after punctuation stopped repeating. The fix
passed the original 26-test Backspace/repeat/modifier/tuning bundle. All 17 tooling
and 40 JVM tests pass; lint has 0 errors/56 warnings and release build passes.

The expanded Backspace/terminal run passed the new gesture cases and all 16
terminal tests, but exposed two fixture problems. The new options setup mistakenly
hid Extra keys; it now explicitly enables that control. The raw-editor transition
also needed reliable input readiness: launch waits for an active editor and visible
keyboard and closes the activity on failure. Local animation settings now match
CI (disabled). The final 12-test Backspace class passed with no failures/skips.
No deletion or restricted-field assertion was weakened.

Alpha19 is published. Exact-candidate CI 35462899374 passed 186 tests;
protected signing 35463561268 and independent signed alpha18-to-alpha19
upgrade/reinstall preservation checks passed. See the mobile roadmap for receipts.
Superseded CI 35442827839 was cancelled because its
fixture setup had already been corrected locally.

## September 19 design review

Independent navigation, visual and keyboard-accessibility reviews prioritized
the reported interaction failures plus reachable Tools, control-name search,
correct category placement and contrast. Implementation preserves emoji tap,
tap-only Settings access and private-draft restrictions. Regression coverage
includes stale callbacks, Extra keys off, staged preferences and both themes.

Follow-up work, outside this candidate: simplify Setup/model management with
feedback beside each action; improve toolbar target sizes without overlapping
letter hitboxes; make Tools selected/toggle states clearer; constrain landscape
Settings width; give rejected editor actions specific, text-free feedback.
Physical TalkBack/Switch Access and thumb comfort remain open.

Research anchors: [Android accessibility actions](https://developer.android.com/guide/topics/ui/accessibility/views/principles-views),
[touch targets](https://support.google.com/accessibility/android/answer/7101858?hl=en),
[gesture cancellation](https://developer.android.com/develop/ui/views/touch-and-input/gestures/viewgroup),
and [haptic feedback](https://developer.android.com/develop/ui/views/haptics/haptics-principles).
These inform acceptance; they do not establish physical-phone usability.

Local UI/UX integration: 59 unique focused instrumentation tests pass, including
9 Settings and 7 compact-layer tests; compact-layer tests also pass at 320dp with
large labels and left alignment. All 17 tooling and 40 JVM tests pass; lint has
0 errors/56 warnings; release build passes. Native light/dark, enabled/disabled
and narrow renders were independently reviewed. The initial Tools autosize error
was fixed before final validation; exact-label search coverage was strengthened.
Physical acceptance remains in the active phone plan.
