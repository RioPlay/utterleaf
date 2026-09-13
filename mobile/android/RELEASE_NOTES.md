# Utterleaf Android 0.1.0-alpha15

This experimental preview makes the original Utterleaf keyboard substantially
more compact and gives it the shorter installed name **Utterleaf**.

## What changed

- **One sliding Tools strip.** Select all, Cut, Copy, Paste and additional tools
  share a horizontal row. Swipe the strip or use More to reveal actions; the
  ABC exit stays visible. Opening Tools no longer stacks five rows above the keys.
- **Separate layers for controls.** Layout/settings and Edit replace the letter
  area. Terminal navigation and function keys use replacement layers with one
  modifier row. The optional number row remains an independent preference.
- **Hold comma for settings.** A normal tap still inserts one comma. Holding
  opens the compact layout/settings layer without inserting punctuation.
  Cancellation and session changes discard pending holds; private-draft guards
  continue to prevent leaving the protected editor through Settings.
- **Backspace selection.** Drag left from Backspace to preview a selection and
  release to delete it once. Reversing shrinks the selection without crossing its
  starting point. Tap and held-repeat deletion remain available. Editor support
  varies, and restricted or unconfirmed editor states refuse the gesture.
- **Clearer presentation.** The toolbar uses restrained controls, consistent
  labels and secondary hints. The launcher and Android keyboard chooser now show
  Utterleaf. The optional voice-only provider is **Utterleaf dictation**.

Alpha14's two-thumb rollover, QWERTY/QWERTZ/AZERTY layouts, one-hand alignment,
local emoji, Latin composition, private drafts and visible long-press hint
selection remain included. The keyboard engine is Utterleaf's own implementation.

## Install and updates

Use **Utterleaf-Android-0.1.0-alpha15.apk**, version code **15**. The package remains
`org.utterleaf.voice` and retains the persistent alpha03-and-later signing
identity. Update an existing signed preview in place; do not uninstall first.
The shorter display name does not create a second app or a new settings store.
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
