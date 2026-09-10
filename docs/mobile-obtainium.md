# Android updates with Obtainium

[Mobile guide](mobile.md) · [Mobile roadmap](mobile-roadmap.md)

Obtainium checks GitHub and installs Android updates. Utterleaf itself keeps **no
Internet permission** and does not add an updater service. The signed channel
begins with Android alpha03; alpha01/alpha02 used disposable debug keys.

Current release: [Android alpha09](https://github.com/RioPlay/utterleaf/releases/tag/android-v0.1.0-alpha09) ·
[Signed APK](https://github.com/RioPlay/utterleaf/releases/download/android-v0.1.0-alpha09/Utterleaf-Android-0.1.0-alpha09.apk).

## Set up

In a signed Utterleaf Android build, open **Set up updates in Obtainium**.
The button opens Obtainium's configuration confirmation; it does not silently
install another application. Obtainium must already be installed separately.

Alternatively, add `https://github.com/RioPlay/utterleaf` in Obtainium and set:

| Setting | Value |
| --- | --- |
| Include prereleases | On while Android is an alpha |
| Filter release titles by regular expression | `^Utterleaf Android ` (including the trailing space) |
| Filter APKs by regular expression | `^Utterleaf-Android-.*\.apk$` |
| Verify latest tag | Off — the repository's stable latest release belongs to desktop |
| Fallback to older releases | On — scan past newer desktop releases to the newest matching Android release |
| Version extraction / trim version string | `^android-v(.+)$` |
| Match group | `1` |
| Version detection | On |

The exact import data is [obtainium.json](../mobile/android/app/src/main/assets/obtainium.json).
Filters deliberately exclude desktop releases and the old debug APKs. No GitHub
token is required for ordinary public-repository access; GitHub rate limits may apply.

## Migrating from the old alpha

Android will reject an update signed by a different key. If alpha01/alpha02 is
installed, uninstall it once, install the signed alpha03-or-later APK and re-import
the speech model. Uninstalling removes app data. Do not disable Android's signature
checks or protection settings to force an update.

Signed alpha03 and alpha04 use the same persistent release identity. An installed
signed alpha03 should be updated in place. The
[successful alpha04 signing/publishing run](https://github.com/RioPlay/utterleaf/actions/runs/34428171272)
verified the unchanged certificate, upgraded signed alpha03 to alpha04 on an
emulator, and reinstalled alpha04. Preference and imported-model preservation were
not exercised. Real Obtainium import and physical updates remain separate gates.

The [passed alpha04 CI run](https://github.com/RioPlay/utterleaf/actions/runs/34427672686)
records 4 JVM, 11 API 35 emulator and 3 release-contract tests. See the
[mobile validation record](mobile.md#android-validation--september-9-2026) for exact
keyboard test coverage.

New installations should use the signed release APK, never a CI debug APK. A
release is available only after its signed APK is published; a roadmap entry or
CI run is not a download release. See [Android releases](https://github.com/RioPlay/utterleaf/releases).

## Verify the signing identity

Package: `org.utterleaf.voice`.

Release certificate SHA-256:

```text
a7987d44a70eed90500b5d77a555df0e18e80e79dd7cf882e1a066dbc2214be6
```

The [public certificate](../mobile/android/release-certificate.pem) and
[fingerprint file](../mobile/android/signing-certificate.sha256) identify the
release key, not any particular APK. Each release also has its own APK SHA-256
checksum. Android checks signer compatibility during updates; Obtainium still
depends on the source and device installer, and is not a separate audit of app safety.

## Maintainer contract

- Use `android-v<versionName>` tags and `Utterleaf Android <versionName>` titles.
- Increase `versionCode` on every published version. Do not replace published APKs.
- Publish one `Utterleaf-Android-<versionName>.apk`, checksums, signing information
  and `version.json`; leave the release as a prerelease during alpha development.
- Keep signing secrets in the main-only `android-release` environment. Normal
  builds and pull requests do not receive them. Sign a verified CI artifact in
  the separate release workflow; private keys never belong in artifacts or Git.
- Maintain an independently protected offline backup of the signing identity.
  The provisioned local keystore is encrypted and its password is protected by
  Windows DPAPI for the current user; that machine-bound copy is not a disaster-recovery backup.
- Test real Obtainium import and version-to-version updates on a device before
  claiming those workflows fully verified. Automated signing/install checks do
  not cover every installer or background-update policy.

Reference: Obtainium's [source/filter documentation](https://wiki.obtainium.imranr.dev/sources/)
and [configuration deep links](https://wiki.obtainium.imranr.dev/deep_links/).
