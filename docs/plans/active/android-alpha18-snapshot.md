# Android alpha18 signed candidate

## Goal and area

Prepare the next signed Android preview from the merged alpha17 stabilization
patch (PR #52, `80bec1b`). Start in `android-keyboard-hardening` from current
`main` (verified September 18 at `aa296c9`), using a dedicated Android release
branch for implementation. Own Android version metadata, release notes and
release documentation. Alpha17 remains the published APK.

## Constraints and non-goals

Keep `org.utterleaf.voice`, the persistent alpha03+ signing identity, preferences
and imported models. Preserve privacy, password/raw-field guards and staged
settings cancellation/reset behavior. No new keyboard features, dependencies,
permissions, learning, telemetry, ambient capture or desktop changes. Do not
replace an immutable published artifact or treat a debug APK as a signed candidate.

## Acceptance and remaining work

1. Prepare versionCode 18 / `0.1.0-alpha18` and accurate release notes for the
   typing/suggestion/geometry fixes. Review the metadata and known limits.
2. Run Android CI for the exact final candidate revision, including tooling,
   JVM, lint, builds and the full emulator suite. Preserve its
   `Android-release-input` artifact. The green polish run is evidence for the
   patch, not a substitute for candidate-revision verification.
3. Integrate reviewed release metadata into `main`; the `android-v0.1.0-alpha18`
   tag must identify the exact verified candidate and be on `main` ancestry.
4. Use the existing main-only protected signing workflow with that tag and build
   run. Verify package/version, non-debuggable state, alignment, signer continuity,
   increasing versionCode and signed install/upgrade/reinstall with preferences
   and models retained. Check alpha17-to-alpha18 update coverage explicitly;
   the workflow's older upgrade baseline alone does not prove that path.
5. Independently verify the APK checksum, signer and metadata; record the exact
   artifact, CI/signing runs and any publication in the mobile roadmap and guide.
   Do not mark alpha18 published until the signed artifact is available.

## Verification commands

From the Android checkout root:

```powershell
python -m unittest discover -s mobile/android/tools -p 'test_*.py'
```

From `mobile/android`, with JDK 17 and the SDK configured:

```powershell
.\gradlew.bat testDebugUnitTest lintDebug assembleDebug assembleRelease assembleDebugAndroidTest --no-daemon --console=plain
```

Canonical CI owns the full emulator run. After recording its exact revision and
successful run ID, the existing signing workflow takes these inputs (replace
`BUILD_RUN_ID` with that verified run; this dispatch publishes a prerelease):

```powershell
gh workflow run android-release.yml --ref main -f tag=android-v0.1.0-alpha18 -f build_run=BUILD_RUN_ID
```

## Current evidence, device gates and stop

Planning only: no alpha18 version change, tag, candidate build, signing or
publication has been performed. The [completed polish record](../completed/android-alpha17-polish.md)
records CI 35290270474: 173 instrumentation tests, 14 tooling tests and JVM/lint/builds.

Keep Pixel 8 Pro/GrapheneOS (record exact OS build), named editors, phone latency,
landscape, three-button navigation, TalkBack/Switch Access and real Obtainium
updates open in the [mobile roadmap](../../mobile-roadmap.md). Use synthetic text
for evidence. Prior snapshot phone-test deferrals do not establish alpha18 phone
acceptance. Stop this slice after candidate verification and an accurate handoff
of publication/device status; no stable-readiness claim or new feature work.
