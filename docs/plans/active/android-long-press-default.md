# Android long-press hint default

## Goal

Make a letter key's visible secondary hint the initial selection when its secure
alternate strip opens. Releasing without intentional finger travel inserts that
hint exactly once; sliding still selects another displayed alternate.

## Area

- `mobile/android/app/src/main/java/org/utterleaf/voice/KeyboardGestures.kt`
- `mobile/android/app/src/main/java/org/utterleaf/voice/TypingPanel.kt`
- Focused gesture/layout tests under `mobile/android/app/src/androidTest/`
- This plan and `docs/mobile-roadmap.md`

## Constraints

- Preserve the original Utterleaf engine and the reviewed `AlternateCharacters`
  catalog. Do not copy LatinIME, FUTO or another keyboard implementation.
- Keep ordinary taps, configurable hold timing, Shift/Caps, Tools → Accents and
  the period punctuation picker behavior intact.
- The strip remains an in-IME view. Do not add a window, input logging, pointer
  history, clipboard access, persistence or a gesture-only character.
- Existing session, geometry, detach, multi-touch, cancellation and rejected-edit
  guards remain authoritative.

## Acceptance

1. With secondary hints visible, each held letter strip initially selects the
   exact hint derived from that key's current QWERTY/QWERTZ/AZERTY position.
2. Releasing at the original position, including movement within touch slop,
   inserts that hint once. Shift/Caps do not transform digit or symbol hints.
3. Deliberate movement beyond touch slop selects the nearest in-bounds alternate;
   release inserts only the final selected value.
4. Release outside the allowed strip/key band, `ACTION_CANCEL`, another pointer,
   layout/session reset or detach inserts nothing and cannot fall back to the base
   key. A refused editor commit is not retried.
5. Ordinary taps still insert the base key, and the tap-accessible Accents route
   remains available.

## Verification

- Focused JVM catalog/layout tests for the stable hint/choice relationship.
- Compile the focused Android test source and run `KeyboardGesturesTest` plus
  `LetterLayoutTest` in the next coordinated API 35 emulator integration pass.
- Request independent source/test review; emulator evidence is not physical-phone,
  TalkBack, Switch Access or comfort proof.

## Non-goals and stop

No new alternate catalog, language model, prediction, swipe, preference or popup
redesign. Stop when the hint-default relationship, deliberate slide and all named
cancellation paths have focused regressions and independent review.

## Progress

The implementation now passes the positional hint explicitly to the hold strip.
It preserves that initial selection through release jitter within system touch
slop and switches to coordinate selection only after deliberate movement. Existing
outside, cancel, multi-touch, reset and detach paths remain fail closed. Focused
JVM catalog/layout checks pass 8 tests with no failures, and the debug plus Android
test Kotlin sources compile. Independent source/test review found no blocking
issue. Touch slop currently follows the existing axis-based gesture convention;
diagonal movement is not a separate Euclidean threshold. The focused API 35
gesture/layout run, physical touch comfort and assistive-technology checks remain
pending.
