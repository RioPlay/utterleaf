# Windows dictation delivery repair, RC4 release record

## Result

Utterleaf 0.4.6 RC4 is published as the unsigned Windows x64 CPU prerelease at the [published RC4 release](https://github.com/RioPlay/utterleaf/releases/tag/desktop-v0.4.6-rc.4). Release `443814965` was published 2026-11-13 04:30:37 UTC with prerelease enabled and `latest=false`; stable v0.4.5 remains the default. PR #76 was merged before release.

The immutable tag `desktop-v0.4.6-rc.4` resolves to commit `9d59996c5d90a0d7d08aef555799ff6a46ebc350`. [PR #76](https://github.com/RioPlay/utterleaf/pull/76/checks) passed its hosted gates, and the exact-tag [Windows build](https://github.com/RioPlay/utterleaf/actions/runs/43364255809) passed. The JUnit report records 1,712 tests, 1,699 passed, 13 skipped, zero failures and zero errors.

## Artifact verification

The published `Utterleaf-windows-x64-cpu.zip` is 113,160,790 bytes with SHA-256 `630949d0144bcc4242380addac62d0eca5d9ed2b068c22f229be91c2009f6b2f`. Public source and runtime review reported no material findings. The archive, frozen CLI and offline fixture checks passed. Review verified all three executable hashes, 10 native payloads and 353 notice-file hashes. All five GitHub asset digests and sizes matched the reviewed local outputs; downloading the public checksum matched the ZIP hash.

## Limits

The release is unsigned and Windows x64 CPU-only. Expat 2.9.0 and SQLite 3.50.4 advisories remain. Actual T3 Code two-take dictation after the local fix is unconfirmed. Model quality, GPU behavior, physical-device accessibility, unbounded performance, other desktop platforms and live OBS are not established by this release verification.
