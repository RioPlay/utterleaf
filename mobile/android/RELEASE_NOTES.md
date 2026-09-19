# Utterleaf Android 0.1.0-alpha18

This preview focuses on dependable everyday typing and predictable customization.
It includes the alpha17 typing/suggestion stabilization and a settings usability
pass. Alpha17's layouts, local emoji, Compose, private drafts, extra keys and
password-field-only password-manager shortcut remain available.

## What changed

- **Typing stays independent of suggestions.** Dictionary loading and bounded
  suggestion reads run off the typing path. Completions refresh after cursor
  changes and verify the exact word and session before replacing it. Stale or
  selected text is rejected. Ordinary touches avoid redundant modifier updates.
- **Stable suggestion geometry.** Empty and populated completion states keep the
  same row height, so the letters do not jump as you type. Insets and explicit
  bottom spacing have separate regression coverage.
- **Settings that honor Apply and Cancel.** Voice options, preview quick controls
  and confirmed resets now stay staged with the other preferences. Apply saves;
  Cancel discards. Reset never deletes models or other user data.
- **Controls before the preview.** Apply stays at the top while categories scroll.
  Theme, alignment and letter-layout selections immediately refresh the practice
  keyboard, including when returning to the original choice.
- **Consistent navigation.** Back returns from a category to the settings list;
  search text and results remain in sync. Rotation retains pending preferences in
  memory, while private practice input is cleared. Replaced preview panels are
  disposed so their old controls cannot insert text or save preferences.

## Install and updates

Use **Utterleaf-Android-0.1.0-alpha18.apk**, version code **18**. The package remains
`org.utterleaf.voice` with the persistent alpha03-and-later signing identity.
Update an existing signed preview in place; do not uninstall first. Alpha01/02
used different debug signers and require a one-time reinstall that removes their
app data. The experimental foundation package is a separate channel.

The release includes SHA-256 checksums, signing-certificate information and version
metadata. Do not substitute an unsigned or CI debug APK for a signed update.

## Verification and limits

Android 8+ ARM64/x86_64 development preview. The release workflow requires
successful exact-revision CI, package/version/certificate checks and signed
install/upgrade/reinstall checks. Focused emulator tests cover staged voice/reset,
preview controls, reversible choices, rotation, navigation and model preservation.
Settings views are reviewed at default, narrow/large-text and landscape emulator
sizes. These checks do not establish physical-phone comfort or latency.

Pixel 8 Pro/GrapheneOS, broad external editors, TalkBack/Switch Access, sustained
landscape use and real Obtainium updates remain open acceptance gates. An editor
that blocks a suggestion read can delay later suggestions until that read returns;
ordinary typing remains independent. Tapping a suggestion still re-verifies the
word through the editor and can wait for a slow editor response.

The public-domain English completion list under-represents modern vocabulary.
No automatic correction, next-word prediction, swipe or broader language support
is added. No Internet permission, typing history, passive learning, clipboard
monitoring or ambient recording is added. Typing needs no model or microphone
permission. Dictation requires an explicit action and is disabled in password
fields. Keyboard screenshot protection remains enabled.
