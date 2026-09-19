# Android alpha18 signed candidate

## Published — September 19, 2026 UTC (September 18 local)

[Signed alpha18](https://github.com/RioPlay/utterleaf/releases/tag/android-v0.1.0-alpha18)
is available as a preview. PR #56 merged at `70b0cbf`; immutable tag
`android-v0.1.0-alpha18` identifies `0b8ed20f62f63f5b9e44720f60ea4da19ccf05c7`.

- [Exact-candidate CI 35416227420](https://github.com/RioPlay/utterleaf/actions/runs/35416227420):
  180 instrumentation tests, no failures/skips, and tooling/JVM/lint/builds passed.
- [Signing 35417085075, attempt 2](https://github.com/RioPlay/utterleaf/actions/runs/35417085075):
  package/version, signer, alignment and alpha03 upgrade/reinstall checks passed.
  Attempt 1 failed at emulator root setup before candidate installation; retry
  passed without changing the APK or bypassing preservation assertions.
- Independent downloaded artifact verification: versionCode 18 / `0.1.0-alpha18`,
  non-debuggable, 16K alignment, persistent signer and checksum passed.
- Signed alpha17 → alpha18 update and alpha18 reinstall passed on API 35 with
  synthetic preferences and model-storage markers preserved byte-for-byte;
  Setup launched successfully. This does not establish real imported-model use.
- APK SHA-256: `128c0f9e2719c5aed56f06ff83e1080da44afc360ba7fd2483be44ac318381c0`.
- Certificate SHA-256: `a7987d44a70eed90500b5d77a555df0e18e80e79dd7cf882e1a066dbc2214be6`.

Candidate work is complete. The next gate is the
[phone acceptance checklist](../active/android-alpha18-phone-acceptance.md).
All physical checks remain unperformed. The original contract below is historical;
earlier pending statements do not reopen the completed release steps.

## Goal and area

Prepare the next signed Android preview from the merged alpha17 stabilization
patch (PR #52, `80bec1b`). Start in `android-keyboard-hardening` from current
`main` (verified September 18 at `aa296c9`), using a dedicated Android release
branch for implementation. Own Android version metadata, release notes and
release documentation. Alpha17 remains the published APK. The authorized
[settings experience pass](android-settings-experience.md) now precedes candidate
preparation; include its reviewed usability and staging fixes with the polish.

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

Version metadata and release notes are prepared at 18 / `0.1.0-alpha18`, alongside
the settings experience pass. Final candidate build/CI, tag, signing and
publication remain pending. The [completed polish record](android-alpha17-polish.md)
records CI 35290270474: 173 instrumentation tests, 14 tooling tests and JVM/lint/builds.

Keep Pixel 8 Pro/GrapheneOS (record exact OS build), named editors, phone latency,
landscape, three-button navigation, TalkBack/Switch Access and real Obtainium
updates open in the [mobile roadmap](../../mobile-roadmap.md). Use synthetic text
for evidence. Prior snapshot phone-test deferrals do not establish alpha18 phone
acceptance. Stop this slice after candidate verification and an accurate handoff
of publication/device status; no stable-readiness claim or new feature work.
