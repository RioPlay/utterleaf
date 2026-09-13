# Active development workspaces

September 12, 2026: desktop and Android work was separated from the old Android
editing branch. The mixed state is preserved locally at `aca2b70`; the original
source checkout stays intact. Use the following workspaces for new work.

| Branch | Purpose | Next work |
| --- | --- | --- |
| `checkpoint/mixed-work-20260912` | Preserved mixed development snapshot; not a release or PR | Recovery/reference only; leave the original source environment intact |
| `release/desktop-0.4.6rc1` | Windows x64 CPU prerelease from current main | Finish CI artifact verification, publish an explicit preview, then continue desktop development |
| `feat/android-keyboard-hardening` | Original Android keyboard from current main | Run focused gesture/layout instrumentation, verify long-press defaults and complete physical-device gates |

The desktop release uses `desktop-v0.4.6-rc.1`; stable desktop `v*` and Android
`android-v*` releases remain separate. Read the platform roadmap and active plan
in the owning checkout. A green test in one checkout does not validate another.

Machine-specific paths, checkpoint revisions and audit receipts live locally in
`.grok/workspaces.json`. Existing older worktrees and branches are retained until
their unique commits and release evidence have been accounted for. Do not prune
or delete them merely because their names look obsolete.

The shared Python environment remains attached to the original source directory.
Release checks scope `PYTHONPATH` to the release checkout and do not redirect the
editable installation. Build outputs, models, test scratch and user data stay out
of commits. See [development boundaries](development-boundaries.md).

The Android integration at `10ad81e` preserves main's alpha13 version/release
metadata and newer settings/test-helper fixes. It passed 14 tooling tests, 31 JVM
tests and offline production/test Kotlin compilation; no emulator or physical
verification follows from that branch separation. The desktop source/package
checkpoint is `3bf1878`; final exact-tag CI artifact checks and publication remain
open. Local `main` was fast-forwarded to `566839d`; historical worktrees were retained.

The mixed checkpoint also preserves repository-wide build routing, prompt-file
ignore rules and the older combined gauntlet journal. Those are deferred shared
work, not part of either platform implementation commit.
