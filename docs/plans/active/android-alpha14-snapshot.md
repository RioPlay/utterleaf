# Android alpha14 snapshot

## Goal

Prepare a signed, installable alpha14 snapshot of the original Utterleaf
keyboard so alpha13 users can update in place while the broader Android
roadmap continues independently.

## Area

- `mobile/android/app/build.gradle.kts` — versionCode 14 and versionName
  `0.1.0-alpha14`.
- `mobile/android/RELEASE_NOTES.md` — bounded feature scope and known limits.
- Existing shipping keyboard source and tests at the integration revision
  `ece1109`.

## Constraints

- Preserve application ID `org.utterleaf.voice` and the persistent alpha03+
  release signing identity. Never downgrade versionCode or reuse the
  experimental foundation ID/signing channel.
- Do not copy or integrate code, resources or assets from `mobile/latinime`.
- Keep no-network, no-ambient-capture, no-clipboard-history, secure-field and
  model-import boundaries unchanged. No permission bypass or unsigned APK is
  acceptable.
- This preparation does not tag, publish, sign or download release inputs. Local
  verification may build debug/test artifacts and install them only on the
  dedicated emulator. A successful emulator run remains evidence for tested
  paths, not physical-device or accessibility certification.

## Snapshot scope

The candidate contains the integrated editor/session hardening and native
decode generation guards; continuous two-thumb rollover; QWERTY/QWERTZ/AZERTY
letter layouts; one-hand alignment; local emoji browser; Latin compose; bounded
private drafts; and the reviewed long-press visible-hint default with deliberate
slide selection and fail-closed cancellation.

Prediction, swipe, multilingual support, broad correction, heatmaps, LatinIME
adoption, and physical/accessibility expansion are non-goals for alpha14.

## Acceptance and verification

Before publication, run the canonical Android checks from `mobile/android`:

- `python -m unittest discover -s mobile/android/tools -p test_*.py`.
- `gradlew testDebugUnitTest lintDebug compileDebugAndroidTestKotlin assembleDebug assembleRelease`.
- Focused API 35 instrumentation for `KeyboardGesturesTest` and
  `LetterLayoutTest`, followed by the affected regression/geometry/editor,
  rollover, emoji, compose, private-draft and persistence coverage as required
  by CI.
- The Android build workflow must pass for the exact commit SHA and preserve
  its `Android-release-input` artifact.

Local snapshot verification at `78da52b`, followed by the test-only fixture fix
at `fcaf110`, completed the bounded pre-publication checks available without
release signing:

- `python -m unittest discover -s mobile/android/tools -p test_*.py` passed 14
  tests.
- `gradlew :app:testDebugUnitTest :app:lintDebug :app:assembleDebug
  :app:assembleDebugAndroidTest --offline --no-daemon` passed 31 JVM tests and
  lint with 0 errors and 51 warnings, and built the debug and test APKs.
- After installing those APKs on the dedicated `UtterleafFoundation35` API 35
  emulator, the explicit `KeyboardGesturesTest,LetterLayoutTest` instrumentation
  run passed all 16 tests in 31.105 seconds. The synchronization fix waits for
  the displayed alternate strip and keeps the layout-switch cancellation,
  stale-release and modifier assertions intact. Independent test review passed.

The signed path is the main-only `.github/workflows/android-release.yml`
workflow: dispatch with the existing `android-v0.1.0-alpha14` tag and exact
successful Android build run, use the protected `android-release` environment,
verify package/version/non-debuggable status, zip alignment, certificate
continuity and increasing versionCode, then exercise signed install/upgrade and
reinstall before publishing the prerelease assets.

## Pending gates

The full Android CI workflow for the final exact SHA, `assembleRelease`, protected
release signing, certificate/version checks, signed install/upgrade/reinstall and
artifact publication remain pending. Physical phones, TalkBack, Switch Access,
landscape and broad editor compatibility, and real Obtainium import/update
behavior remain unverified. These limits must stay in the release notes and
publication description.

## Stop

Stop this preparation after the metadata, notes and plan are coherent and
reviewable. Do not expand alpha14 into roadmap completion or foundation
migration.
