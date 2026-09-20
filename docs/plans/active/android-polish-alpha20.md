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
- Final portrait API 35 suite: 191/191 passed on the visible emulator after the
  responsive Extra Keys and symbol-density changes.
- True landscape (`ROTATION_90`, 914dp by 411dp) daily contract: 2/2 passed.
- The responsive Extra Keys and symbol-density slice passed the complete live
  landscape geometry run. Portrait keeps the daily toolbar and adds one grouped,
  horizontally scrollable Accessory/F-key row. Landscape reuses the toolbar row
  as the specialist header so the keyboard does not grow; Space, Enter, letters,
  the number row, one-hand alignment and all terminal callbacks remain reachable.
  Ctrl/Alt plus arrow multi-touch remains supported. The additional-symbol page
  now distributes its complete inventory across two readable lower rows.
- Correctly oriented full-, left- and right-aligned normal, symbols,
  more-symbols, accessory and F-key captures were inspected on the visible
  emulator. Emulator evidence is not physical-phone acceptance.

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
- Split layout remains the only confirmed layout feature gap from this review.
  Symbol density and responsive Extra Keys geometry are implemented and covered;
  do not regress by dropping characters or breaking held modifier chords.

## Voice-state indicator slice

The explicit mic action uses a compact, untinted Utterling holding a microphone.
The opened Voice surface uses the repository's official Utterling derivatives for
Listening, Processing, Transcript ready, Editing and Needs attention. Every image
is paired with visible state text; the illustration is supplementary and does not
replace Stop, Insert, Discard, recovery copy, timer or local-processing status.

Acceptance evidence on the visible API 35 emulator:

- Voice workflow controls: 13/13 passed, including the six state labels and OLED
  true-black rendering.
- Compact toolbar mic treatment passed enabled/disabled contrast checks in Light
  and Dark; screenshots confirm branded art remains full-color while other action
  icons retain the normal palette tint.
- The generated `utterling_mic.png` is a transparent, non-destructive derivative
  of the official `utterling_default.png`; the other five states reuse existing
  official repository assets.

## Stop

For Slice 0, stop after the daily action contract, Select semantics, portrait and
landscape geometry, visible-emulator screenshots and focused checks pass. Do not
claim physical-phone usability. Later slices own split layout and any broader
Tools/Edit restructuring.
