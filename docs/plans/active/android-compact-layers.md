# Compact Android keyboard layers

## Goal

Replace the vertically expanding keyboard controls with a coherent typing surface.
The September 13 alpha14 feedback rejects the fully expanded keyboard, requests a
sliding toolbar/layers and comma long-hold Settings, and asks that the installed
application be named Utterleaf. This is a product layout correction, not simply a
color change or another row of actions.

## Evidence and references

The current `TypingPanel.render` adds five 48dp Tools rows while retaining the
letter keyboard; Terminal adds two more rows, independently of the number row.
The normal dark/light owned-view renders at 360dp and about 412dp also show four
oversized equal toolbar capsules competing with the letters. Screenshot protection
is functioning on the user's phone and must stay enabled.

FUTO's [documented action organization](https://docs.keyboard.futo.tech/actions/assigningactions)
and its official All Actions demonstration were inspected as interaction/visual
references. Favorite actions occupy the top action bar and additional actions
have a separate menu. No FUTO or LatinIME source, assets or product identity is
an implementation input. Utterleaf keeps its original engine and artwork.

## Area and constraints

Own `TypingPanel.kt`, a focused gesture/helper only where needed, relevant native
Android tests, app/IME display-name resources and this plan. Keep package ID,
version/signing identity, stored preference keys, speech runtime and app data
unchanged. No new dependency, permission, clipboard history, typing collection,
network access or screenshot-protection toggle. Preserve every existing guarded
action and useful customization. Native controls keep spoken names, keyboard
focus, visible selected/disabled state and 48dp action targets.

## Interaction

- Everyday typing has one restrained 48dp toolbar. Use small original icons or
  concise labels with clear focus/pressed states; the current four full-width
  filled capsules should no longer dominate the keyboard.
- Tools changes the contents/layer instead of adding rows above the keyboard.
  A horizontal sliding action strip keeps a fixed Back/ABC control reachable.
  Common actions such as Select all/Cut/Copy/Paste remain explicit and available
  without entering a tall control panel. Additional actions stay discoverable.
- Layout and one-hand choices use a bounded secondary layer in the existing key
  area. Its header supplies Back/ABC; changing a choice retains cancellation and
  preference persistence. More controls must never force the host field off-screen.
- Edit, emoji, accent composition and function/navigation views occupy alternate
  layers. Keep one deliberate Terminal modifier row for Ctrl/Alt chords; put
  navigation/function controls in a same-height sliding row or replacement layer
  rather than stacking every terminal control above the letters. A separately
  enabled number row remains intentional and independent.
- Comma tap still types one comma. Holding comma opens a compact settings layer
  or shortcut menu without inserting punctuation; Settings is reachable without
  finger travel after the hold. Expose the corresponding accessibility action.
  Cancellation, slide-off, multitouch, detach and changed sessions must not launch
  stale actions. Private-draft restrictions on leaving or invoking host actions
  remain explicit and enforced.
- Reduce competing hint/letter/utility emphasis with consistent glyph sizing,
  inset hint placement, spacing and restrained theme accents. Preserve key bounds,
  ordinary rollover, held modifiers, long-press hint defaults and editing gestures.
- The installed application and system keyboard chooser display **Utterleaf**.
  Dictation can still be described as Voice input within the appropriate feature.

## Acceptance

1. Opening Tools adds zero rows to the typing surface. All controls can be reached
   by deliberate horizontal scrolling or a named replacement layer at 360dp and
   412dp, both themes, normal/large labels and Full/Left/Right alignment.
2. A fixed Back/ABC exit is always visible; horizontal scrolling cannot type,
   paste or activate an action on release. Rapid layer/session changes invalidate
   stale controls and stop pending gestures/repeat/modifier state.
3. Toolbar and terminal/layer geometry remains bounded; no vertically stacked
   Tools expansion remains. Separate number-row behavior is preserved.
4. Comma tap/hold/accessibility behavior, cancellation and restricted/private
   behavior pass actual native touch and lifecycle checks, not only direct calls.
