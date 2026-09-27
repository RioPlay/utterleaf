# Utterleaf for Android

<img src="../../docs/assets/brand/utterling-listening.png" width="88" alt="Listening Utterling" />

An experimental English typing keyboard with integrated offline dictation.
**0.1.0-alpha21 is the current signed preview.**
The alpha21 ordinary surface uses one compact daily row for Tools, Edit, three
stable suggestion positions and Dictate. Secondary editing, Emoji, Private Draft
and specialist controls appear only when requested. Its continuous bottom row is
?123, comma, Space, period and the dynamic action key. System,
Light, Dark, and true-black OLED themes now
apply across the keyboard, Settings, setup, emoji, private draft, and voice review.
A grouped Accessory/F-key strip keeps specialist controls to one row and preserves
held modifier-arrow chords when opened from Tools. The complete additional-symbol
set is split across readable rows instead of being compressed into one line.
An optional **Split keyboard in landscape** layout adds a non-interactive center
channel across number, letter, symbol, and dual-Space rows. It falls back to the
standard layout in portrait; choosing Left or Right hand alignment turns split
off so the modes never conflict.
A mic tap keeps the transcript review-and-correct flow; direct insertion remains an
explicit hold option. The mic and Voice surface use official Utterling states with
visible labels for availability, listening, local processing, transcript review,
editing, and problems. [Release evidence and phone QA](../../docs/mobile-roadmap.md#current-status).
It retains F1–F12, the hinted number row, the redesigned Settings screen, a
password-manager shortcut restricted to password fields, and a suggestion strip
that completes the word you are typing from a public-domain English list. See the
[daily redesign plan](../../docs/plans/completed/android-keyboard-daily-redesign.md),
the [community wants harvest](../../docs/mobile-keyboard-community-wants-2026-09.md)
and the [suggestions slice plan](../../docs/plans/completed/android-suggestions-slice.md).

Fields Android identifies as passwords use a minimal sensitive-input surface:
typing, symbols and held-letter accents, manual Shift/Caps, Backspace, the field's
action key, explicit Paste, keyboard switching and the configured password-manager
shortcut. Tools, editing layers, emoji browsing, suggestions, draft and dictation
are absent. Cursor/selection gestures are refused without inspecting host text.
Automatic capitalization and repeat filtering are bypassed there so password
entry stays literal and no last-key cache retains a typed character; saved
preferences are unchanged. Paste dispatches one host action without reading the
clipboard in the keyboard. Leaving an input session disposes its panel and clears
transient state. These protections depend on accurate editor metadata; they do not
identify every potentially sensitive field. Current evidence and lifecycle limits
are recorded in the [capability plan](../../docs/plans/active/android-experience-refresh.md).

Detaching and reattaching the same typing panel now returns it to its field's
letter or numeric baseline: Tools, editing/Fn layers, Caps/modifiers, compose,
alternates and pending gestures/repeats reset. Old controls cannot re-arm Caps or
type into the rebuilt surface. Explicit preferences and the owning local editor's
text are not reset by this panel boundary; private-draft clearing remains the
draft owner's responsibility.

Alpha15 preserves alpha14's two-thumb rollover, letter layouts, one-hand
alignment, local emoji, Latin composition, private drafts and visible
long-press hint default. See the [completed compact-layer contract](../../docs/plans/completed/android-compact-layers.md).

Alpha12 introduced **Edit**, which opens Undo, Redo, Select all, Cut, Copy, Paste and
navigation in a panel that replaces the letters. **ABC** returns to typing.
[Validation and editor limits](../../docs/android-quick-actions.md).

New in alpha13: tuning sliders include their current value in
accessible descriptions, and quick toggles refresh other saved preferences.
Revision `d942098` passed 76 emulator tests, 8 JVM tests, lint, builds and release
contracts in [Android CI](https://github.com/RioPlay/utterleaf/actions/runs/34513111803).
Physical-device and TalkBack acceptance remain open. See the [design notes](../../docs/android-keyboard-design.md#released-in-alpha13).

Alpha11 added the single-row toolbar with **123** (number row),
**>_** (terminal controls) and the Dictate icon. Quick toggles save
locally and stay synchronized with the Settings preview. Voice review supports
**Expand transcript**, scrolling, selection and **Edit transcript**; recording
preferences hide while reviewing. These changes passed 71 emulator tests;
physical-device and accessibility acceptance remain open. See
[alpha11 validation and screenshots](../../docs/android-keyboard-design.md#released-in-alpha11).

Typing works without microphone permission or a speech
model. A separate voice-only option remains available for compatible keyboards.

Alpha10 adds held Ctrl/Alt shortcuts in Terminal controls, independently configurable
delete repetition, and switching between retained model imports. See
[release validation and limits](../../docs/android-keyboard-design.md#released-in-alpha10).

Alpha09 adds Shift-space selection, held deletion, period-key punctuation,
independent height/bottom spacing and private layout practice. The voice panel
offers one primary control, local transcript editing and optional hold-to-insert.
[Validation and current limits](../../docs/android-keyboard-design.md#released-in-alpha09).

This is the foundation for a complete customizable keyboard. Broader language,
prediction, accessibility and device coverage remain on the
[mobile roadmap](../../docs/mobile-roadmap.md). Desktop development is tracked separately.

## Alpha07

- Visible secondary symbols on letters; hide hints in preferences if desired.
- Hold a letter, slide to a highlighted accent/symbol and release to insert.
  Slide away to cancel, or use **Tools → Accents → letter** for a tap-only route.
  Slide the spacebar horizontally to move the cursor; tap to insert a space.
  Cancel inserts nothing; Shift/Caps affect the choices. Old picker callbacks cannot
  insert into a later field. Adjustable hold timing and full language support remain planned.

- Staggered English letter rows, a wide spacebar, direct punctuation, symbols,
  deletion, Enter actions and integrated **Voice** and **Tools** controls.
- Shift/Caps handling carries forward the alpha04 fix: letters follow the displayed case, one-shot
  Shift clears after successful entry, and Shift reverses Caps Lock for one letter.
- Local keyboard preferences: larger keys/labels, light/dark keys, optional vibration
  and repeat filtering, with a preview and reset. Optional number-row and terminal
  preferences are independent. Terminal controls include Esc, Tab, one-shot Ctrl/Alt,
  four arrows, Home/End and Page Up/Down. Fn replaces letters with F1–F12, Insert
  and forward Delete, keeping panel height stable. Actual shortcut behavior
  depends on the receiving editor; broad terminal compatibility is unverified.
  Repeat filtering is off by default;
  enabling it suppresses same-key taps within 250 ms, including fast double letters.
- Voice IME with explicit Speak, Stop, Insert, Discard, and return-to-keyboard actions.
- `ACTION_RECOGNIZE_SPEECH` activity for callers that request an activity result.
- Local English recognition using pinned whisper.cpp, ARM64 and x86_64 builds.
- A guided setup with real keyboard enabled/selected status and separate optional
  voice readiness. Choose one of three reviewed [English speech models](#english-speech-models)
  and use **Import a model**. Import identifies any supported file by exact size and
  SHA-256 independently of the browser download selector.
- No Internet permission, microphone foreground service, accessibility service,
  automatic clipboard writes, contacts access, analytics, backup, or saved audio history.
- Capture cancellation and preview clearing on field changes or panel dismissal;
  explicit speech insertion only. Password typing works in Utterleaf;
  dictation is disabled there. The separate voice-only IME rejects password fields.
- 120-second capture bound and elapsed/remaining time; two-minute preview expiry
  with a 30-second warning and **Keep reviewing** to extend it.
- **Set up updates in Obtainium**, opening configuration in a separately installed
  Obtainium app. Utterleaf does not download or install updates itself.

## Try it

1. Choose an Android APK from a [published signed preview](https://github.com/RioPlay/utterleaf/releases)
   for Android 8.0 or newer with a 64-bit ARM processor (ARM64).
   Alpha21 is the current published preview. Development revisions built locally
   remain unsigned test candidates, not release downloads.
   If alpha01/alpha02 is installed, its debug signer differs: uninstall it once,
   then install the signed preview. Uninstalling removes the imported model and other app data.
   Alpha03 began the persistent signing channel; an installed signed alpha03 uses
   the same release identity and should be updated in place rather than uninstalled.
2. Open **Utterleaf**. Under **Your keyboard**, enable **Utterleaf**
   in Android settings, then choose it. Setup reports which step is still needed.
   You do not need to enable the separate **Utterleaf dictation** input method to use
   the typing keyboard's dictation button.
   Alpha18 keeps the installed package and update identity unchanged.
3. Open a text field and type. Use **Keyboard preferences and preview** in setup to
   change sizing, theme, number row, terminal controls, vibration or repeat filtering. Reopen the keyboard to apply
   saved preferences. The private practice field lets you try the layout without
   entering text into another app; it clears when you leave settings.
   In alpha18, **Apply** stays visible while you scroll;
   controls come before the practice preview. All changes, including voice,
   preview quick controls and Reset, wait for Apply. **Cancel** discards them.
   Theme/layout choices update the preview immediately. Rotating Settings keeps
   pending preferences in memory, while practice text is cleared.
   In alpha20 and later, **Customized** marks values that differ from defaults,
   not merely unsaved edits. Individual **Reset** and **Reset category** actions
   also wait for Apply; Cancel discards them. They leave unrelated settings and
   installed models untouched. Search accepts terms such as `reset number row`.
4. For optional dictation, open **Optional · offline voice** in setup. Choose a model
   below, open its download in your browser, then return and **Import** that file.
   Allow microphone permission. The voice status shows what is still missing;
   granting permission does not start recording.
5. In a non-password field, tap **Dictate** (the voice icon) to start, talk, **Stop**, review, and
   **Insert**. Use **Edit transcript** to correct locally before insertion.
   Speak/Stop/Insert share one primary control. From the idle panel, optionally
   enable **Hold to speak and insert on release**; hold until recording starts,
   speak and release. It inserts after recognition; moving outside cancels.
   The separate voice provider still starts with **Speak**.
   **Keep reviewing** appears near expiry to extend the timeout; **Discard** clears it.
   **Back to keyboard** returns to typing in the integrated keyboard. In the separate
   voice-only IME, it returns to the previous input method where Android permits,
   otherwise opens the picker.
6. If you use Obtainium, open **Set up updates in Obtainium** and review its import
   configuration. See [update setup and signing identity](../../docs/mobile-obtainium.md).
   Actual device import and version-to-version Obtainium updates remain unverified.

## Backspace hold and swipe

With **Hold Backspace or Delete to repeat** enabled and **Ignore repeated taps on the same key within 250 ms**
off, holding Backspace repeats after the system long-press delay. Alpha19
fixes repeat after capitalization and allows a later left swipe to take over:
repeat stops, the editor previews a selection, and release deletes that selection
once. Sliding back shrinks it; cancellation does not undo text already deleted by
the hold.

Password/raw fields and Extra keys refuse swipe selection. Editors must confirm
the selection before deletion; an unsupported or uncertain gesture fails closed.
Explicit Extra keys modifiers keep their separate behavior. See the
[follow-up contract](../../docs/plans/completed/android-backspace-hold-swipe.md).

## English speech models

Keep multiple imported models and change the active one in setup with **Use
Compact English**, **Use Medium English** or **Use Large English**. Their rows show
**Active**, **Installed**, **Not verified** or **Not installed**. In an idle voice panel, the **Model** control
offers the installed choices when there is more than one. Switching is allowed
between takes, not during recording, processing or import.

Alpha20 and later present **Compact English** (77.7 MB, lowest resource use),
**Medium English** (148.0 MB, moderate resource use), and **Large English**
(487.6 MB, highest resource use). These names do not promise accuracy or measured
phone speed. **Show technical model details** reveals the stable identifier, original
filename, GGML format, exact size, checksum and private-storage description.
Opening or closing details does not import, switch models or request microphone
access. **Delete selected model** removes only that import. If you delete the
active model, select another installed model before dictating again.

Compact English uses tiny.en, Medium English uses base.en, and Large English uses
small.en; the accepted file identities and existing selections are unchanged.
Compact English has the smallest download. Larger models require more RAM and
processing time; accuracy and speed depend on your phone and speech. The native
engine currently uses English for all three choices. These are reviewed file
identities, not a claim of equal testing or measured phone performance.

| Browser download | Exact bytes | SHA-256 |
| --- | ---: | --- |
| [tiny.en · 77.7 MB](https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-tiny.en.bin) | 77,704,715 | `921e4cf8686fdd993dcd081a5da5b6c365bfde1162e72b08d75ac75289920b1f` |
| [base.en · 148.0 MB](https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.en.bin) | 147,964,211 | `a03779c86df3323075f5e796cb2ce5029f00ec8869eee3fdfb897afe36c6d002` |
| [small.en · 487.6 MB](https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-small.en.bin) | 487,614,201 | `c6138d6d58ecc8322097e0f987c32f1be8bb0a18532a3f88f734d1bbf9c41e5d` |

Sizes and hashes were checked against the publisher's Git LFS metadata for
[tiny.en](https://huggingface.co/ggerganov/whisper.cpp/raw/main/ggml-tiny.en.bin),
[base.en](https://huggingface.co/ggerganov/whisper.cpp/raw/main/ggml-base.en.bin) and
[small.en](https://huggingface.co/ggerganov/whisper.cpp/raw/main/ggml-small.en.bin).
Use these original files; other languages, quantizations and arbitrary models are
not accepted. A computer-to-phone file transfer also works.

Allow roughly twice the download size in free storage for the browser's copy and
the verified import: about **156 MB**, **296 MB** or **976 MB** respectively. One
model is active at a time; retained imports use additional storage. Selecting a row
changes the browser link; **Use** switches to that installed model. New imports
become active only after verification succeeds. Failed verification,
an interrupted read or a failed replacement keeps the previous file. Existing
verified tiny.en installations remain usable after upgrading. Deleting the imported
model leaves typing available and does not delete your browser's copy in Downloads.

Tiny.en and base.en both completed real local JFK fixture inference in
[alpha05 CI run 34432378047](https://github.com/RioPlay/utterleaf/actions/runs/34432378047). **Small.en inference is
not yet verified.** Memory, latency, battery and thermal behavior need measurements
on real phones before recommending a larger model for a particular device.

## Screenshots and optional voice integration

[Alpha07 validation](../../docs/android-keyboard-design.md#released-in-alpha07)
records 8 JVM, 44 emulator and 3 release-contract tests plus signed installation checks.

<img src="../../docs/assets/screenshots/android-setup.png" width="300" alt="Alpha07 setup showing separate keyboard activation and optional English voice readiness" />
<img src="../../docs/assets/screenshots/android-keyboard-live.png" width="300" alt="Alpha07 keyboard in a synthetic editor with staggered letters, wide spacebar and Voice control" />
<img src="../../docs/assets/screenshots/android-keyboard-accents.png" width="300" alt="Alpha07 common Latin accents with visible Cancel action" />

Actual alpha07 ee47aa7 on the API 35 CI emulator. The setup page scrolls;
the live keyboard is in a synthetic editor, with no personal text or recording.
Status and navigation bars no longer overlap the controls in these captures.
Instrumentation temporarily allows the debug screenshot and restores the secure
flag; release IME windows remain protected. Physical accessibility is still open.

Use **Advanced · voice with another keyboard** only if you want the separate
voice-only provider. A compatible keyboard can delegate its microphone action to it.
The upstream [compatibility notes](https://github.com/futo-org/voice-input/blob/master/README.md)
document this integration pattern for several Android keyboards; **Utterleaf has
not yet been verified with external keyboards on a phone**. Some stock keyboards
do not expose this third-party integration, so installing Utterleaf cannot replace
their microphone button.
There is no `SpeechRecognizer`/`RecognitionService` implementation in this preview.

Speech-intent callers must use an activity result. PendingIntent result delivery,
hands-free/background invocation, and non-English requests are not supported.
The caller chooses its destination; unlike our IME, this route cannot inspect
whether the eventual destination is a password field.

## If Android says “App not installed”

Check the filename first. An earlier release download list included
`Utterleaf-Voice-0.1.0-alpha02-unsigned.apk`. That developer build cannot be
installed; download the signed APK linked above instead. Enabling unknown sources
does not make an unsigned APK installable. Alpha05 provides the installable APK,
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

On Windows, use `gradlew.bat`. CI downloads hash-verified tiny.en/base.en models and the
pinned upstream JFK speech fixture **into the test APK only**, then runs
`connectedDebugAndroidTest` on an API 35 emulator. The ordinary APK does not bundle
either fixture. CI verifies the packaged APK with Android's `apksigner` and installs
it on the emulator without test-only installation flags. Reports and APK checksums
accompany successful builds. `assembleRelease` also checks release compilation,
but its unsigned output stays in the build directory and is not distributed.

Alpha05 **f74b862 passed 4 JVM, 32 API 35 emulator and 3 Python
release-contract tests** in [CI run 34432378047](https://github.com/RioPlay/utterleaf/actions/runs/34432378047).
The emulator report has **zero failures and zero skips**. Additional coverage includes
selected-model bounds/rollback, catalog identification, setup choices, real tiny.en
and base.en inference, system-bar bounds, terminal dispatch, one-shot modifiers,
the optional number row and replacing Fn layer. Controlled editor connections
validate key-event contracts; real-terminal behavior and physical accessibility
remain separate acceptance work. Small.en inference remains unverified.

The [successful alpha05 signing/publishing run](https://github.com/RioPlay/utterleaf/actions/runs/34432995380)
verified the stable certificate, upgraded signed alpha03 to alpha05 on an emulator,
reinstalled the same alpha05 version and launched setup. Preference and imported-model
retention were not tested. Physical updates and real Obtainium acceptance remain open.

The historical alpha04 baseline passed **4 JVM tests, 11 API 35 emulator tests and 3 Python release-contract
tests** in the [verified CI run](https://github.com/RioPlay/utterleaf/actions/runs/34427672686).
Coverage includes model verification and real local
inference, permission/backup restrictions, password filtering, stale voice-result
rejection, single insertion, capture cancellation, typing-panel behavior, keyboard
service protection and preferences rendering. The added live-IME test drives letter
entry, cursor movement, deletion, Done, a voice-panel-to-password transition and
hide/reopen in an emulator test activity; it starts no microphone capture. A separate
direct typing-panel button test verifies Shift/Caps. Selected-text replacement and
compatibility across real editors, phones and assistive technologies remain open.

The [successful alpha04 signing/publishing run](https://github.com/RioPlay/utterleaf/actions/runs/34428171272)
verified the release signature, upgraded signed alpha03 to alpha04 on an emulator,
and reinstalled the same alpha04 version. The signing certificate is unchanged.
Preference and imported-model preservation were not exercised; physical updates
and real Obtainium acceptance remain open. See [validation limits](../../docs/mobile.md#android-validation--september-9-2026).

## Acceptance work before a stable mobile release

### Independent lifecycle host

The opt-in `lifecycleHost` module is a disposable, test-only application in a
separate process. Its instrumentation survives killing the exact verified debug
IME PID and exercises a real second-package editor transition. It is excluded
from ordinary builds and cannot produce a release variant. Only the debug product
manifest exposes its synthetic editor, guarded by a signature permission shared
with the fixture; release components and permissions are unchanged.

Run on a disposable API 35 emulator from this directory:

```powershell
.\gradlew.bat -PincludeLifecycleHost=true :app:installDebug :lifecycleHost:connectedDebugAndroidTest :lifecycleHost:lintDebug --no-daemon
```

The host's connected-debug task explicitly depends on product installation;
command-line task order alone is not an ordering guarantee with parallel Gradle
projects. Run this fixture separately from the ordinary app instrumentation suite
on the same emulator. Its prerequisite also works from an absent test installation.

The driver restores selected/enabled input methods, preserves the independent
host's text and selection, and never records audio or force-stops other apps.
Its claims are limited to the two owned synthetic packages, not third-party
compatibility. The ordinary app suite separately exercises auxiliary voice
hide/reopen and real `uinput` external-keyboard add/remove with explicit soft-keyboard
hide/reopen. The emulator already has an internal alphabetic keyboard, so this
does not establish a no-hardware-to-hardware configuration transition or physical
USB/Bluetooth behavior. No test should substitute injected keypresses for an
observed device-add/remove event.

### Isolated performance observations

The ordinary instrumentation run excludes `KeyboardPerformanceTest`. Run it
separately on a disposable API 35 emulator launched with `-no-audio`, with the
same checksum-verified model and JFK test assets used by CI:

```powershell
.\gradlew.bat connectedDebugAndroidTest -PutterleafPerformance=true --no-daemon
```

This measures synthetic typing, first-draw feedback, candidate work, Tools,
capture startup, local fixture decoding, memory and sustained frame behavior.
The result-insertion metric is explicitly a local `EditText` callback proxy,
not host `InputConnection` or physical display latency. Capture startup uses
the emulator's disabled audio input, not a microphone or user speech. No
production logging, telemetry, model downloads or performance thresholds are
introduced. The fixture restores preferences, selected/enabled keyboards,
temporary permission identity and model state, preserving the original failure.

Archive the raw connected-test output before another run replaces it. Parse the
single test's `logcat-org.utterleaf.voice.KeyboardPerformanceTest-recordApi35EmulatorBaseline.txt`
with `tools/android_performance.py`. Supply `--input`, `--output`, `--apk`, `--repo`,
`--adb`, `--serial` and `--command`; the latter records the actual emulator launch
and Gradle commands (including `-no-audio` and `-PutterleafPerformance=true`). The
parser rejects incomplete measurement/cleanup records and missing provenance,
and writes raw JSONL, metadata, summaries, median and nearest-rank p95. Run its
tests with `python -m unittest discover -s tools -p test_*.py`.

Compare only matched environments/options/model identities. First versus later
decode samples describe order and cache conditions, not a retained native model.
Emulator observations do not establish phone responsiveness, heat, battery,
physical touch comfort or live third-party compatibility. Record accepted runs
and limitations in the [compatibility evidence](../../docs/android-keyboard-compatibility.md).

### Remaining device acceptance

- Actual Pixel/GrapheneOS and other Android phones: mic permission denial/revocation,
  another recorder, Bluetooth, rotation, lock, incoming calls, interruptions, and
  keyboard switching. Never silently continue capturing after losing the panel.
- IME and speech-intent insertion in real editors; verify no stale result crosses
  fields and no text is duplicated after repeated Insert or delayed completion.
- TalkBack, Switch Access, external input, large fonts, landscape,
  gesture/three-button navigation, and small displays, with assistive-technology users.
- Cold inference latency, RAM, battery and thermal behavior on midrange ARM64 phones.
- Physical version-to-version signed installation and real Obtainium import/updates;
  independently protected offline signing-key backup. Alpha03-to-alpha04 upgrade
  and same-version reinstallation passed on an emulator; preference/model
  preservation and these physical-device gates still need verification.
- Dependency provenance, native 16 KB page compatibility and distribution policy
  review. CI debug APKs remain development artifacts, separate from signed releases.
- Bounded incremental dictation, physical validation of larger English models,
  additional reviewed languages, local
  vocabulary and reviewed command behavior. The released keyboard foundation needs
  further editing/language features and security, accessibility and license acceptance.

The implementation uses Android APIs and whisper.cpp under the licenses included
in the APK; it has no affiliation with external keyboard or operating-system
projects.
