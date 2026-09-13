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

Initial inventory recorded five worktrees. The three older external worktrees
have no tracked modifications; their history is retained. Desktop RC1 already
has a separate checkout from main. Android separation and checkpoints are pending.
