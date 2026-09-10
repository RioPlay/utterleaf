# Utterleaf Android 0.1.0-alpha12

- Tap Edit in the toolbar for Undo, Redo, Select all, Cut, Copy, Paste,
  four-way cursor movement, selection mode, Home and End. ABC returns to typing.
  The action panel replaces the letters instead of adding height above them.
- Actions work through the current editor's Android API, including the practice
  editor and local transcript editor. Unsupported commands show Key unavailable.
  Undo/redo depend on the receiving editor's history and command support.
- No clipboard monitoring or history: Copy/Cut/Paste happen only on explicit taps
  through the editor. Copy/Cut are blocked for password fields. Raw terminal
  fields receive no context-menu or fallback Ctrl commands from these actions;
  use Terminal controls for terminal shortcuts.
- Switching fields, leaving the panel or resetting it invalidates old action
  controls. Error feedback has room below the toolbar when needed.

## Included from alpha11

- A compact toolbar provides number-row and terminal-mode toggles without opening
  Settings. Toggles preserve other preferences and stay synchronized with the
  Settings practice keyboard. Utterleaf artwork replaces the Voice text button,
  with a full-size touch target and a Dictate accessibility label.
- Expand or collapse the transcript before inserting. Review supports scrolling
  and selection, with Edit transcript beside the expansion control. Recording
  preferences and model selection stay out of review; entering editing restores
  a smaller preview to leave room for the keys.
- Reaching the recording limit now changes the controls to Transcribing without
  requiring a Stop tap. Late status callbacks cannot overwrite review or affect
  the next take.

Updates use the existing signing identity and an increased version code. Install
over an existing signed release; no uninstall is needed. Processing remains local
and CPU-only. GPU/NPU support and an optional desktop on-screen keyboard remain
planned work, not features of this APK.

## Included from alpha10

- Hold Ctrl or Alt and press another key with a second finger. Ctrl+Backspace
  sends word deletion to compatible editors. The modifier remains active for
  subsequent presses until released; holding Delete repeats the modified key.
  Moving outside, cancellation and panel changes clear the physical chord.
  Tap-to-arm remains available. Application shortcut behavior varies; this does
  not implement drag-to-preview deletion or universal desktop shortcut parity.
- Held deletion has its own preference, enabled by default, separate from
  repeated-tap filtering. Reset restores it without deleting imported models.
- Keep multiple reviewed English models installed and switch without reimporting.
  Setup shows Fast (tiny.en), Balanced (base.en) and Larger (small.en), plus
  installed/active status. A larger model costs more memory and processing time
  and does not guarantee accuracy. The idle voice panel offers a quick model
  choice when multiple models are installed. Switches apply between takes.
- Old verified imports remain available after upgrading. Imports still verify
  full SHA-256 before publication; invalid imports preserve the previous model.
  Delete an individual model in setup. Deleting the active model requires
  selecting another installed model before dictation can resume.

One-handed voice controls and local transcript editing build on the keyboard editing improvements. This is still an
alpha keyboard; suggestions, autocorrection, swipe typing, multilingual layouts
and emoji remain roadmap work.

- One primary voice button stays in place: Speak, Stop, then Insert. A short
  post-insertion delay prevents a rapid second tap starting another capture.
- Tapping Dictate on the typing keyboard immediately starts a reviewable take.
  Returning to a field never starts recording automatically. The voice heading
  reuses the desktop's transparent idle, recording and processing icons.
- Edit transcript opens a local typing surface. Use edits returns to review;
  Insert sends the edited text. Edits stay in the protected panel, are not saved,
  and are cleared on expiry, discard, dismissal or input-session changes.
- Optional hold-to-speak mode starts after the system hold delay and inserts
  after release and recognition. Slide outside to cancel. A changed field or
  dismissed panel cancels delivery. Review/tap mode remains the default.
- Failed automatic insertion retains the transcript for an explicit retry or edit.
  Reset keyboard preferences also restores review mode.

- Hold the period key for common punctuation, slide to a highlighted mark and
  release. A normal tap still types a period; slide away to cancel.