5. Existing action refusal, raw/password restrictions, private drafts, emoji,
   accent composition, Backspace, Space/Shift+Space, settings persistence/cancel/
   reset and layout behavior remain covered after navigation helpers are updated.
   Do not weaken assertions to accommodate hidden or unreachable controls.
6. Inspect actual app-owned normal, Tools, settings/layout, Edit and Terminal
   renders at the named sizes before calling the design finished. Record total
   height, accessible target bounds and any clipping. Emulator evidence remains
   distinct from user phone comfort and assistive-technology acceptance.
7. Installed launcher/app label and IME chooser name are Utterleaf; application ID
   and existing preference/signing update path remain unchanged.

## Verification

Run `python -m unittest discover -s mobile/android/tools -p test_*.py`, then in
`mobile/android` run `gradlew testDebugUnitTest lintDebug assembleDebug
assembleDebugAndroidTest`. Install both rebuilt APKs on the dedicated API 35
emulator; compare installed/local hashes and run focused geometry, touch, layer,
private/editor/gesture regression tests. Use owned-view renders without host text
or disabling secure-window flags. Canonical Android CI follows independent review.

## Non-goals and stop

Do not add Incognito, touch recording/heatmaps, learning, prediction, arbitrary
theme engines or action reordering in this layout correction. Those retain their
separate roadmap contracts. Do not copy a different keyboard's code to accelerate
the redesign. Stop editing when the complete named layout and interaction gates
pass independent review and documentation matches the implementation; release
only the separately verified snapshot. Physical-phone testing is user-deferred
follow-up, not evidence supplied by an emulator.

## Status

Implementation and independent source/visual review are complete on
`feat/android-compact-layers`, based on the reviewed Backspace/test integration
`d199f2e`. The unreleased keyboard now uses one flat 48dp action strip, fixed
typing exits, horizontally revealed tools, bounded settings/Edit layers and
replacing Terminal Fn/Nav layers. Comma tap inserts once while native hold opens
settings; cancellation, slide-off, multitouch, detach, stale generation,
accessibility and private-draft refusal paths are covered. Ctrl/Alt state clears
when its owning layer or session ends. The launcher and primary IME resolve to
Utterleaf, while the auxiliary voice-only IME resolves to Utterleaf dictation;
the package remains `org.utterleaf.voice`.

Final dedicated-emulator evidence uses `emulator-5554`,
`UtterleafFoundation35`, API 35, qemu. A 56-test touch/gesture/geometry/panel
bundle passes in 97.483 seconds, and a separate 31-test Compose/private-draft/
editor/Backspace/tuning/emoji IME bundle passes in 128.024 seconds. Three focused
live-IME structural checks also pass. The 14 Python tooling tests pass, as do
`testDebugUnitTest`, `lintDebug`, `assembleDebug` and
`assembleDebugAndroidTest`. Both rebuilt APKs were installed; local and installed
SHA-256 match exactly (`926123ba21ecbfac2f337668c26d4e6014d4e9c22059c823a68c1612a5e5968a`
for the app and `c5ed6a6d32430416082b4a4b272417fa04d2bafd3f81317d5c4ac443a66e5b24`
for the test APK).

The final instrumentation counts above were reported from tool console output;
their raw stdout was not retained as a log. Independent review read the final
test diffs and the durable 31-test JVM report and independently verified both
local/installed APK hash pairs. Canonical CI must retain the complete results
for the exact release revision before publication.

Owned-view review covers normal typing, Tools at rest and after a real horizontal
swipe, settings, Edit, and Terminal Fn/Nav at 360dp dark/full and 412dp-equivalent
light/large Left and Right layouts. The final local evidence is under
`.grok/compact-final4-360`, `.grok/c412_large_left` and
`.grok/c412_large_right`; it keeps screenshot protection enabled and contains no
host text. Alpha14 remains published and unchanged. This compact slice is
unreleased, and physical-phone and assistive-technology acceptance remain
user-deferred follow-up.
