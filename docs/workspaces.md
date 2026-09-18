# Active development workspaces

September 18, 2026: merged topic branches were deleted after their commits
reached `main`. Remaining checkouts are the mixed recovery snapshot, one Android
tree, one desktop OBS tree, and published/unpublished release receipts.

## Streams (one owner, one PR at a time)

| Stream | Checkout | Next PR |
| --- | --- | --- |
| Android keyboard | `android-keyboard-hardening` on `main` | Signed alpha18 candidate. Phone/TalkBack/landscape stay Ernest. No new keyboard features in this slice. |
| Desktop OBS | `desktop-obs-bridge` | Land draft stack from the base: 36 enrollment → 37 arm → 38 PCM → 39 disarm → 40 controller → 41 provenance → 42 timelines. Rebase each onto current `main`/parent before undrafting. |
| Android CI split | same Android tree, later | Follow-up only: stop downloading speech models and running the full emulator suite on every keyboard PR. |

Do not mix these in one branch. Desktop CI already skips Android-only paths.

| Branch | Purpose | Next work |
| --- | --- | --- |
| `main` | Current Android keyboard checkout (`android-keyboard-hardening` worktree) | [Alpha17 polish](plans/active/android-alpha17-polish.md) is merged; signed candidate and phone acceptance remain |
| `feat/obs-enrollment-flow` | Desktop OBS stack base (`desktop-obs-bridge` worktree); draft [PR #36](https://github.com/RioPlay/utterleaf/pull/36) | Rebase onto current `main`, then pairing UI/vendor requests. Later stack PRs 37–42 stay parked. |
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
