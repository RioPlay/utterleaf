# Skip desktop CI on Android-only changes

## Goal

Stop Android keyboard PRs from packing the Windows/macOS/Linux matrix. Desktop
CI stays on desktop source, packaging, native OBS, and shared brand/README
changes. Android CI stays on `mobile/android` and its workflow.

## Area

`.github/workflows/build.yml`, `docs/development-boundaries.md`,
`docs/development.md`, and `tests/test_repo_boundaries.py`.

## Constraints

Do not change Android emulator/voice job scope in this patch. Do not require
always-present checks; main has no branch protection. `v*` tags keep using the
same desktop workflow; an android-only commit tagged `v*` would already skip
and remains an unlikely desktop-release case. Do not delete branches or
worktrees here.

## Acceptance

A PR whose files are only `mobile/android/**`, Android guides/plans, and
`docs/workspaces.md` does not start `build.yml`. Changing `utterleaf/`,
`tests/`, `packaging/`, or `build.yml` still does. The boundary test names the
ignore list.

## Remaining

Android `android.yml` still downloads speech models and runs the full emulator
suite on every Android source PR. Split that only in a follow-up. Remote merged
topic branches and stale worktrees are listed in the cleanup inventory, not
deleted by this patch.
