# Desktop backup dialog compact layout

## Goal

Keep the backup review dialog usable at its documented 480x460 compact size,
including a readable preview and visible actions when native Tk font metrics are
larger.

## Area and constraints

- `utterleaf/backup_ui.py` and the focused `tests/test_backup_ui.py` geometry test.
- Preserve explicit selection, preview, cancel, overwrite refusal, import and
  export behavior. Keep the existing minimum size and keyboard focus order.
- Do not hide controls, weaken geometry assertions, add dependencies, or claim
  physical-device accessibility evidence from Tk tests.

## Acceptance and verification

At 480x460, the preview and primary action remain mapped, have usable geometry,
and stay within the dialog. Focus traversal continues to reach the action
controls. Run the affected backup tests and a local controlled Tk scaling check;
macOS CI remains the native-platform verification.

## Local evidence

The options now scroll within their own region while preview, status and actions
retain space below. The vocabulary privacy disclosure remains visible before
selection. Independent review checked the production diff and direct Tab
traversal at 480x460 with Tk scaling 1.0, 1.5 and 2.0. All ten backup tests pass,
including a focused check that every scrollable preference/vocabulary control
is revealed without moving the preview or actions. Owned-window renders at the
default size and compact scaling 1.0/2.0 were visually reviewed.

The final combined local packaging, boundary, backup and settings check passed
78 tests in 20.31 seconds. Native macOS CI remains required; these local Windows
checks do not establish Aqua rendering or assistive-technology usability.

The completed implementation passed the native macOS test job, including all
backup tests, in [CI 34746938663](https://github.com/RioPlay/utterleaf/actions/runs/34746938663)
at tested HEAD `3f1bd6c`. All five matrix jobs passed. This satisfies the native
CI gate above; assistive-technology usability remains unverified. Desktop PR #26
merged into main at `bf4dfda`. The published RC2 tag remains separately recorded
as `90d2e147c6c84af2639317b427a2f5135b3ff997` and does not contain this later fix.

## Stop

Stop after the compact layout and its focused checks are reviewable. Do not
expand this slice into a general dialog framework or unrelated desktop UI.
