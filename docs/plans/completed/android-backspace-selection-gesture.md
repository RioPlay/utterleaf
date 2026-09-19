# Android Backspace selection gesture

## Completion - September 18, 2026

Merged through PR #28 (9e389083) and released in alpha15; CI 34742852950 passed 145 instrumentation tests.

The original no-transition-after-hold rule below is superseded by the
[alpha19 follow-up](../active/android-backspace-hold-swipe.md), which stops repeat
before beginning a new selection at the remaining caret.

This bounded increment is closed. The evidence below is historical; earlier
pending/unreleased statements describe that stage, not current work. Physical,
editor and accessibility limits remain open in the [platform roadmap](../../mobile-roadmap.md).

## Goal

Add an optional direct gesture to the original Utterleaf keyboard: drag left
from Backspace to preview a backward text selection, reverse toward the start
to shrink it, and release with a nonempty valid selection to delete it exactly
once. Keep the existing Backspace tap and held-repeat behaviors unchanged.

This is the next original-keyboard interaction increment after the published
alpha14 release. It is not implemented by that release.

## Area

- `mobile/android/app/src/main/java/org/utterleaf/voice/DeleteRepeater.kt` —
  currently owns Backspace tap, hold timing, repeat, release and cancellation.
- `mobile/android/app/src/main/java/org/utterleaf/voice/KeyboardSurface.kt` —
  currently owns multi-pointer routing and the Shift+Space selection chord.
- `mobile/android/app/src/main/java/org/utterleaf/voice/TypingPanel.kt` —
  binds Backspace and routes editor operations through the current panel.
- `mobile/android/app/src/main/java/org/utterleaf/voice/KeyboardIme.kt` and the
  current editor gateway — own the generation-bound `InputConnection`,
  selection updates and host-field restrictions.
- The private-draft editor/panel and focused JVM, direct-panel and actual-IME
  instrumentation tests.

## Implemented behavior

- A Backspace tap deletes once. Holding it past the system long-press timeout
  repeats deletion every 80 ms when held deletion is enabled. Leaving the key,
  multi-touch, cancellation, detach and panel replacement stop the gesture.
- A horizontal Space drag moves the caret. Text selection is a separate
  two-finger chord: hold Shift with one finger, place a second finger on Space,
  then drag that Space finger horizontally. Tapping Shift and later swiping
  Space as a one-finger sequence is not established behavior and must not be
  claimed.
- A leftward Backspace drag in an ordinary editable host field or private draft
  now previews a bounded backward selection. Reversing toward the origin shrinks
  it, and a valid release deletes the confirmed nonempty selection once.
- Password, raw and terminal fields retain tap/hold Backspace but refuse the
  selection gesture. Cancellation, multi-touch, stale sessions and uncertain
  editor results restore or fail closed without deleting.

## Constraints

- Preserve normal Backspace tap and the configured held-repeat behavior. A
  drag that becomes a selection gesture must cancel the repeat timer before
  its first deletion; it must never perform both repeat deletion and selection.
- Keep all pointer state inside the current IME session. Do not record typed
  text, selected text, pointer history or editor contents, and do not use the
  clipboard, network, dictionary or prediction engine.
- Use the editor's native selection movement contract rather than computing
  UTF-16 offsets from collected host text. Do not create a boundary that splits
  a surrogate pair, combining sequence or editor-owned grapheme. If an editor
  cannot confirm safe movement and selection, refuse the gesture without
  deleting.
- Do not expose selected text in a keyboard overlay. The editor's ordinary
  selection highlight is the preview; the keyboard may show only a generic
  gesture-active state.
- The gesture is available for an ordinary editable field with a current,
  confirmed selection session and for a private draft through its local bounded
  editor callback. Password, raw/`TYPE_NULL`, terminal and other restricted
  fields retain tap/hold Backspace but do not start selection preview. A private
  draft gesture never uses the host `InputConnection`.
- No LatinIME/FUTO code, new permission, ambient input collection, persistence,
  haptic requirement or unrequested preference.

## Interaction contract

1. Start with one pointer down inside Backspace and a confirmed collapsed
   caret. Until horizontal motion exceeds system touch slop, the existing
   tap/hold decision remains pending.
2. Horizontal left motion beyond touch slop enters selection mode and cancels
   held-repeat callbacks before any erase. Each
   `maxOf(system touch slop, 16 dp)` step extends the editor's native selection
   backward by one navigation unit. A single event and the whole gesture must
   use explicit caps; start with 64 units per event and 256 total units. If the
   hold timer performs its first repeat deletion before this threshold is
   crossed, repeat mode owns the stream and later movement cannot convert it to
   selection mode.
3. Moving right reverses only the units selected by this gesture. It shrinks
   toward the original caret and never crosses that origin to select forward
   text. Stationary events do nothing.
4. The editor displays the current selection as the preview. Release inside
   the valid horizontal gesture band deletes the confirmed nonempty selection
   exactly once. Release at the origin performs no deletion because the
   gesture already consumed the original tap.
