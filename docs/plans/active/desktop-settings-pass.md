# Desktop Settings bounded improvement pass

## Goal

Make the native Tk Settings window keep focus and popup geometry stable at the
compact Windows size, and keep explanatory copy readable without changing the
UI framework.

## Area

`utterleaf/settings_ui.py`, focused settings UI tests, and desktop documentation.

## Constraints

- Preserve all existing user edits and Android work.
- Do not rebuild distributions, change personal settings, or edit installed builds.
- Do not add a new UI framework or change unrelated desktop behavior.
- Keep audio tests mocked or explicitly discard test audio; no ambient recording.
- Separate source/test evidence from observations of the downloaded CPU build.

## Acceptance

- Opening a shortcut dropdown at the initial scroll position does not move the
  page or detach the popup from its field.
- The first click on a microphone control, device check, or radio button keeps
  activation; keyboard focus can still reveal an actually off-screen control.
- Vocabulary explanatory labels are fully rendered at 770x655 and remain
  scrollable at compact sizes.
- Focused settings tests and the no-microphone screenshot check pass.
- Documentation records source evidence separately from installed-build
  evidence, including UI Automation naming limitations and unverified live
  dictation/paste/persistence/accessibility behavior.

## Validation

- `\.venv\Scripts\python -m pytest tests/test_settings_ui.py tests/test_config.py -q` passed.
- `\.venv\Scripts\python tests/capture_settings.py` passed and refreshed the
  no-microphone screenshots in `artifacts/screenshots`.
- The focused source checks cover popup anchoring, first-click button
  activation, focus reveal above and below the viewport, and compact vocabulary
  label sizing.
- Independently supplied cleanup/polish validation passed 175 tests; this is
  source-only evidence, not installed live-speech proof.

## Remaining limitations

Independent review reran the final settings/config changes: 37 passed in 21.59s
with `.\.venv\Scripts\python -m pytest tests/test_settings_ui.py tests/test_config.py -o addopts='' -p no:cacheprovider --basetemp '.grok/pytest-readiness-unrestricted-20260912-1211' --tb=short`.
The restricted-shell attempts encountered temporary-folder access errors; the
unrestricted run with a fresh local test folder passed. The reviewer identified
an incorrect scroll-fraction denominator in the first patch; the final patch
uses the full scrollregion and passed the strengthened focus tests.

Installed-build live dictation, paste delivery, persistence across relaunch,
reset, and screen-reader/accessibility acceptance remain unverified. Windows UI
Automation may expose visually labelled settings controls as unnamed panes.

## Stop

Stop after the focused source fix, tests, screenshots, and documentation review.
Do not expand into a framework rewrite, packaging, or unrelated desktop/mobile
work.
