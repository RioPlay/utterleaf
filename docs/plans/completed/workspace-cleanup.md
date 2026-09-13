# Branch and workspace cleanup

## Goal and area

Honor the September 12 request for a quick organization phase before publication:
preserve all existing work and give the desktop preview and original Android
keyboard clear, separate development branches and resumable plans.

## Constraints

No work loss, branch force-push, artifact deletion, app replacement or environment
reinstallation. Preserve old worktrees and their unique commits. The local mixed
checkpoint is a recovery snapshot, not a release candidate or a cross-platform PR.
Do not copy stale Android base files over newer main fixes during separation.

## Acceptance and verification

- Save the mixed source/docs/tests state on a named local checkpoint branch.
- Keep the Windows preview on its existing isolated release branch.
- Put Android changes on a current-main branch, using three-way reconciliation
  where the old Android branch and main differ. Preserve version/release metadata.
- Inspect every new branch diff, retain source snapshot receipts, verify no Android
  implementation in the desktop release diff and no desktop implementation in the
  Android diff. Run targeted checks for any conflict resolution.
- Update `docs/workspaces.md`, local `.grok/workspaces.json`, platform roadmaps and
  active plans with exact next steps. No automatic publication during cleanup.

## Non-goals and stop

No speculative branch deletion, broad disk cleanup, history rewrite, UI redesign
or release promotion. Stop when the work is preserved, separated and documented;
resume the Windows prerelease first.

## Progress

The mixed state is preserved by local commit `aca2b70` on
`checkpoint/mixed-work-20260912`; the original checkout is clean and its runtime
source/environment is unchanged. Desktop preview source is isolated at `3bf1878`
on `release/desktop-0.4.6rc1`. Android integration is isolated at `10ad81e` on
`feat/android-keyboard-hardening`, based on main `566839d`.

Six Android textual conflicts and two compile-detected API drifts were reconciled
with current main. The integration retains settings snapshot synchronization,
UiAwait and active-IME-root test helpers, and alpha13 version/release metadata.
Fourteen tooling tests, 31 JVM tests and production/androidTest Kotlin compilation
passed offline. No emulator/physical or release evidence is claimed for that pass.

Git diff checks confirm no Android implementation/workflow in the desktop release
delta and no desktop source/tests/packaging in the Android delta. Local main was
fast-forwarded after an ancestor check; misleading main upstream tracking was
removed from the new release and old unrelated topic branches. No branch or
worktree was deleted, no history was force-pushed and no package was published.
The three older external worktrees retain their history.

See [active workspaces](../../workspaces.md) and local `.grok/workspaces.json` for
paths/revisions and deferred shared changes. Resume the Windows prerelease first;
its exact-tag CI artifact and publication gates remain open.

Independent conflict-integration review of `10ad81e` found no blockers: main's
settings snapshot, accessibility labels, UiAwait synchronization and active IME
root semantics remain alongside the new features. Physical/device gates are
unchanged. Cleanup is complete; no release was published during this phase.
