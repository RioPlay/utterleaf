# Compact desktop Dictation settings

## Completion - September 18, 2026

Merged through PR #31 (03a1c9b); all five desktop jobs passed in CI 34750749369. This source follow-up is not in the immutable RC2 binary.

This bounded increment is closed. The evidence below is historical; earlier
pending/unreleased statements describe that stage, not current work. Physical,
editor and accessibility limits remain open in the [platform roadmap](../../desktop-roadmap.md).

Status: source integrated through PR #31 at `03a1c9b`. Exact-source CI run
[34750749369](https://github.com/RioPlay/utterleaf/actions/runs/34750749369)
passed all five desktop jobs at `76f448c`. This source change is not in the
published RC2 binary; physical display and assistive-technology follow-up remains.

## Goal and area

Keep everyday Dictation settings easy to find at 770x655 without reducing the
user's font size. This slice changes `utterleaf/settings_ui.py`, focused settings
UI tests and captures, the user guide and desktop roadmap.

## Constraints

Preserve Tk/ttk, Utterleaf artwork and theme, local preferences, microphone-test
boundaries, save/cancel/reopen/reset behavior, and fixed Save/Close controls.
Sidebar spacing and short local-processing copy must remain readable at larger
font metrics.
Add no recording, telemetry, dependencies, or Android changes. Published RC2
remains immutable; these are later source changes.

## Acceptance

- At the current Windows default font metrics and 770x655, shortcut, activation,
  microphone selection/status, output style and the speech-end toggle are visible.
- At 760x560 and larger text metrics, controls remain readable and focus reveals
  them through scrolling. Shortcut/microphone groups stack when they need width.
- Output style appears once on Dictation; validation returns to its control.
- Dropdown anchoring and first-click activation remain stable. Long microphone
  status text and repeated compact/wide resizing settle without layout loops.
- Save, discard, reopen and staged defaults retain the existing behavior.

## Verification

From the owning worktree, use the desktop development environment and scope
`PYTHONPATH` to that checkout:

```powershell
$env:PYTHONPATH=(Get-Location).Path
python -m pytest tests/test_settings_ui.py tests/test_config.py -q
python tests/capture_settings.py
```

No microphone is used by these checks. Default, compact and larger-font captures
must be inspected separately from physical display-scaling or screen-reader
acceptance.

## Status

The notes below record verification before the final CI and integration above.

The prior partial work was checkpointed at `20ed5fa`, then main was merged cleanly
at `330f9de`. The revised overview retains default font sizes, responsive columns,
wrapped microphone feedback and existing speech-end privacy explanations. Output
style moved from Vocabulary to Dictation, including validation focus. A regression
check caught and fixed a radio-button validation crash and a one-pixel wrapped-label
resize loop. The final focused settings/configuration suite passes **49 tests** with no skips
in 24.53 seconds. Canonical no-microphone captures pass. The 770x655 render uses
the current Windows default Tk scaling of 1.33399; additional controlled font
captures use 1.5 and 2 times that value. Input groups, focus reveal, microphone
Test/Stop/retry, wrapped hints and the sidebar disclosure pass their geometry
checks. Independent review is clear. CI remains the source integration gate.

CI at `4e829ff` passed Windows/Linux checks and all three builds, but macOS
job `103703425241` hung in the first Settings constructor's `update_idletasks`
and reached its 15-minute limit. The candidate correction gives expanding hint
labels a fixed minimal requested width: wrapped text can request height but
cannot feed a new width back into its own columns. A new regression fails under
the prior behavior and passes with the fix; all **50 focused tests** pass locally
without skips. Fresh default/compact renders were inspected and independent
source review cleared the correction. Actual macOS CI remains required; this
Windows evidence does not establish the macOS fix.

The corrected `ce3a61c` run completed macOS Settings tests without hanging; its
only failure was a clipboard test invoking the real macOS foreground helper
against a simulated clipboard. That helper's polling repeated the mocked copy
event. The fixture now supplies a simulated editor identity as well, preserving
its exact clipboard and no-dispatch assertions. All 30 injection tests pass
locally; complete corrected CI remains required before integration.

The refreshed documentation screenshots show the source layout, not the published
RC2 binary. Local capture receipts are `root-native-1.png`, `root-native-1.5.png`
and `root-native-2.png` under `.grok/desktop-dictation-layout/`.

## Non-goals and stop

Do not redesign the app shell, add new recording modes, change the UI framework,
or expand into live OBS or Android. Stop after the named source checks, inspected
captures, accurate documentation and independent review. Tk UI Automation naming
and physical assistive-technology acceptance remain separate roadmap gates.
