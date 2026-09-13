# A calm place to set up your voice

[Documentation](README.md) · [Brand & assets](branding.md) · [Screenshots](screenshots.md)

Utterleaf is a dictation utility. Settings should make it easy to choose an input,
try a microphone, and return to the document. Keep new modes and technical options
out of that everyday path until they serve a clear user need.

## Shared design

- Charcoal surfaces separate the page, grouped controls, and sidebar. Green marks
  the selected section and primary action; it does not fill every surface.
- Use one section per decision: shortcut, microphone, feedback, model, or recovery.
  Keep labels close to controls. Put the consequence of a setting in plain text.
- Keep Save and Close visible while the page scrolls. Opening Settings again
  preserves the same window and unsaved form. Defaults remain a staged action.
- Use the approved inverse wordmark on the dark sidebar. Utterling decorates
  page headings and microphone feedback; text must explain every meaningful state.
- Page titles name the task directly. Keep the mascot secondary at 80 pixels,
  focus and selection marks visible, and control labels readable without knowing
  config tokens. Validation should return users to the field needing attention.
- Keep the five navigation destinations stable: Dictation, Vocabulary, Voice
  commands, Speech & privacy, and Help. Recovery comes before artwork in Help.
- Retain keyboard navigation, focus indication, readable contrast, and system
  scaling. Check the compact 760 × 560 layout as well as the default window.

On Windows, the current Tk settings window has a known UI Automation limitation:
many controls may be exposed by the OS as unnamed panes even though their visual
labels are present. Treat screen-reader and broader UI Automation acceptance as
an explicit manual gate; source screenshots and Tk tests do not establish it.

The current UI is Tkinter/ttk, styled in `utterleaf/theme.py`, with layout in
`utterleaf/settings_ui.py`. It uses the existing Pillow dependency for bundled
artwork. This refresh adds no UI package, web runtime, remote fonts, or animation
loop. A future toolkit change should be justified by accessibility or platform
integration needs and validated against the same behavior.

The [product quality audit](product-quality.md) records scrutinized decisions,
regression evidence, and remaining native-platform/accessibility work.

## Documentation and screenshots

Use `python tests/capture_settings.py` for real app screenshots with sample data
and no personal config writes. Inspect the results before replacing the images
in `docs/assets/screenshots`; do not append outdated variants to the gallery.
Keep the README to one app screenshot and clear download/setup links. Detailed
screens belong in the gallery, and historical investigations stay marked as such.

Use the primary wordmark on light surfaces and the inverse on dark surfaces.
GitHub's README selects the appropriate image with a `picture` element. Keep
text descriptions and useful links available without images.
