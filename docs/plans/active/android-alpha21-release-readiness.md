# Android alpha21 release readiness

## Goal

Publish the merged daily-surface reset and selected-text completion safeguard as
a bounded signed Android preview without broadening the feature scope or implying
that the full A–M redesign, physical-device, named-app or accessibility audits are
complete.

## Area

Android version metadata, release notes, Android documentation, exact-main CI,
the immutable `android-v0.1.0-alpha21` tag and the protected Android signer.
Product source is frozen at merged revision
`eb4cfd2eb840da7ce0e47594c63b1a021a8923fd` before this metadata-only increment.

## Constraints

- Preserve package ID, signing identity, preference/model storage, offline-only
  operation and all privacy boundaries.
- Do not add product behavior, dependencies, permissions or workflow maintenance
  to the release-preparation change.
- Do not reuse or alter alpha20. Alpha21 uses version code 21 and an immutable tag.
- Emulator evidence is not physical-phone, named-third-party-app, TalkBack or
  Switch Access proof.

## Acceptance

1. Version code/name, filename, tag and release notes agree on alpha21.
2. Release notes describe only the merged layout and selection-safety changes.
3. Release-contract tooling and the PR Android gate pass.
4. The merged metadata revision passes the complete exact-main Android workflow
   and retains `Android-release-input` for that same SHA.
5. The annotated tag resolves to that green main SHA.
6. Protected signing verifies package/version/signer/alignment, signed alpha03
   upgrade, same-version reinstall preservation, and publishes the prerelease.
7. Public APK, checksum, certificate and version metadata are independently
   rechecked after publication.

## Verification

```powershell
& 'C:\Users\unknown\Projects\Utterleaf\.venv\Scripts\python.exe' -m unittest discover -s mobile/android/tools -p 'test_*.py'
```

PR CI owns compile, JVM, lint and debug assembly. After merge, the complete
`.github/workflows/android.yml` run owns emulator privacy/inference, release
packaging and unsigned-input retention. The protected `android-release.yml`
workflow is dispatched only with the exact successful run and immutable tag.

## Completed work

- PR #64 merged the clean-room daily surface at `3545a8e`; PR #65 merged the
  live-selection safeguard at `eb4cfd2`.
- Exact-main Android run
  [36344294106](https://github.com/RioPlay/utterleaf/actions/runs/36344294106)
  passed on `eb4cfd2`, including the complete emulator privacy/inference phase,
  packaging and unsigned release-input retention. Its first attempt exposed two
  unrelated live timing failures that each passed exact isolated reruns; the
  single failed-job rerun passed without a product change.

## Remaining work

Merge the metadata-only release PR, obtain a new exact-main green run for that
revision, create and push the annotated alpha21 tag, dispatch protected signing,
then verify and record the public assets.

## Non-goals and stop

No workflow action upgrades, new keyboard behavior, dictation architecture,
stable-channel claim or speculative device acceptance. Stop and report precisely
if any exact-source, signing, version, upgrade or public-asset check fails.
