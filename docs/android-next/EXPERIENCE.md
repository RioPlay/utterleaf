# Android next keyboard experience

Status: UX specification for the next Utterleaf keyboard. This document is an
interaction contract, not a claim that the isolated LatinIME experiment or any
physical device already satisfies it. It is intentionally independent of FUTO
and Hacker's Keyboard source, assets, names, and implementation details. Those
products inform the desired outcomes; Utterleaf keeps its own visual language,
offline boundary, and editor/session contracts.

The target is a light, fast keyboard that makes ordinary typing the default and
power input deliberate. A person can type, repair, dictate, review, and return
to typing without changing IMEs. Every asynchronous result is bound to the
current editor session. Field changes and dismissal invalidate work; a panel
change that is part of the same voice review/edit flow preserves that take.

## The stable shell

The keyboard has one stable shell in portrait and landscape. System insets are
included in the shell calculation. The shell contains, from top to bottom:

| Location | Default control or content | Rule |
| --- | --- | --- |
| 48dp context bar, left | `Edit` and `Tools` | Always visible in Daily and Symbols. They replace the key deck while the bar stays 48dp high. |
| 48dp context bar, center | Up to three candidates, or `No suggestions` | The center is flexible: show one or two candidates on narrow screens. Do not allocate a fixed percentage or show a decorative empty strip. |
| 48dp context bar, right | `Dictate` | Enabled only for a safe field and ready local speech resource. Language is reached through `Tools` → `Language`, never squeezed into this bar. |
| Optional number row | `1 2 3 4 5 6 7 8 9 0` | Off by default. When on, it is a row above letters and does not change utility-key positions. It is independent of Terminal mode. |
| Letter area | Familiar staggered QWERTY by default | Three letter rows remain the largest surface. Primary character taps are never replaced by a utility menu. |
| Bottom row, left | `?123` or `ABC` | One tap switches letter/symbol pages; the same position is used on every page. |
| Bottom row, middle left | `,` | Direct punctuation; alternate choices have a visible picker and a tap-accessible Tools path. |
| Bottom row, center | Wide `Space` | Tap inserts a space. A configured space gesture may move the cursor, but `Edit` exposes the same operation by tap. Shift+Space selection is an optional shortcut, never the only selection path. |
| Bottom row, middle right | `.` | Direct period. Long press/slide punctuation is optional and cancellable; it never removes normal period tap. |
| Bottom row, right | `Enter` or host editor action | Green/state treatment may distinguish the host action, but the label remains readable. It is the only host action location. In a raw terminal, explicit `Enter` may execute a shell command; no voice/correction path may do so implicitly. |
| Letter row ends | `Shift` at left and `Backspace` at right | Their locations remain stable across letter and symbol pages. Backspace repeat and drag deletion are separately configurable. |

Default geometry is a 52–60dp letter-row target selected for the available
width, 8dp row gap, 8dp bottom spacing, and a 48dp context bar; the
implementation may clamp to the safe available height. Utility targets are at
least 48dp. Ten columns on a phone may therefore use narrower letter keys than
the utility target, with no overlap; an expanded accessibility profile and tap
alternatives provide larger targets where space permits. Physical comfort and
non-overlap remain validation gates.
The user can change key height (48–80dp), bottom spacing (0–80dp), label size,
feedback, and one-handed alignment in settings. These changes reflow the rows
but do not move the context-bar controls or change which mode is active. A
compact-width layout must retain `Edit`, `Tools`, `Dictate`, `Space`, and the
editor action as named controls; it may reduce gaps before shrinking targets.

`Dictate`, `Edit`, `Tools`, and editor action are real controls with
content descriptions, not icon-only affordances. Every gesture has a visible
tap alternative. A focused screen reader user can complete type → correct →
dictate → review → insert → return without a long press, swipe, or multi-touch.

## Daily mode

Daily is the default mode for ordinary text, URLs, email, numbers, messages, and
multiline fields. It uses text/composition APIs for Unicode and reserves key
events for explicitly defined special keys. Auto-capitalization, punctuation
spacing, double-space period, secondary hints, repeat filtering, sound, haptics,
previews, and correction are independent preferences. Their default behavior is
conservative: auto-capitalization on where the editor permits it, spacing and
double-space period off in literal-looking fields, feedback using the system
default, and learning off.

The context strip has three states:

* `No suggestions` when suggestions are disabled or no reviewed resource is
  ready. This is a truthful empty state, not a fake prediction row.
* A maximum of three locally generated candidates when prediction is enabled;
  one or two are shown on narrow screens.
  A candidate tap replaces only the current valid composing range and offers
  immediate Undo. It never rewrites committed text or text in a password,
  terminal, or no-personalized-learning field.
