# Utterleaf Android 0.1.0-alpha03

An early typing keyboard with integrated local dictation. Select **Utterleaf
Keyboard** in Android's keyboard picker; the separate **Utterleaf Voice** provider
remains available for compatible keyboards.

- English letters, numbers and ASCII symbols, Shift/Caps, deletion, cursor arrows,
  and editor-specific Enter actions. No model or microphone permission needed to type.
- Mic opens the existing local voice panel; Back to keyboard returns to typing.
- Password typing remains available; dictation is disabled in password fields.
- Larger keys/labels, a light keyboard option, optional haptics, optional repeated-tap
  filtering, live preferences preview and reset. Native controls expose key labels.
- Voice previews warn before clearing and offer Keep reviewing to extend the timeout.
- Obtainium setup button with Android-only release/APK filters. No built-in updater
  or Internet permission added.

## Install and updates

Use **Utterleaf-Android-0.1.0-alpha03.apk**. This is the first release using the
persistent Android release signing identity rather than a disposable debug key.
If alpha01/alpha02 is installed, uninstall it once before installing this release;
uninstalling removes the imported speech model, so import it again afterward.
Later releases in this channel will use the same signing identity and increasing
version codes. Do not mix CI debug APKs into this update channel.

[Obtainium setup](https://github.com/RioPlay/utterleaf/blob/main/docs/mobile-obtainium.md)
includes the public signing fingerprint and manual configuration. Release assets
include APK checksums, certificate verification output and version metadata.

## Limits

This is an alpha, not a finished everyday keyboard. English UI/layout and English
speech only; no predictions, autocorrection, swipe typing, emoji picker or learned
dictionary yet. Speech takes still have a 120-second bound. Small-screen/landscape
layout, assistive-technology workflows and device/editor interoperability need
physical testing. Large keys can require scrolling in a short keyboard area.

Automated tests cover privacy/model rules, real local inference and microphone
cancellation, voice/keyboard registration, typing callbacks, and preview rendering.
Release signing verifies the package, version, signer and APK alignment, then
tests installation and same-version replacement on an API 35 emulator. That is
not proof of a version-to-version update on a physical phone.

Desktop releases and the desktop stable download are unchanged.
