# Active development workspaces

September 18, 2026: merged topic branches were deleted after their commits
reached `main`. Remaining checkouts are the mixed recovery snapshot, one Android
tree, one desktop OBS tree, and published/unpublished release receipts.

| Branch | Purpose | Next work |
| --- | --- | --- |
| `main` | Current Android keyboard checkout (`android-keyboard-hardening` worktree) | [Alpha17 polish](plans/active/android-alpha17-polish.md) is merged; signed candidate and phone acceptance remain |
| `feat/recorded-file-timelines` | Desktop OBS stack tip (`desktop-obs-bridge` worktree); draft PRs 36–42 | Packaged-decoder release acceptance and leftover real timeline edge cases |
| `checkpoint/mixed-work-20260912` | Preserved mixed development snapshot; not a release or PR | Recovery/reference only; leave the original source environment intact |
| `release/desktop-0.4.6rc2` | Published Windows x64 CPU prerelease | Preserve the immutable RC2 tag and release evidence |
| `release/desktop-0.4.6rc1` | Unpublished RC1 candidate retained for audit | Reference only; tag and downloaded artifact unchanged |
| `release/android-alpha14` | Published signed original keyboard snapshot | Preserve alpha14 evidence; physical-phone testing remains deferred follow-up |
| `release/android-alpha15` | Published signed alpha15 snapshot (local branch; no dedicated worktree) | Preserve alpha15 release evidence |

The desktop release uses `desktop-v0.4.6-rc.2`; stable desktop `v*` and Android
`android-v*` releases remain separate. Current published Android preview is
[alpha17](https://github.com/RioPlay/utterleaf/releases/tag/android-v0.1.0-alpha17).
Read the platform roadmap and active plan in the owning checkout. A green test
in one checkout does not validate another.

Machine-specific paths, checkpoint revisions and audit receipts live locally in
`.grok/workspaces.json`. Desktop CI skips Android source, Android guides/plans
and this table; Android CI stays on `mobile/android`. Shared README/brand
changes still run desktop CI.

The shared Python environment remains attached to the original source directory.
Release checks scope `PYTHONPATH` to the release checkout and do not redirect the
editable installation. Build outputs, models, test scratch and user data stay out
of commits. See [development boundaries](development-boundaries.md).
