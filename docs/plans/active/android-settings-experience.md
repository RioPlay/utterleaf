# Android settings experience before alpha18

## Goal and area

Make customization predictable and easy to use before the signed alpha18
candidate. Own `KeyboardSettingsActivity.kt`, the optional preview preference
callback in `TypingPanel.kt`, focused settings instrumentation and Android docs.
The September 18 user instruction prioritizes Android usability improvements;
this bounded pass precedes the existing snapshot contract.

## Constraints

Every settings change, including voice, Reset and preview quick controls, stays
staged until Apply. Cancel must leave persisted preferences untouched. Reset must
keep models and other user data. No typing persistence, ambient recording, new
permissions/dependencies, desktop work or new prediction engine. Dispose replaced
preview panels and invalidate stale input callbacks. Real keyboard quick controls
retain their immediate-save behavior.

## Acceptance

- Apply stays reachable while scrolling; category controls precede the practice
  preview. System Back returns from a category before leaving Settings.
- Theme/alignment/layout choices can be changed and changed back; each updates
  the preview immediately. Search text and filtered results agree after return.
- Voice, reset and preview controls obey Apply/Cancel. Confirmed reset remains
  cancellable until Apply, retains models and restores documented defaults.
- Preview input stays transient. Old panels cannot change preferences or input
  after replacement/close. No-op previews must not silently discard staged edits.
- Named instrumentation, tooling/JVM/lint/build checks and owned-view visual
  review pass. Physical phone and assistive acceptance stay explicitly open.

## Verification

`python -m unittest discover -s mobile/android/tools -p 'test_*.py'`

From `mobile/android`: `gradlew.bat testDebugUnitTest lintDebug assembleDebug
assembleDebugAndroidTest --no-daemon --console=plain`.

Run `KeyboardTuningTest`, new settings experience tests, `PersistenceTest`,
`PrivateTypingPanelTest`, `OneHandLayoutTest` and `LetterLayoutTest` on API 35.
Capture app-owned Settings views with synthetic practice text and inspect default,
scrolled, large-text and narrow/landscape states. Canonical CI owns the full suite.

## Stop and non-goals

Stop when the bounded contracts pass and the final diff is reviewed; integrate
the Android change and continue the signed alpha18 plan. No broad redesign,
keyboard-engine replacement or claim that emulator success proves phone comfort.

## Evidence

- Implemented staged voice/reset/preview controls, reversible radio choices,
  persistent Apply, controls before practice, consistent Back/search, in-memory
  rotation retention and disposal of replaced previews. No practice text is retained.
- Initial checks: 14 tooling and 40 JVM tests passed; lint/debug/test APK builds
  passed. The first focused API 35 run passed 17 settings/persistence tests;
  the related private-panel/one-hand/layout bundle passed 10 tests.
- Owned-view captures at 1080x2400, 840x1800 with font scale 1.3, and 2400x1080
  are retained under `artifacts/screenshots/android-settings-alpha18/`. The two
  narrow/landscape capture checks passed. Visual review shortened the preview's
  country label to avoid truncating "United States".
- The added system Back test initially nested a UI-thread helper inside a
  UI-thread predicate. Corrected the fixture; final candidate verification and
  canonical CI remain required. No production test failure was hidden or waived.
- Version metadata is now 18 / `0.1.0-alpha18`; signing and publication remain pending.
