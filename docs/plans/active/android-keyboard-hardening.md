# Android keyboard hardening

## Goal

Keep the current custom IME safe and predictable: stale speech/editor work cannot
cross sessions, hold timing is optional with a tap fallback, terminal input stays
literal, and Reset does not delete models. No LatinIME import.

This bounded hardening pass is preserved under the September 12
[independent keyboard rebuild](android-keyboard-rebuild.md). Its restriction on
starting prediction/swipe applies to this pass; the broader product plan records
the later prerequisites. The former LatinIME extraction proposal is superseded.

## Area

`mobile/android/app/src/main/java/org/utterleaf/voice/`
`mobile/android/app/src/main/cpp/bridge.cpp`
`mobile/android/app/src/androidTest/`
`docs/android-keyboard-*.md`, `docs/mobile-roadmap.md`

## Constraints

- Security first; no ambient capture, clipboard history, or context learning.
- Emulator tests are regression evidence, not physical-device or TalkBack proof.
- Do not import AOSP LatinIME, dictionaries, or extra permissions.
- Adaptive touch zones stay off. Geometry stays static.
- Do not collide on `DeviceTest.kt` / `PrivacyCoreTest.kt` with other Android work.

## Acceptance

- Every commit/key/editor/speech callback is generation-gated, including hide/show
  and subtype changes.
- Native decode aborts when `reset()` starts a newer generation or `cancel()`
  marks the current one; a later `reset()` can decode again.
- Hold timing: system default or 250–800 ms; tap still types; Tools → Accents remains.
- `TYPE_NULL` / terminal mode: ASCII as key events, never `commitText` fallback.
- Refused terminal/editor actions show **Key unavailable**.
- `KeyboardOptions.resetPreferences` restores prefs only; verified models stay.

## Completed in source (unreleased)

- Native `work_id` isolation in `bridge.cpp`; `NativeEngine.reset()` starts a generation.
- `KeyboardIme` generation gates and subtype invalidation.
- Hold-timing preference, settings slider, gesture tests.
- `KeyboardOptions.resetPreferences`.
- Terminal tests for `ls`-style raw tokens and refused-key unavailable state.
- `PersistenceTest`: Reset restores defaults and leaves model files/markers.
- Real `TYPE_NULL` EditText: `ls` via key events; Ctrl+C does not insert `c`; copy/paste refused.
- `VoiceIme` insert re-checks the current field (`safeField`) before `commitText`.
- Signed-upgrade preservation: `preserve_upgrade.py` seeds keyboard prefs + model
  markers after the predecessor APK, verifies them after installing the new APK.

## Remaining

- Physical-device, TalkBack, and Switch Access acceptance.
- Do not start prediction, swipe, heatmaps, or LatinIME.

## Verification

- `python -m unittest discover -s mobile/android/tools -p test_*.py`
- `gradlew testDebugUnitTest` and `connectedDebugAndroidTest` when `JAVA_HOME` is set
- Emulator success is not a ship claim

## Validation so far

- Python Android tooling tests passed locally (7 tests), and desktop
  `tests/test_repo_boundaries.py` passed.
- `gradlew testDebugUnitTest --no-daemon` passed with Temurin 17.
- `gradlew lintDebug assembleDebug --no-daemon` passed, including ARM64 and
  x86_64 native builds.
- Focused API 35 instrumentation passed: 56 non-model tests, including
  persistence, tuning, terminal dispatch, gestures, editor actions and voice
  controls; the live IME editor test also passed with raw `TYPE_NULL` input and
  Ctrl+C protection.
- The full 79-test API 35 run passed after temporarily supplying the same
  hash-verified model and JFK fixtures used by CI. This covers native inference,
  reset/cancel/recovery and capture cancellation. The run also exposed and the
  focused reruns resolved test-harness issues (API-35 live-key lookup, stale
  accessibility nodes and an invalid direct `TYPE_NULL` connection assertion).

## Risks

- Hold-timing gesture tests use sleeps; they can flake under load.
- Native generation runtime behavior is covered by the passing model-backed API
  35 tests; the NDK build and Java/JVM checks also pass.
- Uncommitted source is on `feat/android-edit-actions`; do not revert it for
  unrelated desktop work.
