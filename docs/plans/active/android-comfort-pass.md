# Android daily-keyboard comfort pass

## Goal

Make ordinary Utterleaf typing feel calmer and more comfortable while retaining
the independently implemented interaction model released in alpha21.

## Area

- `mobile/android/app/src/main/java/org/utterleaf/voice/TypingPanel.kt`
- `mobile/android/app/src/main/java/org/utterleaf/voice/Ui.kt`
- focused daily-strip and keyboard-geometry instrumentation tests
- Android roadmap and this plan

## Constraints

- Preserve editor behavior, privacy policy, suggestion computation, gestures,
  key ordering, preference identifiers and specialist Tools behavior.
- Keep the suggestion region fixed at 48 dp and every actionable daily control
  at least 48 dp in both orientations.
- Do not copy FUTO code, assets, layouts, labels, constants or theme values.
  FUTO is a behavioral comfort benchmark only; Utterleaf's implementation and
  visual tokens remain independent.
- Emulator rendering is not evidence of physical-phone comfort.

## Acceptance

- Suggestions read as quiet inline text choices rather than a second set of
  raised keys, while retaining three predictable tap regions.
- An empty suggestion state is visually calm and does not add instructional
  filler or change keyboard geometry.
- Secondary hints remain legible but are subordinate to primary key labels.
- The dynamic action key uses the same rounded-key language as the keyboard;
  the branded dictation control remains visually distinct.
- Pressed, focused, selected and disabled controls retain visible state.
- Portrait, landscape, one-handed, split and sensitive layouts retain their
  existing geometry and behavior contracts.

## Verification

1. `python -m unittest discover -s mobile/android/tools -p test_*.py`
2. `mobile/android/gradlew.bat testDebugUnitTest lintDebug --no-daemon`
3. Focused emulator classes: `DailyToolbarContractTest`,
   `KeyboardSpacingTest`, `KeyboardGeometryTest`, `KeyboardTuningTest`,
   `SuggestionStripTest`, `SensitiveTypingPanelTest`, `OneHandLayoutTest`,
   `SplitKeyboardTest`, `CompactLayerTest` and `KeyboardEditorContractTest`.
4. Render ordinary empty, one-candidate and three-candidate states for visual
   comparison. Record the emulator-only limitation.

## Non-goals

- No new prediction, autocorrection, gesture typing or language behavior.
- No Tools architecture, settings, dictation-state or editor-lifecycle changes.
- No release/version bump in this slice.
- No claim of literal visual parity with another keyboard.

## Stop

Stop when the bounded daily-surface changes and focused checks pass. Move any
interaction or architecture issue discovered during review to the owning plan
instead of expanding this pass.

## Status — September 27, 2026

Implemented on `codex/android-comfort-pass`:

- Added a dedicated flat suggestion role with stateful pressed/focus feedback,
  three stable slots and no empty-state filler.
- Hidden slots now clear candidate text and accessibility descriptions instead
  of retaining stale words in invisible views.
- Centralized the bounded key radii, hint size and bottom-row widths in
  `Ui.KeyboardTokens`; hints use the opaque palette-muted color at 9 sp.
- Mode, comma, Space, period and action now retain at least 48 dp touch width;
  Space absorbs remaining width. The action keeps an explicit accent role and
  uses the standard key radius. Dictation remains the branded pill.
- Added explicit pressed fills without changing gesture routing or animation.
- Added a contrast-safe inset focus/selected outline for primary controls; the
  action remains visually distinct under external-keyboard focus.

Verification:

- Android tooling: **26/26 passed**.
- JVM tests and `lintDebug`: **passed**; lint reported no build-stopping issue.
- Focused emulator bundle: **58/58 passed** across daily toolbar, spacing,
  geometry, tuning, suggestions, sensitive mode, one-hand, split and compact
  layers, plus the real-editor action contract. Earlier runs exposed one newly
  over-strict one-pixel width assertion, test assumptions that did not account
  for split mode's two Space keys, and one default-IME readiness race. Review
  also found that primary focus initially matched the default state. The test
  assumptions were corrected, the readiness case passed on exact rerun, the
  focus outline and rendering assertion were added, and the final combined run
  was clean.
- Final emulator renders for empty, no-match, one- and three-candidate states
  were inspected locally under `.grok/validation/comfort-final-2/`.

This is emulator evidence only. Physical-phone comfort and live assistive-
technology review remain unverified.
