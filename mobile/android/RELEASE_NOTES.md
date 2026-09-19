# Utterleaf Android 0.1.0-alpha19

This preview fixes two Backspace problems reported after alpha18.

## What changed

- Holding Backspace keeps deleting after automatic capitalization or ordinary
  letter-case Shift. Capitalization no longer turns Backspace into a single
  modified delete or changes its backward direction.
- You can start holding Backspace and then slide left to select more text.
  Repeat stops before selection begins. Release deletes the highlighted range
  once; sliding back shrinks it. Text already removed by the hold stays removed.
- Cancelling, reversing to the origin or an editor refusing the swipe does not
  restart repeat or produce an extra Backspace tap. Password/raw fields and
  Extra keys retain their restrictions; explicit modifier behavior is preserved.

Held repeat remains controlled by **Hold Backspace or Delete to repeat** and
**Ignore repeated taps on the same key within 250 ms**. Swipe selection depends on the editor confirming native
selection movement. It is refused in password/raw fields and with Extra keys open.

Alpha18's typing/suggestion stability fixes and staged Settings remain included.
No new permissions, dependencies, recording, text history or network access.

## Install and updates

Use **Utterleaf-Android-0.1.0-alpha19.apk**, version code **19**. The package remains
`org.utterleaf.voice` with the persistent alpha03-and-later signing identity.
Update a signed alpha18 or earlier preview in place; do not uninstall first.
Alpha01/02 used different debug signers and require a one-time reinstall that
removes their app data. The experimental foundation package is a separate channel.

The release includes SHA-256 checksums, signing-certificate information and version
metadata. Use the signed APK, not an unsigned or CI debug build.

## Verification and limits

Android 8+ ARM64/x86_64 development preview. Exact-candidate Android CI and the
protected signing/install/upgrade checks are required before publication. Regression
coverage includes sustained hold, late swipe, cancellation/refusal/reversal,
capitalization, editor-confirmed deletion, modifiers and repeat preferences.

Pixel 8 Pro/GrapheneOS confirmation of the reported gesture remains open, as do
broader editor, TalkBack/Switch Access, phone layout/latency and real Obtainium
acceptance. Emulator success does not establish physical-phone comfort.

No automatic correction, next-word prediction, swipe typing or language expansion
is added. Typing needs no model or microphone permission. Dictation remains explicit
and unavailable in password fields. Screenshot protection remains enabled.
