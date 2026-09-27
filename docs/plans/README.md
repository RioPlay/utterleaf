# Plans

Substantial in-flight work lives here so a new session can continue without the
previous chat. One-line fixes do not need a plan.

Start with [workspaces](../workspaces.md) and the platform roadmap's **Now**
section, not the first filename in `active/`. Android alpha19 is published;
continue the roadmap design follow-ups and report physical issues through the
[manual issue path](completed/android-alpha18-phone-acceptance.md). The separate
[desktop modernization stream](active/desktop-modernization.md)
is active, with [0.4.6 RC3 release readiness](active/desktop-0.4.6-rc3-release-readiness.md)
tracking candidate identity, packaging, CI, and the publication boundary. Desktop
OBS remains parked; on resumption refresh/check draft PR #37,
followed by sequential replay of #38–42 in its owning worktree. Other active
plans retain longer-running work or acceptance gates; they are not permission
to start a different feature. Completed records preserve historical evidence
and point unresolved device/release limits back to the roadmaps.

| Location | Use |
| --- | --- |
| [active/](active/) | Work still open |
| [completed/](completed/) | Finished work; keep the note short |

The current cross-milestone Android contract is the
[capability and experience plan](active/android-experience-refresh.md); its
[compatibility and performance template](../android-keyboard-compatibility.md)
records evidence without treating unrun checks as results.

The current bounded preview is being prepared under
[alpha20 release readiness](active/android-alpha20-release-readiness.md). It
freezes the existing feature set for verification; it does not close the broader
experience plan or authorize publishing without the recorded release gates.

An active plan should include objective, area, constraints, acceptance,
completed work, remaining work, validation, and unresolved risks. No calendar
estimates. Roadmaps remain the status authority; a plan is a working note.

When the work ships or is abandoned, move the file to `completed/` and point at
the roadmap or commit.
