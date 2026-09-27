# Android alpha21 release readiness

## Goal and outcome

Publish the merged daily-surface reset and selected-text completion safeguard as
a bounded signed Android preview without implying that the full A–M redesign,
physical-device, named-app or accessibility audits are complete.

Completed September 27, 2026. PR #66 merged the reviewed version and release
metadata as `394fdff11b8ed300d320d9e28c04876d00cc2c93`. Exact-main Android
[run 36347322221](https://github.com/RioPlay/utterleaf/actions/runs/36347322221)
passed and retained the unsigned input for that revision. Annotated tag
`android-v0.1.0-alpha21` resolves to the same commit.

Protected signing/publication
[run 36348423330](https://github.com/RioPlay/utterleaf/actions/runs/36348423330)
verified release identity, package, increasing version code, established signer
and alignment; passed signed alpha03 upgrade and same-version reinstall data-
preservation checks; and published
[Utterleaf Android 0.1.0-alpha21](https://github.com/RioPlay/utterleaf/releases/tag/android-v0.1.0-alpha21).

The downloaded public APK is 11,587,536 bytes with SHA-256
`b3cf9aed7259f3004ecaab657502ce6019abbdd265ff699c96bc16a3c3578434`.
Its checksum matches; `version.json` reports package `org.utterleaf.voice`, code
21 and name `0.1.0-alpha21`; and certificate SHA-256
`a7987d44a70eed90500b5d77a555df0e18e80e79dd7cf882e1a066dbc2214be6`
matches the established release identity.

## Scope and constraints

Alpha21 contains the independently designed one-row daily surface, continuous
bottom row and live selected-text completion safeguard merged by PRs #64 and #65.
No FUTO code, assets, labels, constants or theme values were copied. The release
preparation added no product behavior, dependency, permission or workflow change
and preserved package identity, local preferences/models and offline/privacy
boundaries.

## Verification

- Release tooling: **26/26**.
- Local JVM tests and lint: pass.
- Release-preparation PR Android, Windows, macOS and Linux checks: pass.
- Exact-main Android build/JVM/lint, lifecycle compile, release contracts,
  complete emulator privacy/inference, release packaging and artifact retention:
  pass on `394fdff`.
- Protected package/sign/install/upgrade/reinstall/publication: pass.
- Downloaded public APK/checksum/version/certificate/tag identity: independently
  rechecked.

## Limits

This closes the alpha21 preview release only. Emulator results do not establish
physical-phone comfort, named third-party-editor compatibility, real Obtainium
updates, TalkBack/Switch Access acceptance or final A–M redesign completion. The
Node.js-action/setup-java and Ubuntu runner warnings remain the separate workflow
maintenance item already recorded in the alpha20 release record and roadmap.
