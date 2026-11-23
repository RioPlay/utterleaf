# Android 0.1.0 release

Prepare the first stable signed GitHub APK from main. Ship the existing English
keyboard and optional offline dictation, resolve the 320 dp Space regression,
and include the reviewed Android dependency updates from PR #74.

Keep the existing package, signing key, permissions, local model verification
and preferences. The stable APK uses versionCode 22. Keep Android releases
independent of the desktop Latest designation. Further keyboard redesign,
additional languages and Play Store distribution are outside this release.

## Acceptance and verification

- Run the Android tooling tests with
  `python -m unittest discover -s mobile/android/tools -p 'test_*.py'`.
- Require the Android workflow to pass on the exact main revision used for
  `android-v0.1.0`, including the full emulator suite and unsigned release build.
- Dispatch the protected Android release workflow with that tag and exact build
  run. Require signature, package, version, alignment, upgrade and reinstall checks.
- Verify the public APK checksum, release status and metadata before changing
  current download links. Record the two workflow runs and the published artifact
  in the mobile roadmap.

Android's release policy uses automated verification. Phone, third-party editor,
assistive-technology and actual Obtainium observations remain separately recorded.
Stop feature work once these release checks pass.
