# Active development workspaces

Updated September 27, 2026. Merged topic branches were deleted after their commits
reached `main`. Keep the isolated desktop modernization stream separate from the
mixed recovery snapshot, Android work, the parked desktop OBS stack, and
published/unpublished release receipts.

## Streams (one owner, one PR at a time)

| Stream | Checkout | Next PR |
| --- | --- | --- |
| Android keyboard | `android-keyboard-hardening` on `codex/android-alpha21-release-record` | [Signed alpha21](https://github.com/RioPlay/utterleaf/releases/tag/android-v0.1.0-alpha21) is published. Record the immutable evidence, then continue workflow maintenance and the active experience plan. Physical campaigns remain unverified follow-up, not routine-preview gates. |
| Desktop modernization | `desktop-modernization` on `feat/desktop-modernization` | Baseline, shell, recovery, explicit multilingual model packs, privacy consent and RC3 readiness are tracked in the [active plan](plans/active/desktop-modernization.md). Next: exact-head CI, stable native device identity/physical acceptance, gated model lifecycle, performance, native-dialog and accessibility gates. |
| Desktop OBS | `desktop-obs-bridge` on `feat/obs-session-arm` | Parked while Android is prioritized. PR #36 is merged. On resumption, refresh, review and check draft [PR #37](https://github.com/RioPlay/utterleaf/pull/37), then replay #38 onto the resulting `main`. Keep #38–42 draft until each is rebased and verified. |
| Android CI split | same Android release-record branch | Fast PR checks are implemented; full emulator/release gates remain required on every exact main/manual release revision. |

Android PR #59 is merged; the exact alpha19 tag is `599f675`.
Use current remote `main` at session start. PR #36 is merged and its
remote `feat/obs-enrollment-flow` branch is deleted; do not recreate or rebase it.
PRs #38–42 still have stacked parents: PCM → disarm → controller → provenance →
timelines. After each predecessor lands, replay only the next PR's own changes
onto current `main`, inspect its diff/history, retarget it to `main`, and rerun
its required checks before undrafting or merging. Do not merge the old stack as-is.
Recheck remote status at the start of the next session.

Do not mix these in one branch. Desktop CI already skips Android-only paths.

| Branch | Purpose | Next work |
| --- | --- | --- |
| `codex/android-alpha21-release-record` | Current Android keyboard checkout (`android-keyboard-hardening` worktree) | Record the published alpha21 evidence, then continue the roadmap. Preserve [manual issue reporting](plans/completed/android-alpha18-phone-acceptance.md) and explicit unverified limits. |
| `feat/desktop-modernization` | Isolated desktop experience and RC3 candidate stream from current `main` | Finish immutable CI/package evidence under the [RC3 readiness plan](plans/active/desktop-0.4.6-rc3-release-readiness.md); keep native follow-ups separate from OBS and Android. |
| `feat/obs-session-arm` | Desktop OBS worktree (`desktop-obs-bridge`); draft [PR #37](https://github.com/RioPlay/utterleaf/pull/37) | Parked. Its earlier green check was against `aa296c9`; refresh onto current `main` and rerun checks before landing #37 and replaying #38. |
| `checkpoint/mixed-work-20260912` | Preserved mixed development snapshot; not a release or PR | Recovery/reference only; leave the original source environment intact |
| `release/desktop-0.4.6rc2` | Published Windows x64 CPU prerelease | Preserve the immutable RC2 tag and release evidence |
| `release/desktop-0.4.6rc1` | Unpublished RC1 candidate retained for audit | Reference only; tag and downloaded artifact unchanged |
| `release/android-alpha14` | Published signed original keyboard snapshot | Preserve alpha14 evidence; physical-phone testing remains deferred follow-up |
| `release/android-alpha15` | Published signed alpha15 snapshot (local branch; no dedicated worktree) | Preserve alpha15 release evidence |

The desktop release uses `desktop-v0.4.6-rc.2`; stable desktop `v*` and Android
`android-v*` releases remain separate. Current published Android preview is
[alpha21](https://github.com/RioPlay/utterleaf/releases/tag/android-v0.1.0-alpha21).
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
