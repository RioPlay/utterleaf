# Android alpha15 snapshot — completed

[Android alpha15](https://github.com/RioPlay/utterleaf/releases/tag/android-v0.1.0-alpha15)
was published September 13, 2026 at 08:31:48 UTC. The tag
`android-v0.1.0-alpha15` identifies tested source
`52b0e6a3b0acab05765ee7aa8f7ea9395b8993b2`, merged through
[PR #29](https://github.com/RioPlay/utterleaf/pull/29) at
`bc1cc2ba370c7935adbce49e950ef088f34c6ad7`.
Current product work remains on the [mobile roadmap](../../mobile-roadmap.md).

## Released result

The original keyboard now has a single sliding Tools strip, replacement
settings/edit/navigation layers, comma-hold Settings and Backspace selection.
The launcher and primary keyboard are named **Utterleaf**; the separate
voice-only input is **Utterleaf dictation**. See the
[completed layout contract](android-compact-layers.md).

The package remains `org.utterleaf.voice`, versionCode 15 and versionName
`0.1.0-alpha15`. Alpha03-and-later signing identity, preferences, model storage
and privacy boundaries remain unchanged. No new runtime dependency, permission,
network access, typing history, ambient recording or screenshot-protection
change is included. The published alpha14 and desktop RC2 artifacts are unchanged.

## Verification and artifact

[Canonical CI 34747169547](https://github.com/RioPlay/utterleaf/actions/runs/34747169547)
checked out that exact source and passed 148 API 35 tests and 31 JVM tests with
zero failures or skips, 14 tooling tests, builds and lint (0 errors,
55 warnings). Its pinned tiny.en/base.en inference fixtures passed. The
`Android-release-input` artifact came from this same successful revision.

The first candidate run 34746232693 failed one of 148 tests because a setup
assertion retained the old Utterleaf Keyboard label. It produced no release
input. The test-only correction passed locally, retained its model/privacy
assertions and added explicit distinct IME-label checks; the final canonical
run above supplies the complete release acceptance evidence.

[Protected release run 34747825102](https://github.com/RioPlay/utterleaf/actions/runs/34747825102)
verified main ancestry, version increase, package identity, non-debuggable state,
16KB alignment and certificate continuity. It installed signed alpha03, seeded
preferences, upgraded to alpha15, verified those preferences and reinstalled
alpha15 before publishing. This is emulator upgrade evidence, not a physical
phone or Obtainium acceptance result.

[Signed APK](https://github.com/RioPlay/utterleaf/releases/download/android-v0.1.0-alpha15/Utterleaf-Android-0.1.0-alpha15.apk):
7,510,616 bytes; SHA-256
`442302ab60ef5c81ed7af6eb0e035ca8d35b17824584377f2c65c438cb067c12`.
The certificate SHA-256 remains
`a7987d44a70eed90500b5d77a555df0e18e80e79dd7cf882e1a066dbc2214be6`.

Independent downloaded-artifact review matched all four public asset hashes,
verified one signer with v2/v3 signatures, package/version/non-debuggable state,
alignment and the compiled launcher/IME labels. Public checksum, certificate
and version sidecars accompany the APK. Local receipts are in
`.grok/android-alpha15-ci/run-34747169547/` and
`.grok/release/android-alpha15-delivery/`.

## Remaining limits

Physical-phone testing is user-deferred. TalkBack/Switch Access, landscape,
broad editor behavior and real Obtainium updates remain unverified. Android
speech capture still has a 120-second limit. Prediction, swipe typing, broader
languages, Incognito and touch heatmaps are not part of this snapshot.
This release slice is complete; those product areas retain separate roadmap work.
