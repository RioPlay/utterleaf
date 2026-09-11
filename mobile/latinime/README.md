# Utterleaf LatinIME foundation work

Execution update: Ernest has approved implementation, testing and shipment, and
has requested Kotlin as the target for the Android port. Earlier local-only and
approval-pending notes below are historical planning context, superseded by that
instruction. Publication still requires honest verification and license compliance.
The experimental build is now under `app/`; it is not yet the replacement product.
A signed [preview01 test APK](https://github.com/RioPlay/utterleaf/releases/tag/android-foundation-v0.1.0-preview01)
is available alongside alpha13, under a separate application ID and signing identity.
It provides basic typing and comfort settings; voice, correction and swipe are unfinished.
The latest local corrections guard delayed suggestion results across editor sessions
and make height/theme changes take effect during same-field practice. Suggestion
workers now use owner-captured composer/context inputs and deep pointer copies;
dictionary loads reject retired generations and stale UI notifications. Native
dictionary/proximity leases defer disposal until admitted operations finish without
blocking the UI on decoding. Owner-checked service/view cleanup releases retired
pointer state and timers while preserving successor state and verified view reuse.
Cached keyboard layouts now keep immutable keyboard-only editor metadata.
Remaining native hardening and lifecycle/cache checks
continue; the external emulator probe verifies only bounded process-death behavior. See the
[execution evidence](EXECUTION-EVIDENCE.md) for verified paths and remaining limits.
The linked AOSP gesture policy is absent: native swipe recognition is not implemented
in this experiment. Gesture cancellation/input-isolation tests do not prove swipe.
See [Kotlin migration](KOTLIN-MIGRATION.md) for the conversion policy.

Start with the [implementation plan](IMPLEMENTATION-PLAN.md) for the proposed
work packages, UI/defaults, ownership, dependencies and approval/acceptance gates.
It is the canonical plan for the complete agreed hybrid.

Status: the isolated foundation debug APK built locally on September 10, 2026.
It is not yet the replacement keyboard; preview01 is an experimental prerelease. This standalone
Gradle project remains separate from the shipping `mobile/android` app and desktop.
Implementation, testing and shipment have been authorized; compliance and release
verification remain required. The [community research](COMMUNITY-RESEARCH.md)
records priorities, tradeoffs and acceptance checks.

Local build evidence: `gradlew.bat -p mobile/latinime --no-daemon :app:assembleDebug`
passed with JDK 17, Gradle 8.13, SDK 36 and NDK 28.0.13004108, including ARM64 and
x86-64 native compilation. Resource namespaces were adapted for the experimental
application ID, and AndroidX Core 1.16.0 supplies the inherited accessibility API.
JVM tests, API 35 emulator tests, lint and unsigned release assembly now also pass.
See [execution evidence](EXECUTION-EVIDENCE.md) for the scope and remaining gates.
Lint warnings, physical-phone usability, dictionary licensing and release acceptance
remain open; this is not the replacement product.

Use Aden for scoped symbol trees, exact searches and caller inspection before
changes; validate results against source and tests. Framework and JNI entry points
must not be treated as unused because the graph finds no callers.

Where comfort and interaction preferences differ, provide explicit local choices
with sane defaults, practice and reset. The research includes a preference matrix;
security and privacy guarantees apply to every combination.

The [adversarial plan review](ADVERSARIAL-PLAN-REVIEW.md) reconciles independent
security, usability and feasibility challenges into staged approval/build gates.
Its full-IME feasibility milestone refines the initial build proposal below.

The [baseline checklist](PARITY-CHECKLIST.md) defines the current product:
LatinIME foundation, FUTO-inspired comfort/refinements, Hacker's Keyboard-style
power controls and Utterleaf's own local voice engine. All four belong to the
intended replacement. Separate engineering gates do not demote power/voice
integration, swipe or language targets to silently omitted extras.

## Source and reproduction

Upstream: <https://android.googlesource.com/platform/packages/inputmethods/LatinIME>

Pinned revision: `127336e9f29d69607eab55982324b210279ae8c5`.

From a development directory, create a separate checkout:

```powershell
git clone --no-checkout https://android.googlesource.com/platform/packages/inputmethods/LatinIME utterleaf-latinime-upstream
git -C utterleaf-latinime-upstream remote rename origin upstream
git -C utterleaf-latinime-upstream switch -c utterleaf/android-base 127336e9f29d69607eab55982324b210279ae8c5
git -C utterleaf-latinime-upstream rev-parse HEAD
```

The local checkout and branch have been created. No GitHub fork has been published.
The experiment includes an internal, local **Licenses and notices** viewer. The build
verifies staged document hashes and refreshes the original upstream notices, including
Utterleaf's current modification record, into generated assets. The
[dependency inventory](DEPENDENCY-INVENTORY.md) records the reviewed scope and remaining
attribution gaps; packaged notices alone do not establish release compliance.

Preserve upstream history and notices. Do not put the upstream binary dictionaries
into Utterleaf's release assets: the root `NOTICE` includes a separate Lexiteria
permission statement. Asset-by-asset redistribution review remains open.

## Verified build blockers

At this revision, `build.gradle` uses AGP `3.2.0-beta03`, SDK 28, JCenter,
a dynamic AndroidX version and a shared debug keystore. Its native build points to
`native/jni/Android.mk`, which is absent. The supported platform definitions are
Soong `Android.bp` files. Running the old wrapper is not a standalone port.

Implemented in this experiment: a separate public-SDK Gradle/CMake build with pinned
dependencies, its own experimental application ID and ordinary local debug
signing. Do not reuse the upstream shared key or Utterleaf's release key for the
experiment. Establish compilation before connecting voice or replacing the IME.

## Security and privacy are adoption gates

Security first, privacy second, convenience third. Neither upstream maturity nor
an open-source license proves these properties. The following are requirements
for the port, **not claims about the unmodified checkout**:

- Core keyboard has no network, contacts, accounts, sync, credentials, external
  storage or boot permissions. Inspect the final merged APK manifest, including
  dependencies; removing declarations alone does not establish safe data flow.
- Remove dictionary download/update components and contact/cloud integrations.
  Review indirect paths through other apps/providers as well as direct networking.
- No passive typing collection, clipboard monitoring/history, telemetry or raw
  input/audio logging. Explicit local dictionary entries remain separate from
  automatic learning. Disable app backup of sensitive local data.
- Preserve sensitive-field behavior, secure windows, session-generation checks,
  cancellation and stale-action rejection across focus changes. Microphone use
  requires an explicit voice action; no ambient capture.
- Dictionary/model loading must be bounded, provenance-checked and atomic. Audit
  native parsers and their failure paths before accepting external assets.
- Keep terminal modifiers, gestures and local speech behind tested adapters.
  Reset settings must preserve models and other user data.

The upstream manifest currently requests contact/profile, account/sync,
user-dictionary, download, boot and storage permissions and enables backup. It
registers dictionary services, download/update receivers and a dictionary provider.
These paths require source removal or replacement, not hidden settings toggles.

## Requested experience and requirements

The requested interaction reference is FUTO's familiar, compact keyboard, using
Utterleaf's own branding and assets. The supplied screenshots inform the target:
staggered rows, comfortable touch targets, a broad spacebar, visible secondary
characters, hold-slide-release alternatives and a compact suggestion/action area.
Keep microphone access reachable with one hand. Editing and terminal controls
must be readily available without permanently crowding everyday typing. Preserve
adjustable height/bottom spacing and a practice field with reset. These are design
targets, not features established by cloning LatinIME or permission to import
another project's code or assets. Usability must be tested on the resulting port.

Preserve these user requests during the foundation change; this list records
requirements, not a claim that the fork implements them:

- Everyday typing: reliable overlapping two-thumb input, local correction and
  suggestions, explicit personal dictionary management, visible secondary keys,
  hold-slide-release accents and quick punctuation from the period key.
- Editing: spacebar cursor movement, held Shift plus spacebar selection,
  backspace repetition and drag-selection feedback before deletion, forward
  Delete, and reachable undo, redo, select, cut, copy and paste actions. Clipboard
  actions are explicit operations, never background monitoring or history.
- Terminal use: accessible Ctrl/Alt/Shift and other supported modifiers, Esc, Tab,
  arrows, navigation and function keys. Held modifier combinations must work
  consistently without clashes with typing or destructive gestures. Document
  editor-dependent limitations and test real terminal applications.
- Voice: a reachable Utterleaf microphone icon, recording on explicit mic
  activation, optional hold-to-speak/release-to-insert, and an expandable editable
  transcript review. Keep stop, cancel and insert understandable and reachable
  with one hand. Speech-pause auto-submit remains an optional idea requiring
  separate accidental-submission and cancellation validation.
- Setup and models: clear missing-model detection, a general Import model action,
  verified model choices with clear download guidance, and switching between
  installed models between takes. Explain speed/accuracy and hardware constraints
  honestly; phone GPU/NPU acceleration is an investigation, not a guarantee.
- Customization: sane local defaults, compact quick settings, adjustable keyboard
  height and bottom padding, optional utility rows, accessible gesture alternatives
  and a practice editor. Preferences must persist predictably, cancel cleanly and
  reset without deleting user models or dictionary data.
- Presentation: a polished, comfortable everyday layout with Utterleaf branding;
  useful features appear where needed instead of permanently adding rows. External
  keyboards are internal research references, not marketing identity. Preserve
  required legal attribution separately from product copy.

Security and privacy above take precedence over every convenience request.
Autocorrection and suggestions must not introduce passive collection or implicit
learning. Accessibility, responsiveness, lifecycle correctness and real-device
usability are acceptance criteria throughout development, not a final polish step.

## Validation before migration

1. Build the standalone experiment with pinned Java/native dependencies and a
   reviewed source, asset and license inventory.
2. Enforce a permission/component allowlist on the built APK and exercise
   sensitive-field, recording, persistence and cancellation behavior.
3. Run matched editor/terminal, composition, multitouch, accent, deletion and
   accessibility regressions against the current keyboard. Verify stale controls
   cannot cross editor sessions.
4. Measure startup, touch latency and memory; perform real-phone and TalkBack
   checks. Emulator passes cannot establish physical usability.
5. Only then migrate the shipping app with upgrade/model preservation tests.

The local toolchain is now installed and the standalone project builds and runs.
Current results and limitations are recorded in [execution evidence](EXECUTION-EVIDENCE.md).
Remote CI and physical-device acceptance remain separate gates.

The synthetic abrupt-process-death probe runs separately from the normal Gradle
suite. Use only the disposable emulator: it terminates the experimental app process,
checks the cold launch, then restores its saved preference map. Build both debug APKs
first; connected tests may uninstall them, so install them again before this command:

```powershell
$adb = 'C:/Users/unknown/AppData/Local/UtterleafBuild/sdk/platform-tools/adb.exe'
& $adb -s emulator-5554 install -r mobile/latinime/app/build/outputs/apk/debug/app-debug.apk
& $adb -s emulator-5554 install -r mobile/latinime/app/build/outputs/apk/androidTest/debug/app-debug-androidTest.apk
& C:/Users/unknown/Projects/Mindict/.venv/Scripts/python.exe mobile/latinime/tools/process_death_probe.py `
  --adb $adb --serial emulator-5554 --logs C:/Users/unknown/AppData/Local/UtterleafBuild/process-death-probe
```

Keep failed-run evidence and its token-owned preference backup for recovery; do not
clear application data. This probe does not test real framework IME recovery or
Android saved-task restoration. Its precise scope is recorded in execution evidence.
See the [foundation review](../../docs/android-keyboard-foundation-decision.md)
for the source references and remaining decisions.

A separate probe now tests actual IME process death while a synthetic editor in
another process survives. Its debug-only host has no release variant and is excluded
unless explicitly enabled. Build and install all three test APKs, then run:

```powershell
./mobile/latinime/gradlew.bat -p mobile/latinime --no-daemon '-PincludeRecoveryHost=true' `
  :app:assembleDebug :app:assembleDebugAndroidTest :recoveryHost:assembleDebug
$adb = 'C:/Users/unknown/AppData/Local/UtterleafBuild/sdk/platform-tools/adb.exe'
& $adb -s emulator-5554 install -r -t mobile/latinime/app/build/outputs/apk/debug/app-debug.apk
& $adb -s emulator-5554 install -r -t mobile/latinime/app/build/outputs/apk/androidTest/debug/app-debug-androidTest.apk
& $adb -s emulator-5554 install -r -t mobile/latinime/recoveryHost/build/outputs/apk/debug/recoveryHost-debug.apk
& C:/Users/unknown/Projects/Mindict/.venv/Scripts/python.exe mobile/latinime/tools/ime_process_recovery_probe.py `
  --adb $adb --serial emulator-5554 --logs C:/Users/unknown/AppData/Local/UtterleafBuild/ime-process-recovery
```

The controller verifies emulator/UID/PID identity before killing only the keyboard
process. It injects measured keyboard touches before and after recovery, and checks
that host process/activity, text and geometry survive. It restores the previous
enabled/default IME and animation settings, then removes only its token-owned files.
The API 35 run passed **after one same-field user re-show**; automatic keyboard
reappearance was not established. This probe does not establish physical-device,
saved-task, voice or model recovery. Foundation CI includes it; its first remote run
stopped at an earlier IME fixture readiness failure before reaching this probe.
See [PR #19](https://github.com/RioPlay/utterleaf/pull/19) for subsequent check results.

Dictionary publication has a separate debug-only process-death probe. After installing
the debug and androidTest APKs as above, run:

```powershell
& C:/Users/unknown/Projects/Mindict/.venv/Scripts/python.exe mobile/latinime/tools/dictionary_storage_crash_probe.py `
  --adb $adb --serial emulator-5554 --logs C:/Users/unknown/AppData/Local/UtterleafBuild/dictionary-storage-crash
```

All six API 35 cases passed locally: formats 402/403 before exchange, after exchange,
and after directory synchronization. The controller verifies emulator/UID/PID identity,
preserves failed token data, and deletes only successful synthetic case directories.
Fault controls are absent from the release APK. This checks process death, not power
loss or physical storage durability; production format migration remains unavailable.
