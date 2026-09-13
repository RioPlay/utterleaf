# Active development workspaces

September 12, 2026: desktop and Android work was separated from the old Android
editing branch. The mixed state is preserved locally at `aca2b70`; the original
source checkout stays intact. Use the following workspaces for new work.

| Branch | Purpose | Next work |
| --- | --- | --- |
| `checkpoint/mixed-work-20260912` | Preserved mixed development snapshot; not a release or PR | Recovery/reference only; leave the original source environment intact |
| `release/desktop-0.4.6rc2` | Published Windows x64 CPU prerelease with runtime notice corrections; PR #26 merged | Preserve the immutable RC2 tag and release evidence; continue desktop work from main |
| `feat/desktop-dictation-layout` | Partial Dictation settings layout work at `e05a2cf`, with local uncommitted edits | Frozen for Android priority; compact-window acceptance is incomplete and this work is not released |
| `release/desktop-0.4.6rc1` | Unpublished RC1 candidate retained for audit | Reference only; its immutable tag and downloaded artifact are unchanged |
| `release/android-alpha14` | Published signed original keyboard snapshot; PR #25 merged | Preserve alpha14 evidence; physical-phone testing remains deferred follow-up |
| `release/android-alpha15` | Published signed alpha15 compact keyboard and Utterleaf naming snapshot; PR #29 merged | Preserve alpha15 release evidence; physical-phone testing remains deferred follow-up |

The desktop release uses `desktop-v0.4.6-rc.2`; stable desktop `v*` and Android
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

Historical separation receipts: Android integration `10ad81e` preserved main's alpha13 version/release
metadata and newer settings/test-helper fixes. It passed 14 tooling tests, 31 JVM
tests and offline production/test Kotlin compilation; no emulator or physical
verification followed from that branch separation. The desktop source/package
checkpoint was `3bf1878`. Local `main` was then fast-forwarded to `566839d`;
historical worktrees were retained.

September 13 release status: [Android alpha14](https://github.com/RioPlay/utterleaf/releases/tag/android-v0.1.0-alpha14)
is the prior published snapshot from `46893f2`; [Android alpha15](https://github.com/RioPlay/utterleaf/releases/tag/android-v0.1.0-alpha15)
is published from verified source `52b0e6a` through merge `bc1cc2b`, with exact-revision CI,
persistent signing, installation and upgrade verification.
[Windows RC2](https://github.com/RioPlay/utterleaf/releases/tag/desktop-v0.4.6-rc.2)
is published from `90d2e14`, after exact-tag CI and independent downloaded-artifact
verification. Stable desktop v0.4.5 remains the default release. Desktop PR #26
merged at `bf4dfda`; Android PR #29 merged at `bc1cc2b`. The separately
reviewed Backspace gesture is not in alpha14; it shipped
in alpha15. See the platform roadmaps for
remaining product work and unverified device behavior.

The mixed checkpoint also preserves repository-wide build routing, prompt-file
ignore rules and the older combined gauntlet journal. Those are deferred shared
work, not part of either platform implementation commit.
