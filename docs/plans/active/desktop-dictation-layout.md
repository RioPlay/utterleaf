# Desktop Dictation layout slice

## Goal

Make the native Tk Dictation settings page useful at compact Windows sizes by
putting the primary setup choices in a compact, readable overview.

## Area

`utterleaf/settings_ui.py` and the focused Settings UI capture/tests.

## Constraints

- Preserve existing local preference variables, save/cancel/reset behavior, and
  microphone test boundaries.
- Use the existing Tk/ttk stack, theme, wordmark, and Utterling artwork.
- Do not add audio telemetry, ambient capture, dependencies, or framework work.
- Keep secondary recording and startup controls scrollable below the overview.

## Acceptance

- At 770x655, shortcut, microphone selection/status, activation, output style,
  and stop-after-speech controls are grouped above the secondary sections.
- Output style is represented once on the Dictation page and remains persisted
  through the existing `output_format` variable and save/reset flows.
- Focus traversal, combobox anchoring, and wrapped labels remain usable at
  compact sizes.
- Canonical no-microphone screenshots and focused Settings/config tests pass.

## Verification

- `\.venv\Scripts\python tests/capture_settings.py`
- `\.venv\Scripts\python -m pytest tests/test_settings_ui.py tests/test_config.py -q`

## Non-goals

Do not redesign the app shell, add a Start dictation action to Settings, mimic
PulseMix audio-mixer content, or claim installed-build screen-reader support.

## Status

Implemented in the assigned worktree. Source validation and screenshots remain
to be run before handoff.

## Limitations

Tk/ttk provides limited control over elevation, segmented controls, and Windows
UI Automation naming. Visual and keyboard checks do not establish full
screen-reader or physical-device accessibility acceptance.