* `English · layout ready · speech ready` (or the equivalent declared status)
  when the user opens the language/resource chooser. Layout, dictionary,
  composition, prediction, and speech readiness are separate badges.

`Tools` replaces the key deck with a compact, accessible action deck. It does
not add a row below the bar or horizontally scroll nine tiny actions. Its first
grid contains `Caps`, `←`, `→`, `Accents`, `Emoji`, `Language`, `Terminal`,
`Settings`, `Switch keyboard`, and `ABC`; `ABC` returns to letters in one tap.
`Language` opens the layout/resource chooser. `Accents` opens a visible
character picker for the focused letter or period; long press and slide remain
optional shortcuts. `Emoji` opens local search and categories, supports complete
Unicode sequences including skin tones and ZWJ, and has `ABC` in the same
deck.

## Edit mode

`Edit` replaces only the letter area. The context bar remains 48dp high, with
`Back to letters` in the leftmost position and `Dictate` in its normal right
position; the host field action remains only at bottom-right. The edit surface
is a 4×4 tap-first command grid:

| Grid | Controls | Behavior |
| --- | --- | --- |
| 4×4 | `←`, `→`, `↑`, `↓`; `Word ←`, `Word →`, `Home`, `End`; `Select`, `Select all`, `Undo`, `Redo`; `Cut`, `Copy`, `Paste`, `Del →` | Uses the host editor contract. Each utility target is at least 48dp. Clipboard is read only on explicit `Paste`; there is no history or monitoring. Unsupported actions announce `Unavailable` and do not retry blindly. |

The active selection is visible through the host editor. `Select` is a toggle
with label `Select on`/`Select off`; it is the tap alternative to Shift+arrow.
Copy and Cut are guarded in password fields according to the editor contract.
Raw terminal fields do not receive this clipboard row: `Copy` cannot be
mistaken for Ctrl+C. They retain Terminal controls instead.

`Back to letters` is a single tap and clears temporary selection mode only after
the transition has been accepted. Leaving the field, dismissing the keyboard,
or changing language invalidates all pending Edit actions. Undo/Redo belongs to
the receiving editor's history; the keyboard does not maintain a shadow text
document.

## Terminal mode

Terminal is explicit, off by default, and entered by tapping `Terminal` in
Tools. Entry shows a one-time confirmation when first
enabled: `Terminal sends literal keys; speech, suggestions, learning, and
surrounding-text reads are off.` The mode chip reads `Terminal on`; tapping it
again returns to Daily. `Back to letters` is always visible in the bottom-left
row.

The default Terminal shell height stays stable. Its compact utility row is:
`Esc`, `Tab`, `Ctrl`, `Alt`, `Fn`, then the printable letter area. Arrows and
remaining navigation are on the `Fn` deck and in Edit. An optional `Navigation
row` preference explicitly increases height; it is not claimed to fit the
fixed-height default. `Fn` replaces the letter deck with `F1`–`F12`, arrows,
`Home`, `End`, `PgUp`, `PgDn`, `Insert`, and `Del →`, plus `ABC`.

* Main area: the same staggered printable letters, with no correction,
  automatic spacing, learning, or smart capitalization.

`Ctrl`, `Alt`, and `Shift` are visibly `off`, `armed`, or `locked`. A tap arms
one chord, sends a complete down/up transaction with the next key, and clears
the state. A separate `Release modifiers` control appears whenever a modifier
is held or locked. Mode change, field change, language change, cancellation,
and dismissal clear every local modifier before any new editor is bound.
Meta and numpad are later additions behind their own compatibility evidence.

Terminal text remains literal until an explicit key is pressed. Explicit
`Enter` sends the host's newline/execute key event and may execute a shell
command; voice insertion, correction, and model output never press Enter or
submit implicitly. `Ctrl+C` is a terminal interrupt, distinct from Edit `Copy`.
Printable non-ASCII input in
raw fields is refused with `Unsupported in terminal` rather than silently
committed as text. Unknown or invalid connections fail closed.

## Voice: one continuous, reviewable path

Voice is always explicit. A tap on `Dictate` opens Voice in place and starts a
reviewable take; IME creation, field focus, or keyboard reopening never starts
the microphone. Voice is unavailable in password, raw `TYPE_NULL`, and
unknown-sensitive fields. An explicit Terminal choice in a text-aware editor
may expose Voice only for review followed by explicit safe literal insertion;
it never reads surrounding text or executes a command. The keyboard stays
usable when no model or microphone permission is available. The conservative
profile suppresses voice and context features for
`IME_FLAG_NO_PERSONALIZED_LEARNING`; that is product policy, not an Android
guarantee that the flag identifies every sensitive field.