5. Predominantly vertical movement before selection begins, more than 48 dp
   vertical drift, leaving the allowed band, a second pointer, `ACTION_CANCEL`,
   detach, layout rebuild, field/subtype change, IME hide/finish/destroy,
   connection replacement or an unconfirmed selection update cancels. It
   deletes nothing and cannot fall back to a tap or repeat.
6. Cancellation restores the original collapsed caret only when the same
   editor/session still owns the gesture and restoration is confirmed. Stale
   callbacks never restore into or mutate a replacement editor. If restoration
   cannot be confirmed, invalidate the gesture and perform no deletion.
7. A rejected or uncertain final deletion is not retried automatically. Report
   the existing unavailable feedback without issuing an Enter, key-event or
   clipboard fallback.

## Acceptance

- Direct gesture tests distinguish tap, hold-repeat and swipe modes and prove
  only one can own a pointer stream. They cover threshold boundaries, discrete
  leftward units, stationary moves, reversal to zero, the per-event/total caps,
  valid release and every cancellation path above.
- An actual-IME fixture begins from a collapsed selection, previews exact
  backward ranges, then deletes once on release. Named cases cover ASCII,
  supplementary characters, combining marks and a ZWJ emoji sequence without
  malformed UTF-16 or extra surrounding deletion.
- A refused editor operation and an editor/session change after preview retain
  text and cannot mutate the next field. Password/raw/terminal fixtures prove
  the gesture is unavailable while tap/hold deletion keeps its current
  contract.
- Private-draft direct tests prove preview and final deletion stay in the local
  model and never call the host or clipboard.
- Existing `DeleteRepeaterTest`, `KeyboardGesturesTest`, held-modifier,
  Space-cursor and Shift+Space selection tests remain unchanged and pass.

## Verification

- Run the smallest new JVM/direct-panel tests first.
- Build the debug and Android test APKs, then run the focused new actual-IME
  class plus `DeleteRepeaterTest`, `KeyboardGesturesTest` and affected editor
  contract tests on the dedicated API 35 emulator.
- Run canonical Android CI before integration because editor behavior and
  cancellation vary across connections.
- Record emulator evidence as such. Physical-phone touch comfort, TalkBack,
  Switch Access, OEM editor behavior and broad grapheme behavior remain
  separate acceptance gates.

## Non-goals and stop

Do not add swipe typing, prediction, dictionaries, word heuristics, delete
acceleration, a selected-text preview, a new settings surface, or change the
existing Shift+Space chord. Stop when the bounded Backspace gesture has exact
failure semantics, independent review and focused emulator evidence; retain
unsupported-field and physical-device limits.

## Implementation notes — September 13, 2026

The implementation keeps pointer ownership in `DeleteRepeater`: a leftward
move beyond touch slop cancels its pending repeat before an erase, then steps at
`max(touch slop, 16 dp)` with a 64-step event and 256-step gesture cap. Vertical
drift, a second pointer, cancellation, detach and layout/session invalidation
cancel the selection and do not fall back to a tap.

`KeyboardIme` seeds the selection from `EditorInfo` when input starts and then
records only editor-provided offsets from `onUpdateSelection`; it does not read
selected or surrounding host text. A host gesture captures the generation and
`InputConnection`, queues one native Shift+arrow movement at a time, and deletes
by one empty `commitText` only after the editor confirms the latest backward,
nonempty range anchored at the original caret. It clamps at a confirmed beginning
of field and never reverses through the origin into a forward selection. Rejected,
stale or unconfirmed operations restore only within that captured session and
otherwise do nothing. Password, raw and the current terminal-mode setting fail
the gesture gate while their existing Backspace paths remain available.

Private drafts use their bounded model callback and ICU grapheme boundaries;
they never obtain a host connection or clipboard. `BackspaceSelectionTest`
covers direct pointer ownership and limits, host confirmation and stale-session
behavior, private grapheme preview/deletion, generic unavailable feedback,
restricted fields and the live terminal toggle.

Verified on the dedicated API 35 `UtterleafFoundation35` emulator:

- `BackspaceSelectionTest` passed all 10 tests, including direct gesture state,
  actual host-IME preview/deletion, private-draft graphemes, cancellation,
  beginning-of-field overshoot/reversal and restricted-field gates.
- A combined instrumentation run passed all 47 tests across the new class plus
  `DeleteRepeaterTest`, `KeyboardGesturesTest`, `KeyboardEditorContractTest`,
  private editor/panel/IME, held-modifier and letter-layout coverage.
- Android tooling passed 14 Python tests; Gradle passed 31 JVM tests, debug lint
  with zero errors, and debug plus Android-test APK assembly.

Physical-phone touch comfort, TalkBack, Switch Access and broader OEM-editor
coverage remain follow-up acceptance work. Emulator evidence does not establish
those results.
