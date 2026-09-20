# Android polish and alpha20 release

## Goal

Ship a calmer, faster Utterleaf Android preview while preserving the source-derived
daily productivity contract. The default keyboard keeps editor actions and core
destinations directly reachable, adds complete System/Light/Dark/OLED appearance
choices, clarifies voice review versus direct insert, and shortens routine CI.

## Area

- `mobile/android/app/src/main/java/org/utterleaf/voice/`
- focused Android JVM and instrumentation tests
- `.github/workflows/android.yml`
- Android release metadata and release notes

## Constraints

- Recording remains explicit and local. No ambient capture, partial transcript
  insertion, clipboard history, or automatic clipboard reads.
- Review is the ordinary dictation path. Direct insertion remains an explicit
  hold gesture and must not retry after an uncertain host result.
- Settings remain staged behind Apply/Cancel; Reset preserves models and user data.
- A fast PR path may skip the emulator, but a release tag must still identify an
  exact successful `main`/manual run with the full emulator privacy suite.
- OLED means true-black primary surfaces with readable controls; it is not a
  battery-life claim.

## Source-derived capability inventory

| Capability | Current owner | Slice 0 destination |
| --- | --- | --- |
| Undo / Redo | `EditorActions` through `KeyboardIme` or private editor | Anchored action row |
| Cut / Copy / Paste | Explicit context-menu actions; no passive clipboard read | Anchored action row outside Private Draft |
| Select | Native word-selection chord and explicit Select all action | Tap Select for neighboring word; hold for Select all |
| Tools / Edit / Emoji | Existing `TypingPanel` surfaces | Anchored destination row |
| Private Draft | Safe-field callback owned by `KeyboardIme` | Stable destination slot; absent in restricted/private fields |
| Voice | Explicit `showVoice` callback | Stable mic slot; visibly disabled in restricted fields |
| Password manager | Password-field-only callback | Reuses the Draft slot only in password fields |
| Extra keys | Existing preference and terminal callbacks | Stable specialist slot when enabled |

There is no separate clipboard-history or clipboard-browser callback in the shipping
source. Paste is the only explicit clipboard command. Slice 0 does not invent a
clipboard reader or passive history surface.

## Approved Slice 0 layout

Daily uses two fixed rows of six equal positions. The first row anchors Undo, Redo,
Cut, Copy, Paste and Select. The second anchors Tools, Edit, Emoji, Draft/password
manager, Voice and Extra keys. Restricted actions stay in position and visibly
disable where safe; private editing omits host and clipboard capabilities. Tools,
Edit and Extra Keys keep their existing secondary rendering for this slice.

## Acceptance

- Daily exposes every existing productivity callback without scrolling; six
  stable positions per row remain at least 48dp at 320, 360 and 411dp portrait
  widths and 600 and 800dp landscape widths.
- Tap Select selects the neighboring word. Long-press Select invokes Select all,
  with an explicitly named accessibility action.
- Ordinary, password, raw and private profiles have an enumerated parity test.
  Restricted actions are absent or visibly disabled rather than silently active.
- Theme choice includes System, Light, Dark and OLED, persists across restart,
  previews before Apply, and Reset returns to System without deleting models.
- Mic tap always records for review; the optional hold gesture is clearly named
  as direct insertion after recognition. Failed/uncertain insertions stay
  recoverable and are never blindly repeated.
- Pull requests run tooling, JVM, lint and build checks without provisioning an
  emulator. Pushes to `main` and manual runs retain the full emulator/privacy
  suite and unsigned release input.

## Verification

1. `python -m unittest discover -s mobile/android/tools -p test_*.py`
2. `mobile/android/gradlew testDebugUnitTest lintDebug compileDebugAndroidTestKotlin assembleDebug assembleRelease`
3. Focused API 35 instrumentation for settings, compact layers, voice review,
   private draft and persistence, then the full connected suite for the candidate.
4. Successful exact-revision Android CI on `main`, followed by protected signing,
   signer/package/version/alignment and signed upgrade/reinstall checks.

Local candidate evidence on 2026-09-19:

- Android release tooling: 17/17 passed.
- JVM tests, lint, instrumentation compilation, debug APK and unsigned release
  APK: passed in one Gradle invocation.
- API 35 emulator suite: 187/187 passed after the final timing-hardening change.
- Generated live-keyboard, Settings-preview and editor-action screenshots were
  inspected; emulator visuals are not physical-device acceptance.
- Slice 0 portrait API 35 suite: 189/189 passed on the visible emulator.
- True landscape (`ROTATION_90`, 914dp by 411dp) daily contract: 2/2 passed.
  The live geometry run intentionally remains red because Extra Keys clips Space
  and Done in landscape. Correctly oriented normal, symbols, more-symbols and
  failing Extra Keys captures were inspected and saved locally; the second
  symbol page visibly compresses twenty characters into its final row.

## Non-goals

- Streaming or partial speech recognition, live host-field rewriting, prediction,
  clipboard history, new language models, or a stable-channel release.
- Restructuring Tools, the spatial Edit pad, the Extra Keys flyout, Voice, Emoji,
  Private Draft chrome, Setup or Settings information architecture in Slice 0.
- Claims about physical-phone comfort or assistive-technology behavior that were
  not directly observed.

## Layout follow-ups found during visible-emulator review

- The shipping source has Full, Left hand and Right hand alignment only. It has
  no split-keyboard preference or split renderer. A real split layout needs a
  separately bounded landscape slice with preference persistence, Settings and
  practice-preview parity, safe center-gap touch routing, rotation/resize
  behavior and portrait fallback; one-handed alignment is not a substitute.
- The symbols page, especially the additional-symbol row, places too many keys
  on one line at phone widths. Preserve complete punctuation coverage, but
  redesign its grouping and pagination after capturing portrait and landscape
  evidence; do not silently remove characters to make the page look cleaner.

## Stop

For Slice 0, stop after the daily action contract, Select semantics, portrait and
landscape geometry, visible-emulator screenshots and focused checks pass. Do not
claim physical-phone usability. Later slices own split layout, symbol density,
Tools/Edit structure and the flyout.
