# Utterleaf Android 0.1.0-alpha04

An early typing keyboard with integrated local dictation. Select **Utterleaf
Keyboard** in Android's keyboard picker; the separate **Utterleaf Voice** provider
remains available for compatible keyboards.

- Fixed Shift with Caps Lock: Shift now produces one lowercase letter, then returns
  to capitals. Key labels match the letter that will be entered.
- Added a live keyboard/editor regression test for typing, deletion, cursor movement,
  editor actions, password-field dictation blocking, and hiding/reopening the keyboard.
  The synthetic test editor is excluded from release APKs.

Typing still works without a model or microphone permission. Dictation stays local,
requires an explicit tap, and is disabled in password fields. No Internet permission,
saved recordings, automatic clipboard writes or built-in updater. Voice previews
clear after two minutes unless Keep reviewing extends the timeout.

## Install and updates

Use **Utterleaf-Android-0.1.0-alpha04.apk**. Alpha04 uses the same persistent signing
identity as alpha03 and increases the version code to 4. Install it over signed
alpha03 without uninstalling; settings and the imported speech model are retained.

If alpha01/alpha02 is installed, uninstall it once before installing this release
because those builds used disposable debug keys. Uninstalling removes the imported
speech model, so import it again afterward. Do not mix CI debug APKs into this channel.

[Obtainium setup](https://github.com/RioPlay/utterleaf/blob/main/docs/mobile-obtainium.md)
includes the public signing fingerprint and manual configuration. Release assets
include APK checksums, certificate verification output and version metadata.

## Limits

Android 8.0 or later on ARM64 or x86_64 is required. This is an alpha, not a finished
everyday keyboard. English UI/layout and English
speech only; no predictions, autocorrection, swipe typing, emoji picker or learned
dictionary yet. Speech takes still have a 120-second bound. Small-screen/landscape
layout, assistive-technology workflows and device/editor interoperability need
physical testing. Large keys can require scrolling in a short keyboard area.

Automated tests cover privacy/model rules, real local inference and microphone
cancellation, voice/keyboard registration, live keyboard/editor interactions,
typing callbacks, and preview rendering.
Release signing verifies the package, version, signer and APK alignment, then
tests installation and same-version replacement on an API 35 emulator. That is
not proof of a version-to-version update on a physical phone.

Desktop releases and the desktop stable download are unchanged.
