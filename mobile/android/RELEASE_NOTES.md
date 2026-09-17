# Utterleaf Android 0.1.0-alpha17

This experimental preview rebuilds the everyday keyboard to the approved design:
an icon toolbar with a fold-out Extra keys panel, a hinted number row, a
redesigned Settings screen, a password-manager shortcut restricted to password
fields, and a suggestion strip that completes the word you are typing.

## What changed

- **The approved daily redesign.** The letter keyboard gains an icon toolbar
  (undo, redo, copy, cut, paste, private draft, dictate and an expand chevron)
  with editing actions one tap away instead of stacked text buttons. The
  chevron opens the **Extra keys panel** — Esc, Tab, Ctrl, Alt, Shift, Home,
  End, Ins, Del, PgUp, PgDn and the arrow keys — above the letters, with
  **F1–F12** behind Fn. The old permanent Terminal row and the Tools/Edit
  button strips are superseded; all previous routes keep tap-accessible
  equivalents (Caps lock is a long-press on Shift, keyboard tools and settings
  are a hold on the emoji key).
- **Hinted number row on by default**, with the digit hints you hold to type.
  Letter hints show symbols while the number row is visible and digits when it
  is hidden, so hold-to-insert stays complete. Hints sit where the design puts
  them and remain optional in Settings.
- **The mockup bottom row**: `?123`, an emoji key (hold it for keyboard tools
  and settings), a space labeled with the active language such as
  "English (US)", period, and a rounded Enter pill that follows the editor's
  action. The comma key moves to the period key's slide menu and the symbols
  page.
- **Redesigned Settings**: a searchable category list (Layout & size,
  Navigation & terminal, Typing assistance, Holds & gestures, Appearance,
  Voice input, Privacy & data) with staged edits — **Apply** saves and
  **Cancel** discards — plus a practice message with a live keyboard preview.
  New options include fold-out extra keys, auto-capitalization, arrow repeat,
  key borders and a System/Light/Dark theme. Reset preferences restores the
  new defaults and never deletes models.
- **Password-manager shortcut, password fields only.** A keyring button
  appears in the toolbar on explicit password fields and opens your configured
  autofill application. It is never shown on ordinary text, email or number
  fields; the keyboard sends nothing to the target application, and the key
  does not exist when no autofill application is configured.
- **Suggestion strip.** While you type, up to three completions of the current
  word appear below the toolbar, drawn from a frequency-ordered English list
  derived solely from public-domain Project Gutenberg texts. Tapping a
  suggestion completes only the word being typed — nothing is auto-corrected,
  learned or sent. The strip is off on password and terminal fields, has an
  on/off switch under Typing assistance, and adds no permissions.

Alpha16's All Actions behavior, latched Ctrl/Alt, complete US punctuation,
Backspace selection gesture, private drafts, local emoji, Latin composition,
QWERTY/QWERTZ/AZERTY layouts, one-hand alignment and long-press hint insertion
remain included. The keyboard engine is Utterleaf's own implementation.
Existing preferences migrate once to the new defaults; your explicit choices
are kept from then on.

## Install and updates

Use **Utterleaf-Android-0.1.0-alpha17.apk**, version code **17**. The package remains
`org.utterleaf.voice` and retains the persistent alpha03-and-later signing
identity. Update an existing signed preview in place; do not uninstall first.
The display name does not create a second app or a new settings store.
Alpha01/alpha02 used disposable debug signers and require a one-time reinstall,
which removes their app data.

The release includes SHA-256 checksums, public signing-certificate information
and version metadata. The separate experimental foundation package is not this
update channel. Never substitute an unsigned or CI debug APK for a signed update.

## Verification and limits

This is an Android 8+ ARM64/x86_64 development preview, with English typing layouts
and reviewed English offline speech models. Automated checks cover the new
toolbar, panel and strip behavior, the restricted-field gates, native editor,
gesture, privacy and layout contracts. The signing workflow requires successful
exact-revision Android CI, package/version/certificate checks and signed
install/upgrade/reinstall checks before publication.

Physical-phone testing is deferred to follow-up user feedback. TalkBack, Switch
Access, landscape, broad editor behavior and real Obtainium updates remain
unverified. The suggestion list is drawn from classical prose and
under-represents some modern vocabulary; expandable local word lists are
planned. Suggestions complete words but never replace them: auto-correction,
next-word prediction, swipe typing and broader language support are not
included in this snapshot.

Typing needs no model or microphone permission. Dictation starts only by an
explicit action and is disabled in password fields. The password-manager key
launches your configured autofill application and sends it nothing. No Internet
permission, ambient recording, typing history, clipboard monitoring or saved
audio history is added. Explicit Copy/Cut/Paste still use the receiving editor's
clipboard commands. Keyboard screenshot protection remains enabled.
