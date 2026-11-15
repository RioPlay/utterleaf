# Plans

Substantial in-flight work lives here so a new session can continue without the
previous chat. One-line fixes do not need a plan.

Start with [workspaces](../workspaces.md) and the platform roadmap's **Now**
section, not the first filename in `active/`. Desktop development is the current
focus; Android work is paused until a suitable pipeline is agreed. Android
alpha21 is published; its [release record](completed/android-alpha21-release-readiness.md) preserves the
exact promotion evidence. Its roadmap retains design follow-ups for resumption;
[physical issues are reported manually](completed/android-alpha18-phone-acceptance.md),
and a dedicated phone acceptance campaign is no longer required. The separate
[desktop modernization stream](active/desktop-modernization.md) is active, with
[0.4.6 RC5 release readiness](active/desktop-0.4.6-rc5-release-readiness.md)
tracking local candidate identity, correction staging, release checks, and the
publication boundary. The local RC5 archive and frozen CLI checks are prepared;
published Windows RC4 remains the latest public preview, and RC5 GUI acceptance
and publication remain open. Desktop
Windows accessibility work is isolated in the
[native presentation-shell plan](active/desktop-windows-accessibility-shell.md);
the proof remains opt-in until its UIA and assistive-technology gates pass. Desktop
OBS remains parked; on resumption refresh/check draft PR #37, followed by
sequential replay of #38–42 in its owning worktree. Other active
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

The latest completed bounded preview record is preserved under
[alpha21 release readiness](completed/android-alpha21-release-readiness.md). It
does not close the broader experience plan or its physical/accessibility gates.

An active plan should include objective, area, constraints, acceptance,
completed work, remaining work, validation, and unresolved risks. No calendar
estimates. Roadmaps remain the status authority; a plan is a working note.

When the work ships or is abandoned, move the file to `completed/` and point at
the roadmap or commit.
