# Android polish and alpha20 release

## Goal

Ship a calmer, faster Utterleaf Android preview with four stable daily keyboard
destinations, complete System/Light/Dark/OLED appearance choices, clearer voice
review-versus-direct-insert behavior, and much faster routine pull-request CI.

## Area

- `mobile/android/app/src/main/java/org/utterleaf/voice/`
- focused Android JVM and instrumentation tests
- `.github/workflows/android.yml`
- Android release metadata and release notes

## Constraints

- Recording remains explicit and local. No ambient capture, partial transcript
  insertion, clipboard history, or automatic clipboard reads.
- Review is the ordinary dictation path. Direct insertion remains an explicit
  hold gesture and must not retry after an uncertain host result.
- Settings remain staged behind Apply/Cancel; Reset preserves models and user data.
- A fast PR path may skip the emulator, but a release tag must still identify an
  exact successful `main`/manual run with the full emulator privacy suite.
- OLED means true-black primary surfaces with readable controls; it is not a
  battery-life claim.

## Selected layout

The approved fixed-layout wireframes use four stable daily destinations:
**Tools**, **Edit**, **Emoji**, and **Voice**. Editing actions move behind the
single Edit destination; settings, layout and power controls remain under Tools.
Every secondary surface has one obvious return to typing.

## Acceptance

- Daily toolbar exposes no more than the four selected destinations and keeps
  touch targets at least 48dp.
- Edit exposes undo/redo, selection, cut/copy/paste and navigation without
  putting those controls on the daily toolbar.
- Theme choice includes System, Light, Dark and OLED, persists across restart,
  previews before Apply, and Reset returns to System without deleting models.
- Mic tap always records for review; the optional hold gesture is clearly named
  as direct insertion after recognition. Failed/uncertain insertions stay
  recoverable and are never blindly repeated.
- Pull requests run tooling, JVM, lint and build checks without provisioning an
  emulator. Pushes to `main` and manual runs retain the full emulator/privacy
  suite and unsigned release input.

## Verification

1. `python -m unittest discover -s mobile/android/tools -p test_*.py`
2. `mobile/android/gradlew testDebugUnitTest lintDebug compileDebugAndroidTestKotlin assembleDebug assembleRelease`
3. Focused API 35 instrumentation for settings, compact layers, voice review,
   private draft and persistence, then the full connected suite for the candidate.
4. Successful exact-revision Android CI on `main`, followed by protected signing,
   signer/package/version/alignment and signed upgrade/reinstall checks.

Local candidate evidence on 2026-09-19:

- Android release tooling: 17/17 passed.
- JVM tests, lint, instrumentation compilation, debug APK and unsigned release
  APK: passed in one Gradle invocation.
- API 35 emulator suite: 187/187 passed after the final timing-hardening change.
- Generated live-keyboard, Settings-preview and editor-action screenshots were
  inspected; emulator visuals are not physical-device acceptance.

## Non-goals

- Streaming or partial speech recognition, live host-field rewriting, prediction,
  clipboard history, new language models, or a stable-channel release.
- Claims about physical-phone comfort or assistive-technology behavior that were
  not directly observed.

## Stop

Stop after the alpha20 prerelease is published with recorded checks and known
device/editor limitations remain explicit.
