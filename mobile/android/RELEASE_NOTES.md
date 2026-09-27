# Utterleaf Android 0.1.0-alpha21

This preview makes ordinary typing calmer while keeping Utterleaf's editing,
terminal, navigation and offline-voice tools available on demand.

## What changed

- The ordinary keyboard now uses one compact daily row: **Tools**, **Edit**,
  three stable suggestion positions and **Dictate**. Secondary editing actions,
  Emoji, Private Draft and specialist controls appear only when requested.
- The bottom row is continuous: **?123**, comma, Space, period and the field's
  dynamic action key. The unused bottom-left gap is gone.
- Tools keeps editing, navigation, symbols, Compose, alternate letter layouts,
  the optional number row, Extra Keys, modifiers, Fn keys and terminal controls
  available without making them permanent keyboard chrome.
- Suggestion completion checks the editor's live selection immediately before
  replacing text. A delayed Android selection callback can no longer make a
  completion overwrite selected text.
- Portrait and landscape preserve the single daily row. Split landscape retains
  only its intentional center channel; ordinary and one-hand layouts have no
  inert bottom-row slot.

The layout was designed independently after clean-room study of familiar Android
keyboard interaction patterns. No FUTO code, assets, labels, constants or theme
values were copied.

No new permission, dependency, network access, telemetry, ambient recording,
clipboard inspection, typing history or model-loading path is introduced.

## Install and updates

Use **Utterleaf-Android-0.1.0-alpha21.apk**, version code **21**. The package remains
`org.utterleaf.voice` with the persistent alpha03-and-later signing identity.
Update a signed alpha20 or earlier preview in place; do not uninstall first.
Alpha01/02 used different debug signers and require a one-time reinstall that
removes their app data. The experimental foundation package is a separate channel.

The release includes SHA-256 checksums, signing-certificate information, and
version metadata. Use the signed APK, not an unsigned or CI debug build.

## Verification and limits

Android 8+ ARM64/x86_64 development preview. Exact-candidate Android CI and the
protected signing/install/upgrade checks are required before publication. Emulator
coverage exercises daily/sensitive geometry, editing and selection safety; the
broader alpha20 privacy, lifecycle, terminal, voice and settings behavior remains.

Emulator success does not establish physical-phone comfort. Pixel 8 Pro/GrapheneOS,
broader editor, TalkBack/Switch Access, phone layout/latency, and real Obtainium
acceptance remain explicit follow-up work.

The daily row, continuous bottom row, split channel and Tools disclosure are
covered on the visible API 35 emulator. Physical-phone reach and comfort remain
unverified.

No automatic correction, next-word prediction, swipe typing, streaming partial
dictation, or language expansion is added. Typing needs no model or microphone
permission. Dictation remains explicit and unavailable in password fields.
Screenshot protection remains enabled.

Changing fields still cancels/clears dictation rather than carrying a transcript
to another target. Recoverable stale-result delivery and the replacement Tools
composition remain planned. Standalone voice landscape/large-font reachability,
extreme narrow/large-text Settings header wrapping, and the final accessibility
audit remain open; passing emulator bounds checks is not full usability evidence.
