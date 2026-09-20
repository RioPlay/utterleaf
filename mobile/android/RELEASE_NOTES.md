# Utterleaf Android 0.1.0-alpha20

This preview polishes the daily keyboard, makes editing easier to reach, adds
complete dark appearance choices, and shortens routine Android CI feedback.

## What changed

- The stable toolbar now has four clear daily destinations: **Tools**, **Edit**,
  **Emoji**, and **Voice**. Less-common controls remain one shallow layer away
  without crowding the letter rows.
- **Edit** groups Undo, Redo, Select all, Cut, Copy, Paste, cursor movement, and
  Extra keys. The Extra keys panel keeps terminal/navigation controls available
  without making them permanent keyboard chrome.
- Settings, setup, keyboard, emoji, private draft, and voice surfaces share the
  selected palette. Appearance now offers **System**, **Light**, **Dark**, and
  true-black **OLED** modes.
- A normal mic tap preserves the review-and-correct flow before **Insert**.
  **Hold mic to insert after recognition** remains an explicit opt-in shortcut.
- Protected drafts omit voice, password-manager routes, host settings, keyboard
  switching, and preference toggles. Opening Extra keys no longer changes its
  saved preference.
- Superseded pull-request runs cancel automatically. Pull requests perform the
  fast compile, unit-test, lint, and debug-build path; the full emulator,
  privacy/inference, release build, and packaging gates still run on the exact
  main/manual release candidate.

No new permissions, dependencies, ambient recording, text history, clipboard
automation, or network access are added. Live partial transcription into the
receiving editor is intentionally deferred: rewriting host text while speech is
still changing needs a separate editor-compatibility and privacy design.

## Install and updates

Use **Utterleaf-Android-0.1.0-alpha20.apk**, version code **20**. The package remains
`org.utterleaf.voice` with the persistent alpha03-and-later signing identity.
Update a signed alpha19 or earlier preview in place; do not uninstall first.
Alpha01/02 used different debug signers and require a one-time reinstall that
removes their app data. The experimental foundation package is a separate channel.

The release includes SHA-256 checksums, signing-certificate information, and
version metadata. Use the signed APK, not an unsigned or CI debug build.

## Verification and limits

Android 8+ ARM64/x86_64 development preview. Exact-candidate Android CI and the
protected signing/install/upgrade checks are required before publication. Emulator
coverage exercises appearance persistence, OLED black backgrounds, daily layers,
private-mode isolation, editing, terminal controls, voice review, and settings.

Emulator success does not establish physical-phone comfort. Pixel 8 Pro/GrapheneOS,
broader editor, TalkBack/Switch Access, phone layout/latency, and real Obtainium
acceptance remain explicit follow-up work.

No automatic correction, next-word prediction, swipe typing, streaming partial
dictation, or language expansion is added. Typing needs no model or microphone
permission. Dictation remains explicit and unavailable in password fields.
Screenshot protection remains enabled.
