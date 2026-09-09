# Utterleaf on phones

<img src="assets/brand/utterling-thinking.png" width="88" alt="Utterling considering mobile voice input" />

[Documentation](README.md) · [Roadmap](roadmap.md) · [Android preview](../mobile/android/README.md)

Mobile development follows the same priority as desktop: privacy and security
first, convenience second. The Android project is a separate native application;
it does not replace or add dependencies to the desktop Python application.

## Android — compact voice companion first

[Download the Android alpha](https://github.com/RioPlay/utterleaf/releases/tag/android-v0.1.0-alpha01) ·
[Setup and current limits](../mobile/android/README.md)

The initial implementation uses Kotlin, Android's input-method framework, and
local whisper.cpp inference. It offers a compact voice IME and an explicit
speech-recognition activity result for compatible keyboards. A full keyboard is
not required to test whether this solves the user's need.

See the [Android guide](../mobile/android/README.md) for exact implemented scope,
setup, permissions, test evidence and remaining native-device acceptance work.
Build success alone does not establish keyboard compatibility or phone usability.
Desktop vocabulary and spoken-command behavior have not yet been ported.

<img src="assets/screenshots/android-setup.png" width="300" alt="Utterleaf Voice Android setup with a friendly Utterling, dark controls, and three steps for model import, microphone permission, and keyboard activation" />

Actual debug APK on an API 35 Pixel 6 emulator. The setup page scrolls; no
recording or personal transcript is shown. Voice windows protect their contents
from screenshots.

### Android validation — September 9, 2026

The Android preview passes **4 JVM tests and 7 API 35 emulator tests**, including
hash rejection for same-size untrusted models, packaged permission/backup checks,
denied microphone access, password-field filtering, auxiliary voice subtype
discovery, stale-result rejection, single insertion, actual whisper.cpp
transcription of the pinned JFK speech fixture, and foreground microphone
capture/cancellation. ARM64 and x86_64 debug/release APKs compile; Android lint
passes its error gate. Remaining warnings include English UI localization and
newer dependency versions.

Native optimization reduced the fixture test from about 4m18s to 33s on separate
hosted emulator runs. These times include model import/verification/loading and
are **not a controlled benchmark or a prediction of phone dictation latency**.
Physical ARM64 speed, battery use, keyboard interoperability, TalkBack and
interruption tests remain unverified. See the
[Android CI reports](https://github.com/RioPlay/utterleaf/actions/workflows/android.yml).

## iOS — feasibility gate before promising keyboard dictation

Apple's [keyboard extension documentation](https://developer.apple.com/library/archive/documentation/General/Conceptual/ExtensibilityPG/CustomKeyboard.html)
states that extensions cannot access the microphone. A full custom keyboard does
not remove that restriction. Apple's
[interface guidance](https://developer.apple.com/documentation/uikit/configuring-a-custom-keyboard-interface)
describes containing-app integration but does not establish a universal replacement
for another keyboard's microphone provider.

The first iOS milestone should be a native foreground recording application with
local inference and explicit copy/share. Before adding a keyboard extension, prove
a supported containing-app handoff on a physical iPhone, review current App Store
rules, and measure lifecycle behavior. Do not use private APIs or keep a microphone
session alive between takes simply to make switching feel seamless.

No iOS application or keyboard extension is implemented in this Android pass.
The shared native inference option has upstream
[Android and iOS examples](https://github.com/ggml-org/whisper.cpp), but each platform
still needs its own permission, audio, UI, and delivery tests.
