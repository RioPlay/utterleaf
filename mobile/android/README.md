# Utterleaf for Android

<img src="../../docs/assets/brand/utterling-listening.png" width="88" alt="Listening Utterling" />

An experimental English typing keyboard with integrated offline dictation.
**0.1.0-alpha03 is released as a signed development preview.** Typing works without
microphone permission or a speech model. A separate voice-only option remains
available for compatible keyboards.

This is the foundation for a complete customizable keyboard. Broader language,
prediction, accessibility and device coverage remain on the
[mobile roadmap](../../docs/mobile-roadmap.md). Desktop development is tracked separately.

## What is implemented

- English typing with letters, numbers, symbols, shift/caps, deletion, cursor arrows,
  Enter actions and an integrated **Mic** button.
- Local keyboard preferences: larger keys/labels, light/dark keys, optional vibration
  and repeat filtering, with a preview and reset. Repeat filtering is off by default;
  enabling it suppresses same-key taps within 250 ms, including fast double letters.
- Voice IME with explicit Speak, Stop, Insert, Discard, and return-to-keyboard actions.
- `ACTION_RECOGNIZE_SPEECH` activity for callers that request an activity result.
- Local English recognition using pinned whisper.cpp, ARM64 and x86_64 builds.
- Explicit import of the original `ggml-tiny.en.bin`, verified against SHA-256
  `921e4cf8686fdd993dcd081a5da5b6c365bfde1162e72b08d75ac75289920b1f`.
- No Internet permission, microphone foreground service, accessibility service,
  clipboard insertion, contacts access, analytics, backup, or saved audio history.
- Capture cancellation and preview clearing on field changes or panel dismissal;
  explicit speech insertion only. Password typing works in Utterleaf Keyboard;
  dictation is disabled there. The separate voice-only IME rejects password fields.
- 120-second capture bound and elapsed/remaining time; two-minute preview expiry
  with a 30-second warning and **Keep reviewing** to extend it.
- **Set up updates in Obtainium**, opening configuration in a separately installed
  Obtainium app. Utterleaf does not download or install updates itself.

## Try it

