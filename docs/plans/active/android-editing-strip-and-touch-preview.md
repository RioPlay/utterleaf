# Android editing strip and touch preview

## Goal

Design a small, accessible quick-action banner for the original Android
keyboard and a local, opt-in typing touch preview. The banner should expose
frequent editing actions without requiring the full Edit panel. The preview
should help a person inspect where their taps land while making no claim to
measure finger identity, typing accuracy or intent.

## Current evidence

- `EditorAction` and `EditorActions` in
  `mobile/android/app/src/main/java/org/utterleaf/voice/EditorActions.kt:3-24`
  already provide editor-owned Select all, Cut, Copy and Paste (along with
  Undo/Redo). They use explicit `InputConnection.performContextMenuAction`;
  there is no clipboard history or automatic fallback. Copy/Cut are refused
  for password variations and `TYPE_NULL` is refused.
- `TypingPanel.editingRows()` in
  `mobile/android/app/src/main/java/org/utterleaf/voice/TypingPanel.kt:589-620`
  currently renders two 48dp action rows: Undo/Redo/Select all, then
  Cut/Copy/Paste when not in the private editor, followed by 48dp cursor and
  navigation rows. The Edit toolbar itself is a 48dp row at
  `TypingPanel.kt:636-650`; `key()` adds small insets while preserving native
  Button accessibility and focus semantics.
- The action panel is already generation-cancelled by `render()` and guarded
  through the current editor callback. Existing tests cover practice and live
  Select all/Copy/Cut/Paste, stale buttons, refusal feedback and geometry.
- The original app has no `Incognito` option in `KeyboardOptions` or
  `TypingPanel`; the only current Incognito implementation is in the separate
  next-keyboard design/candidate. This plan therefore treats Incognito as a
  new explicit local privacy state, not as an existing capability.
- `KeyboardSurface` in
  `mobile/android/app/src/main/java/org/utterleaf/voice/KeyboardSurface.kt:12-183`
  owns ordinary-key bounds, rollover and cursor/selection gestures. Its
  coordinates can support a transient preview overlay, but the current code
  does not retain a touch history or heatmap.

## Area

- `TypingPanel.kt`, `EditorActions.kt`, `KeyboardSurface.kt` and the owning IME
  lifecycle only after this plan is accepted for implementation.
- A focused Android test area for action availability, sensitive fields,
  session/lifecycle clearing, compact geometry, Incognito and preview privacy.
- Settings/Tools strings and the mobile roadmap status entry.

## Proposed interaction

The default Daily toolbar may expose one compact 48dp banner row with native
buttons ordered `Select all`, `Cut`, `Copy`, `Paste`, and `Incognito` where the
available width permits. On narrow layouts it should use the existing aligned
column and a deterministic wrap or horizontal paging decision recorded by the
implementation; it must not shrink labels below accessible names or displace
ordinary letter keys. The full Edit panel remains the complete route for
Undo/Redo, cursor movement and Select mode. Private draft mode continues to
hide host clipboard actions. Password/raw/unknown-sensitive fields must refuse
or disable unsafe actions according to the existing editor contract.

Incognito must be a visible, explicit local preference with a clear On/Off
state and reset semantics. It disables touch-preview collection and any future
learning for the active keyboard session. Sensitive fields may force an
effective Incognito state; the user must see that it is required. A failed
preference write must fail closed for the session and must not claim durable
state.

The touch preview is a separate opt-in diagnostic session, Off by default. It
may render bounded aggregate hit density over the current keyboard geometry,
with a visible `Preview`, `Reset`, and `Stop` control. It must clear on Stop,
field/subtype change, hide/finish/detach, reset and entering Incognito. Do not
persist samples or export them implicitly. Samples contain only bounded local
coordinates/key-region aggregates and timestamps needed for the active
session: no text, key labels, editor/app identity, clipboard, audio or
chronological pointer trail. Exclude password, raw terminal and other
sensitive/unknown fields. The preview describes touch density on this layout;
it cannot infer finger identity, intended key, typing speed, correctness or
comfort.

## Constraints

- Security first: no ambient collection, passive typing telemetry, clipboard
  history, app identity, raw text in diagnostics or network path.
- Native buttons retain spoken labels, focus order, minimum touch targets and
  visible state. All actions remain explicit and session/generation guarded.
- Do not copy code or assets from `mobile/latinime`; do not edit
  `DeviceTest.kt`, `PrivacyCoreTest.kt` or `TypingPanel.kt` during this planning
  pass.
- Keep ordinary typing, terminal literal dispatch, private drafts and secure
  window behavior unchanged. No persistent heatmap is allowed without a later
  reviewed design with explicit inspect/clear controls.

## Acceptance

- Source review identifies one compact banner geometry that remains usable at
  the supported narrow width, large labels, both themes and all alignments.
- Select all, Cut, Copy and Paste invoke the existing editor-owned commands
  exactly once, preserve current refusal behavior and never fall back to text
  or terminal events. Private drafts and sensitive fields have explicit,
  tested availability rules.
- Incognito state is visible, explicit, local, fail-closed on save failure,
  preserved through ordinary reset as specified, and clears/disables preview
  data at every named lifecycle boundary.
- Preview is Off by default; while active it shows bounded aggregate touch
  density only, excludes protected/sensitive fields, exposes Reset and Stop,
  and leaves no samples after Stop, field change, hide, finish, detach, reset
  or Incognito. No raw text, app identity or persistent touch history exists.
- Tests distinguish observed touch locations from any inference about typing
  accuracy or human behavior, and document that emulator evidence is not
  physical-device or accessibility certification.

## Verification

- `python -m unittest discover -s mobile/android/tools -p test_*.py`
- `gradlew testDebugUnitTest lintDebug compileDebugAndroidTestKotlin`
- Focused API 35 instrumentation for action banner geometry and accessibility,
  editor action refusal/session invalidation, Incognito persistence/failure,
  and preview Off/Reset/Stop/sensitive-field/lifecycle clearing.
- Review source and test diffs for absence of clipboard/text/app identity
  capture, and run the existing regression bundle after integration.

## Non-goals

No prediction, swipe learning, adaptive hit-zone application, chronological
heatmap, cloud/export flow, analytics, app classification, or replacement of
the full Edit/Tools panels. Incognito does not claim to control the host app's
own logging or keyboard behavior.

## Stop

Stop after the interaction, privacy boundaries, geometry choice and test
contracts are independently reviewable. Do not implement source, add
permissions, persist touch data or broaden this into the next-keyboard
foundation work without a new scoped plan.
