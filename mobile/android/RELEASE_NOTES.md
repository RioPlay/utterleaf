# Utterleaf Android 0.1.0-alpha05

A redesigned typing surface with an optional terminal layer. This is still an
alpha keyboard; suggestions, autocorrection, swipe typing, multilingual layouts
and emoji remain roadmap work.

- Consistent staggered letter rows, Shift/Delete beside the letters, a wide
  spacebar, direct comma/period keys and a highlighted editor action.
- Compact Tools button reveals cursor controls, Caps Lock, settings and switching.
- Dark/light keycaps with visible focus and selected states; larger keys retained.
- Optional number row, independent of the optional terminal controls.
- Terminal controls provide Esc, Tab, Ctrl, Alt, arrows, Home/End, Page Up/Down and
  F1–F12. Ctrl/Alt release after the next key and reset when the field changes.
  Raw terminal fields accept ASCII key events only when terminal mode is enabled;
  dictation stays disabled there. Terminal applications determine shortcut support.

Select **Utterleaf Keyboard** in Android's picker. Typing needs no model or
microphone permission. The separate Utterleaf Voice provider remains available.
No Internet permission, typing history, clipboard collection or saved recordings.
Dictation is explicit and remains disabled in password fields.

## Install and updates

Use **Utterleaf-Android-0.1.0-alpha05.apk**, version code 5. It uses the persistent
alpha03/alpha04 signing identity and supports installing over those releases.
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
plain text. Installation and upgrade checks run separately before publication.

The visual design uses independent native Android code; FUTO's public screenshots
were a reference, with no FUTO source or artwork included.
