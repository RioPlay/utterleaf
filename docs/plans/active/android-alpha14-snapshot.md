# Android alpha14 snapshot — published

## Goal

Prepare and publish a signed, installable alpha14 snapshot of the original Utterleaf
keyboard so alpha13 users can update in place while the broader Android
roadmap continues independently.

## Area

- `mobile/android/app/build.gradle.kts` — versionCode 14 and versionName
  `0.1.0-alpha14`.
- `mobile/android/RELEASE_NOTES.md` — bounded feature scope and known limits.
- Existing shipping keyboard source and tests tagged at revision `46893f2`.

## Constraints

- Preserve application ID `org.utterleaf.voice` and the persistent alpha03+
  release signing identity. Never downgrade versionCode or reuse the
  experimental foundation ID/signing channel.
- Do not copy or integrate code, resources or assets from `mobile/latinime`.
- Keep no-network, no-ambient-capture, no-clipboard-history, secure-field and
  model-import boundaries unchanged. No permission bypass or unsigned APK is
  acceptable.
- Local preparation does not tag, publish, sign or download release inputs.
  Publication runs only through the protected main-branch release workflow.
  Local emulator evidence remains evidence for tested paths, not physical-device
  or accessibility certification.

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

The first pull-request CI run, [34738528821](https://github.com/RioPlay/utterleaf/actions/runs/34738528821),
passed the build, JVM, lint and tooling steps, then ran all 135 API 35 tests with
4 failures and 0 skips. The bounded corrections make the Geometry test click
the same ready accessibility node within its existing wait, include the Hold
timing slider in tuning expectations, open Tools before using a Tools-only quick
toggle, and persist the terminal-mode one-hand fixture before preference
synchronization. The corrected tagged revision `46893f2` then passed
[Android CI 34740122401](https://github.com/RioPlay/utterleaf/actions/runs/34740122401):
all 135 API 35 tests with zero failures or skips, the release build, 31 JVM tests,
lint and 14 tooling tests. The workflow preserved the unsigned release input for
isolated signing.

The main-only `.github/workflows/android-release.yml` path completed in
[signed publication 34741640577](https://github.com/RioPlay/utterleaf/actions/runs/34741640577).
It verified the `android-v0.1.0-alpha14` tag against the successful build,
package/version/non-debuggable state, zip alignment, certificate continuity and
increasing versionCode, then passed signed install/upgrade/reinstall before
publishing the [prerelease APK and metadata](https://github.com/RioPlay/utterleaf/releases/tag/android-v0.1.0-alpha14).

## Pending gates

TalkBack, Switch Access, landscape and broad editor compatibility, and a real
Obtainium update remain unverified. Physical-phone testing is also unverified;
for alpha14 it is deferred to follow-up user feedback rather than blocking the
completed publication. These limits stay in the release notes and publication
description, and no physical-device verification is claimed.

## Stop

Stop this preparation after the metadata, notes and plan are coherent and
reviewable. Do not expand alpha14 into roadmap completion or foundation
migration.
