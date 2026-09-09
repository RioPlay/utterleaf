# Utterleaf Voice for Android

<img src="../../docs/assets/brand/utterling-listening.png" width="88" alt="Listening Utterling" />

An experimental, offline voice companion. Keep a compatible keyboard, or select
the compact Utterleaf voice panel through Android's keyboard switcher.
**0.1.0-alpha01 is a development preview, not a production keyboard replacement.**

## What is implemented

- Voice IME with explicit Speak, Stop, Insert, Discard, and return-to-keyboard actions.
- `ACTION_RECOGNIZE_SPEECH` activity for callers that request an activity result.
- Local English recognition using pinned whisper.cpp, ARM64 and x86_64 builds.
- Explicit import of the original `ggml-tiny.en.bin`, verified against SHA-256
  `921e4cf8686fdd993dcd081a5da5b6c365bfde1162e72b08d75ac75289920b1f`.
- No Internet permission, microphone foreground service, accessibility service,
  clipboard insertion, contacts access, analytics, backup, or saved audio history.
- Capture cancellation and preview clearing on field changes or panel dismissal;
  explicit insertion only. Password fields are blocked by the IME.
- 120-second capture bound and elapsed/remaining time; two-minute preview expiry.

## Try it

1. Install the **debug APK** from the [Android alpha release](https://github.com/RioPlay/utterleaf/releases/tag/android-v0.1.0-alpha01).
   Development builds and reports are also available from [Android CI](https://github.com/RioPlay/utterleaf/actions/workflows/android.yml).
   The unsigned release APK is for developers and cannot be installed until signed.
   CI debug certificates are disposable; a later preview may require uninstalling
   the old one, which removes the imported model. Stable release signing is pending.
2. Open **Utterleaf Voice**. Use the confirmed browser link to download the 77.7 MB
   English model, or transfer it from another computer. Import it through the
   document picker; allow about 156 MB of free storage during import.
3. Grant microphone permission, then enable **Utterleaf Voice** in keyboard settings.
4. Open a non-password text field and choose Utterleaf in the keyboard switcher.
   Tap **Speak**, talk, **Stop**, review, and **Insert**. **Back to keyboard** returns
   to the previous input method where Android permits it, otherwise opens the picker.

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
either fixture. Reports and APK checksums accompany successful builds.

## Acceptance work before a stable mobile release

- Actual Pixel/GrapheneOS and other Android phones: mic permission denial/revocation,
  another recorder, Bluetooth, rotation, lock, incoming calls, interruptions, and
  keyboard switching. Never silently continue capturing after losing the panel.
- IME and speech-intent insertion in real editors; verify no stale result crosses
  fields and no text is duplicated after repeated Insert or delayed completion.
- TalkBack, large fonts, landscape, gesture/three-button navigation, and small displays.
- Cold inference latency, RAM, battery and thermal behavior on midrange ARM64 phones.
- Stable signing, dependency provenance, native 16 KB page compatibility, and
  distribution policy review. Debug APKs are for testing, not store publication.
- Bounded incremental dictation, additional reviewed models/languages, local
  vocabulary and shared desktop command behavior. No full QWERTY keyboard is planned
  until evidence shows the companion approach is insufficient.

There is no affiliation with FUTO or GrapheneOS. Their designs inform product
principles; the implementation uses Android APIs and whisper.cpp under the licenses
included in the APK.
