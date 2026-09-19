# Daily keyboard redesign to the approved mockups

## Completion - September 18, 2026

Merged through PR #44 (a3c8138), with restart-race follow-ups; published in alpha17. Canonical CI 35030029554 passed 157 instrumentation tests.

This bounded increment is closed. The evidence below is historical; earlier
pending/unreleased statements describe that stage, not current work. Physical,
editor and accessibility limits remain open in the [platform roadmap](../../mobile-roadmap.md).

## Goal

The approved design mockups (September 15, 2026) define a compact Utterleaf
keyboard: an icon toolbar with an expand chevron, a fold-out Extra keys panel
with an F-keys sub-panel, a hinted number row, symbol letter hints, a bottom row
of `?123 · emoji/settings · labeled space · period · Enter`, and a redesigned
Settings screen (search, categories, Cancel/Apply, practice message with live
preview). The app must match these mockups while keeping every existing
capability reachable through tap controls.

## Area

`mobile/android/app/src/main/java/org/utterleaf/voice/` (TypingPanel,
KeyboardOptions, LetterLayouts, new vector drawables, KeyboardSettingsActivity),
Android tests under `src/androidTest`, `src/test`, and tooling under
`mobile/android/tools`.

## Constraints

- No placeholder suggestions: the mockup's suggestion strip is omitted until the
  planned R4 dictionary/prediction slice provides a real local engine. No fake
  words, no reserved strip.
- Security/privacy posture unchanged: no new permissions, no input retention,
  FLAG_SECURE stays, reset keeps models and microphone permission.
- Accessibility: every removed text button keeps a tap-equivalent control;
  content descriptions stay stable wherever a control survives; announced
  routes for long-press alternatives.
- Independent implementation; no third-party icon or layout asset imports.
  New vector icons are original simple geometry drawn in this repo.
- Emulator/JVM evidence only; physical-phone, TalkBack and release claims stay
  open and are not asserted by this plan.

## Decisions (agreed with the product owner)

1. **Suggestions omitted.** The strip returns with real bounded prediction.
2. **Comma key removed** per mockup. Comma remains available from the period
   key's slide menu (first entry), the punctuation panel, and the symbols page.
   The emoji key (long-press = keyboard settings) takes its bottom-row slot.
3. **Terminal preference is superseded by the Extra keys panel.** `terminal`
   migrates to `extraKeys = true` (the panel provides Esc/Tab/Ctrl/Alt/nav/F1–F12
   on demand). The old permanent-row mode is not preserved.
4. **Settings apply explicitly.** Edits stage locally; Apply saves, Cancel
   discards, matching the mockup header. The practice preview reflects staged
   options.
5. **Mockup defaults become product defaults:** number row on, extra keys on,
   appearance System, auto-capitalization on, arrow repeat on, key borders on,
   320 ms hold. Existing users keep their stored choices via migration.
6. **"Simulated recognition" is not real here:** the Voice input summary
   describes the actual local model state instead.

## Keyboard structure (mockup-faithful)

- Toolbar: undo, redo, copy, cut, paste, private draft, dictate, expand chevron.
  Undo/redo/copy/cut/paste perform editor actions directly when the editor
  supports them; unavailable actions report failure without layout change.
- Expand toggles the Extra keys panel above the toolbar:
  `[Fn Esc Tab Ctrl Alt Shift] [Home End Ins Del PgUp PgDn] [← ↓ ↑ →]`.
  Fn swaps the first row to `[Hide F keys Esc Tab Ctrl Alt Shift]` and adds
  F1–F6/F7–F12 rows, exactly as the mockup's "Function keys open" state.
- Ctrl/Alt arm sticky modifiers (existing chords), Shift arms shift/caps
  (long-press Shift = caps lock), all with spoken state.
- Number row: on by default, digit hints `! @ # $ % ^ & * ( )`.
- Letter hints: with the number row shown they are the mockup's symbol set
  (`~ \ | = [ ] < > { }` positionally on the top row; `@#$%&-+()/` and
  `*"':;!?` rows unchanged). With the number row hidden, digit hints return so
  every hinted value stays reachable. Hold still preselects the displayed hint.
- Bottom row: `?123`, emoji key (tap = emoji, long-press = keyboard settings,
  gear glyph beneath), space labeled with the active subtype locale
  (`English (US)`), period, Enter pill (action label or `↵`).
- Shape language: ~8 dp key radius, pill shapes for dictate and Enter, key
  borders per preference, mockup dark palette (existing colors already match).

## Settings structure (mockup-faithful)

Header `Cancel · Settings · Apply`; search filters categories; categories
Layout & size, Navigation & terminal, Typing assistance, Holds & gestures,
Appearance, Voice input, Privacy & data; Reset preferences row. Each category
opens bounded controls with honest summaries. Practice message prefilled
(`Let's meet tomorrow at six. Bring the notes.`) with the live keyboard
preview; practice input stays local, is cleared on close and never saved.

## Acceptance

- The four mockup states render from the real attached keyboard view: normal,
  Extra keys open, Function keys open, Settings categories.
- Every removed entry point (Tools layer, terminal mode, comma key) has a
  documented tap alternative; reset restores new defaults without deleting
  models; Cancel discards staged settings.
- Named checks pass: tools pytest, JVM tests, focused instrumentation,
  `lintDebug`.

## Verification

- `python -m unittest discover -s mobile/android/tools -p test_*.py`
- In `mobile/android`: `gradlew.bat testDebugUnitTest lintDebug --no-daemon`
- Focused instrumentation on the API 35 emulator, XML inspected separately;
  owned-state view captures to `artifacts/screenshots/android-daily-redesign/`.

## Non-goals

Suggestions/prediction, swipe, new languages, release publication, physical or
assistive-technology acceptance, desktop code.

## Stop

Stop when the named checks pass, docs match, and the mockup states are
captured. Remaining gaps (physical trials, suggestions, release) stay recorded
in the mobile roadmap.

## Progress

- September 15, 2026: contract written; implementation started on
  `feat/android-action-organization` in the Android worktree.
- Same day: keyboard surface and Settings redesign implemented. Icon toolbar
  (undo/redo/copy/cut/paste + draft/dictate/expand), fold-out Extra keys panel
  with F1–F12 sub-panel, hinted number row, symbol letter hints while the number
  row shows, mockup bottom row (`?123 · emoji/hold-for-tools · labeled space ·
  period · Enter pill`), private-draft Tools entry, raw-field compose guard,
  auto-capitalization, arrow repeat, key borders, System/Light/Dark theme,
  Settings with search, staged Apply/Cancel, practice message + live preview,
  and one-time defaults migration (`optionsVersion`).
- Verification on UtterleafFoundation35 (API 35, 1080 × 2400 @ 420dpi):
  157 instrumented tests with zero errors and one intermittent timing failure
  (`BackspaceSelectionTest.hostImeBackspaceDragPreviewsUnicodeAndDeletesOnceOnRelease`
  under full-suite load on software rendering; passes standalone 10/10 —
  investigation open), 8 JVM tests, 14 tooling tests, `lintDebug` 0 errors.
  41 owned-view captures in `artifacts/screenshots/android-daily-redesign/`
  include the normal, Extra-keys-open, Function-keys-open and Settings states
  matching the mockups. Space label renders "English (United States)" pending a
  rebuild with the compacted "English (US)" form.
- Open gaps: physical-phone/TalkBack/Switch Access acceptance, the suggestion
  strip (waits for R4 prediction), release publication, and the BackspaceSelection
  timing investigation.
