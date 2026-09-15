# Utterleaf Android 0.1.0-alpha16

This experimental preview replaces the long Tools strip with everyday actions
that stay in reach, and makes Terminal modifiers stay on until you turn them off.

## What changed

- **All Actions instead of a sliding Tools strip.** Tools opens a bounded
  replacement layer for Edit, Emoji, drafts, accents, composition, layout,
  settings and keyboard switching. ABC returns to typing. No extra rows stack
  above the letters.
- **Spatial Edit pad.** Undo, Redo, Select all and forward Delete sit on the
  top row. Cut, Copy and Paste sit beside a directional pad. Tap Select to
  select the neighboring word through the editor's Ctrl+Shift+Left equivalent;
  hold Select for Select all. The existing Select all action remains on the
  same layer.
- **Terminal arrows stay beside the letters.** Esc, Tab, Ctrl, Alt, Nav and Fn
  use a shorter accessory row. F1–F12 remain behind Fn. Enabling Terminal from
  All Actions shows the accessory keys immediately.
- **Latched Ctrl and Alt.** Tap a modifier to keep it selected until you tap it
  again. Hold-chords still apply only while the finger is down. Shift stays
  selected for arrows and terminal keys, so Ctrl+Shift+Left can keep extending
  a word selection. Letter and digit Shift remain one-shot. Field and layer
  changes still clear local modifiers.
- **Complete US punctuation** on the two symbol pages, including brackets,
  braces, backtick, pipe and the usual paired marks.

Alpha15's compact Utterleaf names, Backspace selection gesture, comma-hold
Settings, two-thumb rollover, QWERTY/QWERTZ/AZERTY layouts, one-hand alignment,
local emoji, Latin composition, private drafts and visible long-press hints
remain included. The keyboard engine is Utterleaf's own implementation.

## Install and updates

Use **Utterleaf-Android-0.1.0-alpha16.apk**, version code **16**. The package remains
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
and reviewed English offline speech models. Automated checks cover native editor,
gesture, privacy and layout behavior. The signing workflow requires successful
exact-revision Android CI, package/version/certificate checks and signed
install/upgrade/reinstall checks before publication.

Physical-phone testing is deferred to follow-up user feedback. TalkBack, Switch
Access, landscape, broad editor behavior and real Obtainium updates remain
unverified. Emulator and owned-view renders do not establish typing comfort or
assistive-technology usability.

Android speech takes still have a **120-second limit**. Longer desktop dictation
is a separate feature. Prediction, swipe typing, broader language support,
Incognito and touch heatmaps are not included in this snapshot.

Typing needs no model or microphone permission. Dictation starts only by an
explicit action and is disabled in password fields. No Internet permission,
ambient recording, typing history, clipboard monitoring or saved audio history
is added. Explicit Copy/Cut/Paste still use the receiving editor's clipboard
commands. Keyboard screenshot protection remains enabled.