- Tune key height and bottom spacing independently, with a live practice area.
  Practice text is bounded, protected from screenshots, never saved and cleared
  when leaving settings. Reset restores default height and spacing.

- Hold Shift first, then slide the spacebar with a second finger to select text.
  Either finger lifting stops selection, without typing a space or latching Shift.
  Tools → Select plus the arrows provides a tap-only route.
- Hold Backspace or forward Delete for steady repetition after the system hold
  delay. Release, move outside or dismiss the keyboard to stop. Repeat filtering
  disables held deletion. No automatic acceleration to whole-word deletion.
- Tools exposes Delete to right, Home and End; the optional terminal layer retains
  Esc, Tab, Ctrl/Alt, arrows, Page Up/Down, Insert and F1–F12.
- Shift-space selection dispatches only Shift+arrow, independent of armed Ctrl/Alt.
  Editor support varies; named terminal and physical-phone acceptance remain open.

- **Import a model** identifies supported tiny.en, base.en and small.en files by
  verified size and SHA-256. The download choice no longer restricts import.
  A failed import preserves the previous model; the app still has no Internet permission.
- Slide the spacebar left/right to move the cursor; tap it to type a space.
- Hold a letter, slide to the highlighted accent/symbol and release to insert it.
  Slide away to cancel. The compact strip stays inside the protected keyboard window.
- Cancellation, multitouch, panel changes and dismissal clear active gestures.

- Secondary symbols are visible on letter keys by default; hide them in keyboard settings.
- For a tap-only route to an accent or secondary symbol,
  choose Tools → Accents, then a letter. Cancel returns without inserting anything.
- Shift and Caps apply to accents. Unsupported terminal combinations show an error
  without silently inserting plain text. Common Latin accents are not full language support.
- Old keyboard/picker callbacks are invalidated on layout or input-session changes.
- Hints yield to primary labels at very large font sizes; accent selection remains
  available with hints hidden.

- Consistent staggered letter rows, Shift/Delete beside the letters, a wide
  spacebar, direct comma/period keys and a highlighted editor action.
- Compact Tools button reveals cursor controls, Caps Lock, settings and switching.
- Dark/light keycaps with visible focus and selected states; larger keys retained.
- Optional number row, independent of the optional terminal controls.
- Guided keyboard setup with separate typing/voice readiness and verified
  tiny.en, base.en and small.en model choices, sizes and browser download links.
- Terminal controls provide Esc, Tab, Ctrl, Alt, arrows, Home/End, Page Up/Down and
  F1–F12, Insert and forward Delete. Ctrl/Alt release after the next key and reset when the field changes.
  Raw terminal fields accept ASCII key events only when terminal mode is enabled;
  dictation stays disabled there. Terminal applications determine shortcut support.

Select **Utterleaf Keyboard** in Android's picker. Typing needs no model or
microphone permission. The separate Utterleaf Voice provider remains available.
No Internet permission, typing history, clipboard collection or saved recordings.
Dictation is explicit and remains disabled in password fields.

## Install and updates

Use **Utterleaf-Android-0.1.0-alpha07.apk**, version code 7. It uses the persistent
alpha03–alpha06 signing identity and supports installing over those releases.
Do not uninstall first: Android removes app settings and the model on uninstall.
Alpha01/alpha02 used disposable debug keys and require a one-time uninstall.

[Obtainium setup](https://github.com/RioPlay/utterleaf/blob/main/docs/mobile-obtainium.md)
explains the signed channel. APK checksums and public signer metadata accompany
this release. Never substitute an unsigned or CI debug APK for a release update.

## Validation and limits

Android 8+ on ARM64/x86_64. English layout and speech only; speech takes remain
bounded to 120 seconds. Automated checks cover native key actions, geometry at
320/412dp with both themes/key sizes, modifier event dispatch, real local inference,
privacy rules and live synthetic editor interactions. These are not physical
terminal, TalkBack, Switch Access or landscape acceptance tests. Large keys and
terminal rows may require scrolling on short displays. Modified input requires a
single supported ASCII character; unsupported combinations are not inserted as
plain text. Small-model speed, memory use and accuracy still need physical-phone
validation; its larger download is not a promise of a better result for every user.
Installation and upgrade checks run separately before publication.
