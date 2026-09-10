# Utterleaf Android 0.1.0-alpha08

Selection and held deletion improve everyday editing. This is still an
alpha keyboard; suggestions, autocorrection, swipe typing, multilingual layouts
and emoji remain roadmap work.

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
