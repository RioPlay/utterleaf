# Utterleaf on phones

<img src="assets/brand/utterling-thinking.png" width="88" alt="Utterling considering mobile voice input" />

[Documentation](README.md) · [Roadmap](roadmap.md) · [Android preview](../mobile/android/README.md)

Mobile development follows the same priority as desktop: privacy and security
first, convenience second. The Android project is a separate native application;
it does not replace or add dependencies to the desktop Python application.

## Android — compact voice companion first

The initial implementation uses Kotlin, Android's input-method framework, and
local whisper.cpp inference. It offers a compact voice IME and an explicit
speech-recognition activity result for compatible keyboards. A full keyboard is
not required to test whether this solves the user's need.

See the [Android guide](../mobile/android/README.md) for exact implemented scope,
setup, permissions, test evidence and remaining native-device acceptance work.
Build success alone does not establish keyboard compatibility or phone usability.
Desktop vocabulary and spoken-command behavior have not yet been ported.

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