The Voice surface keeps a fixed 48dp top bar and a fixed primary action above
the bottom return actions. The transcript editor is local, non-autofill, bounded,
and never shares its connection with the host field.

| State | Visible content and labels | Allowed transitions |
| --- | --- | --- |
| Idle | `Voice`, `Microphone off · <language> · local processing`; `Speech model`; `Speak`; `Back to keyboard` | `Speak` starts capture. `Speech model` opens readiness/selection. |
| Capture | `Listening · <elapsed>`; primary becomes `Stop`; secondary `Cancel` | `Stop` ends audio and enters processing. `Cancel` releases capture, clears audio, and returns Idle. No text is inserted. |
| Processing | `Processing locally…`; disabled primary; `Cancel` | Completion enters Review. Cancel invalidates the take and returns Idle. |
| Review | Transcript preview, `Expand transcript`, `Edit transcript`, `Insert`, `Discard`, `Keep reviewing`, `Back to keyboard` | `Insert` commits once to the bound current field. `Edit transcript` enters local Edit and preserves this take. `Discard` clears it. Preview expiry says `Preview expired · microphone off`. |
| Edit | Local transcript with the same Edit command surface, `Done editing`, `Insert`, `Discard` | `Done editing` returns Review. Edits never affect the host until explicit Insert. |
| Error | Plain cause, such as `Microphone permission denied`, `Model unavailable`, or `No usable transcript`; `Try again`, `Speech model`, `Back to keyboard` | Retry is explicit and uses a fresh session token. Previous audio/result is cleared. |

The default is manual Stop and explicit Insert. Hold-to-speak is an optional
setting and a deliberate gesture: after the configured hold it captures, release
stops and inserts only if the result and editor session are valid. Slide-away or
multi-touch cancels. Silence stopping, if later enabled, ends capture only; it
does not insert or send. Feedback sounds can be disabled. Wired/Bluetooth route
and focus behavior are separate settings with visible failure recovery.

The model chooser lists each reviewed installed resource with language, size,
and status (`Ready`, `Not installed`, `Importing`, `Failed verification`). Import
is local, bounded, hash checked, atomic, and cancellable. A failed replacement
leaves the prior active model available. Choosing a model never deletes a model
or dictionary. The current alpha13 catalog is the source of truth for available
speech resources; the UX queries and displays that catalog rather than claiming
a fixed foundation list. Broader speech languages are unavailable until
separately reviewed. A layout may be ready while its dictionary or speech
resource is not.

## Settings and persistence

Settings open as a normal app screen and are grouped into five sections:

1. `Typing & correction`: suggestions, correction strength, auto-capitalization,
   punctuation spacing, double-space period, local vocabulary, blocked words,
   offensive-word policy, and snippets.
2. `Layout & touch`: key height, bottom spacing, label size, number row, hints,
   alternate-character ordering, repeat/dwell, one-handed left/right alignment,
   split/floating profiles, gesture ownership, and `Touch calibration`.
3. `Feedback & appearance`: sound, haptics, previews, contrast theme, borders,
   and optional read-back.
4. `Languages & voice`: installed layouts, dictionaries, composition resources,
   speech models, language switching, audio route, silence stop, and hold mode.
5. `Power & privacy`: Terminal controls, modifier behavior, inline autofill
   interoperability, the fixed `Word learning unavailable` status, `Practice`,
   `Incognito`, `Reset preferences`, and explicit `Delete models`/`Clear
   personal dictionary` actions.

Changes are draft values until `Apply`. `Discard changes` restores the last
saved values; leaving the screen prompts only when the draft differs. `Reset
preferences` restores reviewed defaults and never deletes models, dictionaries,
snippets, or explicitly added vocabulary. Data deletion has its own confirmation
and names the exact resource. The reset operation is versioned so new defaults
do not silently rewrite data. Preferences are local and explicit; no typed text,
clipboard history, contacts, credentials, raw audio, or transcripts enter
preferences, logs, diagnostics, or telemetry.

`Practice` uses a secure ephemeral field capped at 256 Unicode code points. It
clears on Stop, leaving the screen, and process loss. It demonstrates the active
layout, correction, gestures, feedback, and Terminal labels without sending
practice text to a host app.

## Touch calibration and Incognito

Visible keycaps and labels remain stable. Optional touch calibration changes only
the hidden hit geometry around those keycaps, using small bounded expansions or
contractions based on correction outcomes. It never changes the layout, key
labels, word order or linguistic prediction rules; it can change which nearby
letter a touch resolves to. Calibration is `Off` by
default and has exactly three settings states:

