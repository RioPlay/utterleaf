# Android 0.1.0 release

Published the first stable signed GitHub APK on November 23, 2026 UTC.
The English keyboard and optional offline dictation include the 320 dp Space
correction and reviewed Android dependency updates from PR #74.

Keep the existing package, signing key, permissions, local model verification
and preferences. The stable APK uses versionCode 22. Keep Android releases
independent of the desktop Latest designation. Further keyboard redesign,
additional languages and Play Store distribution are outside this release.

## Verification

- All 36 local tooling tests passed with
  `python -m unittest discover -s mobile/android/tools -p 'test_*.py'`, and
  the Maven audit found zero applicable advisories in 236 coordinates.
- Tag `android-v0.1.0` resolves to
  `c79e5a9ee80b9cb6d3345404fa9952ad6f16f422`.
  [Exact-main Android CI](https://github.com/RioPlay/utterleaf/actions/runs/45094727177)
  passed build, lint, audit, release contracts, 239 keyboard emulator tests and
  two lifecycle-host emulator tests, with zero skips or failures.
- [Protected signing](https://github.com/RioPlay/utterleaf/actions/runs/45096360732)
  verified the established signer and passed the signed alpha03 upgrade and
  same-version reinstall checks with synthetic settings and model markers.
- The [public stable release](https://github.com/RioPlay/utterleaf/releases/tag/android-v0.1.0)
  has package `org.utterleaf.voice`, version code 22 and the established signer.
  The downloaded APK independently passed signature, package, version,
  non-debuggable status and 16 KB alignment checks. Its SHA-256 is
  `e75df292d445d114aa8e66f71d4a14bf5e22799c7bb0aaec6ce898195083d451`.
  GitHub's Latest release still points to desktop.

The first two full runs failed in the live field-switch fixture. PR #79 made
the test wait for the destination keyboard's controls before typing and kept
all typing assertions. PR #78 removed action-pin changes for the separate
prototype workflows after the prototype's emulator failed to acquire focus.

Android's release policy uses automated verification. Phone, third-party editor,
assistive-technology and actual Obtainium observations remain unverified for
this release. The [mobile roadmap](../../mobile-roadmap.md) tracks follow-ups.
