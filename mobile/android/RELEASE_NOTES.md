# Utterleaf Android 0.1.0

The first stable Utterleaf Android release offers an English keyboard with local
word completions and optional offline dictation.

- The daily row keeps Tools, Edit, suggestions and Dictate within reach.
- Space stays broad on narrow keyboards while the bottom-row controls retain
  48 dp touch targets. Suggestions and key hints are quieter, and key presses
  and focus have distinct feedback.
- The embedded speech engine and Android build dependencies include the reviewed
  security updates.

## Install or update

Use **Utterleaf-Android-0.1.0.apk**, version code **22**, on Android 8 or newer
with ARM64 or x86_64. The package is `org.utterleaf.voice` with the established
release signer. Update signed alpha03 and later installations in place to retain
settings and models. Alpha01 and alpha02 used different signers. Migrating from
either requires a reinstall, which removes the old installation's app data.

Typing requires neither a speech model nor microphone permission. Dictation
requires a supported local model and starts only on request. It is unavailable
in password fields and cancels when its editor target changes.

The release workflow checks Android emulator behavior, the APK signature and
alignment, and in-place upgrade and reinstall with synthetic preference and model
markers. Physical-device comfort, assistive-technology coverage and real
Obtainium updates remain unverified. Swipe typing and automatic correction are
outside this release.