1. [Download and install Utterleaf Android alpha03](https://github.com/RioPlay/utterleaf/releases/download/android-v0.1.0-alpha03/Utterleaf-Android-0.1.0-alpha03.apk)
   on Android 8.0 or newer with a 64-bit ARM processor (ARM64).
   Use `Utterleaf-Android-0.1.0-alpha03.apk` from the [signed release](https://github.com/RioPlay/utterleaf/releases/tag/android-v0.1.0-alpha03).
   If alpha01/alpha02 is installed, its debug signer differs: uninstall it once,
   then install alpha03. Uninstalling removes the imported model and other app data.
2. Open **Utterleaf Voice**, tap **Enable Utterleaf Keyboard**, enable it in Android's
   settings, then use **Choose keyboard**. Choose **Utterleaf Keyboard** for typing;
   **Utterleaf Voice** is the separate voice-only option.
3. Open a text field and type. Use **Keyboard preferences and preview** in setup to
   change sizing, theme, vibration or repeat filtering. Reopen the keyboard to apply
   saved preferences. The preview does not enter or save text.
4. For optional dictation, return to setup. Use the confirmed browser link to download
   the 77.7 MB English model, or transfer it from another computer. Import through
   the document picker; allow about 156 MB free storage during import. Grant microphone
   permission. Typing does not require these speech-setup steps.
5. In a non-password field, tap **Mic**, then **Speak**, talk, **Stop**, review, and
   **Insert**. **Keep reviewing** extends the preview timeout; **Discard** clears it.
   **Back to keyboard** returns to typing in the integrated keyboard. In the separate
   voice-only IME, it returns to the previous input method where Android permits,
   otherwise opens the picker.
6. If you use Obtainium, open **Set up updates in Obtainium** and review its import
   configuration. See [update setup and signing identity](../../docs/mobile-obtainium.md).
   Actual device import and version-to-version Obtainium updates remain unverified.

<img src="../../docs/assets/screenshots/android-setup.png" width="300" alt="Alpha03 setup: enable and choose the typing keyboard, open preferences, configure Obtainium, and optionally import a speech model" />
<img src="../../docs/assets/screenshots/android-keyboard-preferences.png" width="300" alt="Actual keyboard preferences and typing-layout preview, with larger labels, light keys, vibration and repeat-filter controls" />

Actual alpha03 CI app on an API 35 emulator. These scrolling setup/preferences
screens contain no transcript; the layout is a preview, not an editor-delivery test.
IME windows protect input from screenshots.

A compatible keyboard can delegate its microphone action to an external provider.
FUTO's [compatibility notes](https://github.com/futo-org/voice-input/blob/master/README.md)
establish that this pattern exists for HeliBoard, FlorisBoard, AnySoftKeyboard and
others; **Utterleaf has not yet been verified with those keyboards on a phone**.
Gboard and Samsung Keyboard do not expose this third-party integration according
to those notes. Their mic buttons cannot be replaced by installing Utterleaf.
There is no `SpeechRecognizer`/`RecognitionService` implementation in this preview.

Speech-intent callers must use an activity result. PendingIntent result delivery,
hands-free/background invocation, and non-English requests are not supported.
The caller chooses its destination; unlike our IME, this route cannot inspect
whether the eventual destination is a password field.

## If Android says “App not installed”

Check the filename first. An earlier release download list included
`Utterleaf-Voice-0.1.0-alpha02-unsigned.apk`. That developer build cannot be
installed; download the signed APK linked above instead. Enabling unknown sources
does not make an unsigned APK installable. Alpha03 provides the installable APK,
checksums, signing information and a version manifest.

Alpha01/alpha02 used disposable debug certificates. Alpha03 starts the persistent
release-signing channel and requires a one-time reinstall from those old previews,
which removes the imported model. Later signed releases must keep the same signing
identity; an unexplained signature mismatch is not a normal update step.
If installation still fails, report the filename, Android version, phone model,
and whether a previous preview is installed. Do not disable device protections to
work around an unexplained installation failure.

## Privacy boundaries

Your browser or selected document provider may use the network when acquiring a
model; Utterleaf itself cannot open Internet sockets. Import stores a verified copy
under `noBackupFilesDir`. Backup and device transfer are disabled. Deleting the
copy does not delete the original file in Downloads.

Recordings stay in bounded memory. Capture ends before decoding begins. Cancel
requests abort decoding and suppress late results; model loading may still finish
before cleanup. Changing the editor clears the take instead of carrying it to the
next field. No surrounding editor text is requested. Sensitive voice windows block
screenshots; the setup screen contains no transcript. Memory cleanup is best effort,
not a forensic erasure guarantee. The receiving app can retain inserted text.

## Build and test

Requirements: JDK 17, Android SDK platform 36, NDK 28.0.13004108, CMake 3.22.1.
Set `ANDROID_HOME` to your SDK or create an untracked `local.properties`.
The checked-in Gradle wrapper verifies its distribution hash. Native dependencies
are fetched at build time from whisper.cpp commit
`2eeeba56e9edd762b4b38467bab96c2517163158` (v1.8.3); there is no runtime fetch.
The source archive is verified against SHA-256
`089b898aa83b24a8321e0fd554eeb0967fb03dd687e27f6374c72d3363b5b429`.

```sh
./gradlew testDebugUnitTest lintDebug assembleDebug assembleRelease
```

On Windows, use `gradlew.bat`. CI also downloads a hash-verified model and the
pinned upstream JFK speech fixture **into the test APK only**, then runs
`connectedDebugAndroidTest` on an API 35 emulator. The ordinary APK does not bundle
either fixture. CI verifies the packaged APK with Android's `apksigner` and installs
it on the emulator without test-only installation flags. Reports and APK checksums
accompany successful builds. `assembleRelease` also checks release compilation,
but its unsigned output stays in the build directory and is not distributed.

Alpha03's verified baseline is **4 JVM tests, 10 API 35 emulator tests and 3 Python
release-contract tests**. Coverage includes model verification and real local
inference, permission/backup restrictions, password filtering, stale voice-result
rejection, single insertion, capture cancellation, typing-panel behavior, keyboard
service protection and preferences rendering. The
[successful signing/publishing run](https://github.com/RioPlay/utterleaf/actions/runs/34425184566)
verified signed installation/reinstallation and published
[alpha03](https://github.com/RioPlay/utterleaf/releases/tag/android-v0.1.0-alpha03).
These tests do not establish complete live-IME behavior across real editors or
physical phones. See [validation limits](../../docs/mobile.md#android-validation--september-9-2026).

## Acceptance work before a stable mobile release

- Actual Pixel/GrapheneOS and other Android phones: mic permission denial/revocation,
  another recorder, Bluetooth, rotation, lock, incoming calls, interruptions, and
  keyboard switching. Never silently continue capturing after losing the panel.
- IME and speech-intent insertion in real editors; verify no stale result crosses
  fields and no text is duplicated after repeated Insert or delayed completion.
- TalkBack, Switch Access, external input, large fonts, landscape,
  gesture/three-button navigation, and small displays, with assistive-technology users.
- Cold inference latency, RAM, battery and thermal behavior on midrange ARM64 phones.
- Physical version-to-version signed installation and real Obtainium import/updates;
  independently protected offline signing-key backup. Signing and emulator
  installation/reinstallation have passed, but do not establish these device gates.
- Dependency provenance, native 16 KB page compatibility and distribution policy
  review. CI debug APKs remain development artifacts, separate from signed releases.
- Bounded incremental dictation, additional reviewed models/languages, local
  vocabulary and reviewed command behavior. The released keyboard foundation needs
  further editing/language features and security, accessibility and license acceptance.

There is no affiliation with FUTO or GrapheneOS. Their designs inform product
principles; the implementation uses Android APIs and whisper.cpp under the licenses
included in the APK.
