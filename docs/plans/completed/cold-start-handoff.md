# Cold-start documentation refresh

## Goal and area

Make the main checkout's workspace table, roadmap hub and platform roadmaps
identify the actual next work without chat context. Archive completed increments
and create the alpha18 signed-candidate contract.

## Constraints and non-goals

Documentation only. Preserve historical test scope and open physical-device,
editor, accessibility and release gates. Do not rebase or merge the OBS stack,
change runtime code, sign an APK, prune worktrees or publish a release here.

## Acceptance and verification

- Workspace/roadmap entry points identify merged PR #36, next PR #37 and the
  sequential replay requirement for #38–42.
- Alpha17 remains published; alpha18 has an active release contract.
- Completed plans have completion receipts and working inbound/relative links.
- Verify GitHub PR/release state using `gh pr view`, `gh pr list`,
  `gh release list` and `git ls-remote`; check documentation with
  `git diff --check`, a relative Markdown link audit and stale-reference search.

## Completion and stop

September 18: checked against main `aa296c9`. PR #36 merged; its remote branch
is absent. PR #37 is draft, green and mergeable; #38–42 retain stacked parents.
PR #54 has no check runs. Alpha17 is the latest Android preview. The refreshed
documents record these facts and preserve unresolved acceptance limits.
Stop after documentation validation; platform implementation belongs in its
own workstream.