| Setting | Behavior | Data controls |
| --- | --- | --- |
| `Off` | Use reviewed static hit geometry. Do not acquire or apply calibration data. | Existing profile remains stored but inactive. |
| `Learn` | Acquire bounded touch outcomes for the current profile and update hidden hit zones only after validated, delayed training. | `Inspect calibration` shows aggregate counts, profile and geometry summary without text/audio or timestamps; `Clear calibration` deletes the profile. |
| `Frozen` | Apply the retained profile without acquiring or training new outcomes. | Inspect and clear remain available; changing to `Off` stops use but preserves the profile. |

Calibration stores no typed words, corrections as lexical content, swipe paths,
clipboard values, audio, app text, or history. A correction outcome is reduced
to touch/key geometry metadata before persistence. It is bound to the local
layout/profile, private to the keyboard rather than exposed to other apps, and has no diagnostic export
by default. The existing calibration profile is separate from preferences and
from the personal dictionary.

`Tools` contains a reachable `Incognito` quick toggle. When manually enabled,
the flexible center of the 48dp context bar is replaced by a high-contrast
`Incognito` marker in every keyboard mode once persistence is acknowledged,
the toggle remains sticky across fields and restarts until the user turns it
off explicitly through `Exit Incognito` in Tools. Resetting preferences never
silently exits manual Incognito. Manual Incognito uses neutral static hit
geometry for simple, consistent behavior, even if `Touch calibration` is set to
`Learn` or `Frozen`. It suppresses personalized context, correction learning,
and all calibration acquisition, training, application, and new profile updates.
A safe ordinary field may still use a reviewed nonpersonal
dictionary with purpose-bounded transient context and explicit local voice.
Sensitive fields prohibit those context reads. Any queued calibration result is cancelled
or discarded before it can be applied; queued results from before the toggle
are not resumed later.

Incognito persistence is acknowledged, fail-closed, and visible. Keep the
session protected while the preference write is pending. Show the durable
`Incognito` marker only after the local preference write has been acknowledged;
on a failed or partial save, keep Incognito active for the current session and
show `Incognito not saved` with `Retry`/`Keep for this session`, never implying
that a restart will preserve it. An already accepted OS flush may finish, but
queued new or stale calibration training cannot publish after the toggle or
field transition.

Sensitive policy can force an effective Incognito state for password, unknown,
private, raw-terminal, and no-personalized-learning fields. The marker reads
`Incognito · required` and the user cannot turn it off for that field. Forced
Incognito always uses static hit geometry; it never applies a retained adaptive
profile. The saved preference remains visible as `Incognito preference: On/Off`,
while `Effective mode: Required` explains why the quick toggle is disabled.
Leaving the forced field restores the saved preference without changing it.

Incognito protects the keyboard's own capture, model context, calibration, and
local persistence. It does not claim that the host app is private, prevent the
host from logging its own input, or alter Android/editor retention outside the
IME. No new logs, telemetry, clipboard history, or text history are created by
either mode. `Reset preferences` turns calibration `Off`, preserves the
calibration profile, and preserves the current manual Incognito state;
deletion requires the separate, explicit `Clear calibration` action.

## Accessibility and ergonomics

Every utility key is at least 48dp in the default accessible profile; letter
keys use the width that fits the selected row without overlap. Every key has a
spoken label and state announcement, and remains reachable in one-handed mode.
One-handed
mode aligns the complete shell left or right and provides a fixed `Center
keyboard`/`Exit one-handed mode` control in Tools. Split and floating modes are
separate gates; until physical and accessibility evidence exists they are
labelled experimental and do not change the default profile.

TalkBack focus order follows context bar, utility actions, rows left-to-right,
then bottom actions. Switch Access can scan every action without requiring a
gesture. Large text increases panel height or enables deliberate scrolling; it
does not clip labels or hide Voice, Edit, Terminal, Space, Backspace, or the
editor action. Color never carries modifier, recording, error, or selection
state alone. Haptic/audio feedback respects system and sensitive-field policy.

## Gesture ownership and conflict table

