# Compact desktop Dictation settings

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

The refreshed documentation screenshots show the source layout, not the published
RC2 binary. Local capture receipts are `root-native-1.png`, `root-native-1.5.png`
and `root-native-2.png` under `.grok/desktop-dictation-layout/`.

## Non-goals and stop

Do not redesign the app shell, add new recording modes, change the UI framework,
or expand into live OBS or Android. Stop after the named source checks, inspected
captures, accurate documentation and independent review. Tk UI Automation naming
and physical assistive-technology acceptance remain separate roadmap gates.