| Gesture/action | Owner | Default | Tap alternative | Conflict resolution |
| --- | --- | --- | --- | --- |
| Space tap | Text entry | Insert space | None needed | Never also moves cursor. |
| Space horizontal slide | Cursor navigation | Off until enabled | Edit `←`/`→` | Cancels on direction reversal or multi-touch; one gesture has one owner. |
| Shift+Space | Selection navigation | Off until enabled | Edit `Select`, arrows | Selection wins only when Shift began before Space and field is non-terminal. |
| Letter long press/slide | Alternate character | On for reviewed accents | Tools `Accents` | Cancel on leaving key; at most one output. |
| Period long press/slide | Punctuation picker | On where reviewed | Tools `Accents` → period | Normal period tap remains immediate. |
| Backspace hold | Delete repeat | On with conservative repeat | Tap `Backspace` repeatedly or Edit `Del →` | Stops on focus loss, pointer cancel, or field change. |
| Backspace drag | Delete by word/range | Off | Edit navigation and delete | Never shares ownership with cursor gestures. |
| Emoji search | Emoji surface | Tap only | Tools `Emoji` | Search text stays local and is cleared on exit unless the user saves a setting. |
| Voice hold | Voice capture | Off | Tap `Dictate`, then `Stop` | Pointer drift/multi-touch cancels; release never submits host action. |
| Ctrl/Alt/Shift | Terminal | Tap to arm one chord | Terminal modifier keys | Terminal owns modifier gestures; Daily never emits a raw chord. |

## Resource and language readiness

Each language has an explicit row with separate columns for `Layout`,
`Dictionary`, `Composition`, `Prediction`, `Speech`, and `Swipe`. A language is
selectable for typing when its reviewed layout exists; unavailable columns say
`Not installed` or `Not supported`. Switching language preserves the current
editor selection and invalidates pending suggestions, voice, alternate pickers,
and modifiers. QWERTY, QWERTZ, and AZERTY are separate reviewed layouts.

Accents, dead keys, compose sequences, RTL mixing, emoji sequences, and complex
scripts require language-specific evidence. Swipe requires its own licensed,
bounded decoder and measures accuracy, repair effort, latency, memory, battery,
cancellation, and privacy. A dictionary-only decoder cannot be presented as
swipe parity. Prediction context is transient and bounded to 256 Unicode code
points. There is no passive learning; personal vocabulary changes require an
explicit add/remove action and remain inspectable and erasable.

Inline autofill is delegated to supported Android/password-manager integration.
The IME does not scrape, persist, or learn credentials. Custom layouts, when
implemented, are versioned data-only imports with preview, validation,
rollback, and a known-good escape; they cannot contain code, scripts, or native
libraries.

## Sensitive and raw-terminal policy

The keyboard uses `EditorInfo` metadata, the current session, and conservative
unknown-field handling. Password and unknown-sensitive fields disable speech,
prediction, learning, read-back, and surrounding-text access. Raw terminal
fields additionally disable Unicode fallback and smart text behavior. Denied
microphone permission never blocks ordinary typing.

The secure window prevents screenshots where supported. No raw text or audio is
logged. Clipboard access occurs only after an explicit Paste action, and there
is no clipboard history. A result from speech, model work, suggestions, edit
actions, or a gesture is accepted only when its editor/session generation still
matches. On any mismatch it is cancelled without replaying into the new field.

## Delivery grouping and parity accounting

All baseline checklist capabilities remain in scope. The grouping below is a
delivery order, not permission to omit a row:

| Delivery | Checklist scope | Experience outcome |
| --- | --- | --- |
| Foundation | P0, K01–K08, V01, V05, X01–X03, E01 | Stable Daily shell, safe sessions, local voice review, persistence/reset, accessibility contract, and model readiness. |
| Edit and power | A04–A07, A02, A06, T01–T05, U01–U02 | In-place Edit; explicit Terminal with Ctrl/Alt/Esc/Tab/arrows/Fn; selection, clipboard, undo/redo, correction, and voice-to-edit path. |
| Language and correction | K03–K06, L01–L07, L10, V04 | Reviewed layouts, accents/compose, emoji, reversible suggestions/correction, explicit vocabulary, language switching, and separate readiness status. |
| Evaluated engines | L08–L09, V03, U03, U05 | Licensed offline swipe and prediction, bounded transient context, silence stop, model switching, and named-device resource evidence. |
| Ergonomics and integration | K09, A01, A03, A05, A08–A09, V02, U04, U06, P5 | Inline autofill, gesture configuration, pinned/reordered actions, one-handed, split/floating, custom data layouts, routes, practice, and original identity. |

The release record for every row is one of `planned`, `source implemented`,
`automated evidence`, or `physical evidence`, with named device, OS, editor,
language, and limitations. Screenshots and emulator results do not advance a
row to physical acceptance. Unsupported editor behavior is documented beside
the control that exposes it. No feature is silently dropped from the baseline;
separate gates remain visible until their feasibility, provenance, security,
quality, and accessibility evidence is complete.
