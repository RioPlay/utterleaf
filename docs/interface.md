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
- Keep the page body within a readable maximum of 860 pixels at 96 DPI, scaled
  with Tk's text scale. Center that body on wide windows; narrow windows keep
  the available width and vertical scrolling.
- Dictation separates the app's applied settings at the last check from the
  selected draft model's local-file status. The app can report Ready, Idle,
  Listening, Processing, or Needs attention. “Ready · applied speech model loaded”
  requires a successfully loaded engine matching the applied model, requested
  device, compute type and language; the existing CPU fallback remains associated
  with that request. Installed files or an unsaved choice cannot establish it.
  Idle remains valid when that proof is unavailable. Ready does not establish
  microphone availability or the success of the next take.
  Dictation and Help name the **loaded model for applied settings** using the
  same runtime snapshot. Only matching successful-load metadata supplies this
  name; custom identifiers and paths become “Custom model.” “Not confirmed”
  means the check has no matching proof, not necessarily that no engine exists.
  This is not the model retained by an already-running take. Changing or saving
  the draft does not rewrite the last-check result; Refresh checks again.
  Opening Settings and explicit Refresh take a snapshot, with no added periodic
  checking. The app status query uses cached state without device enumeration,
  filesystem/model probing, or model loading. Only an explicit older-server
  response permits a legacy status check, with loaded detail marked unavailable.
  Authentication/transport failures and malformed replies never negotiate a
  fallback or display raw text. Checking and failures clear the previous claim;
  stale, duplicate and closed-window callbacks cannot restore it.
  On narrow/larger-text layouts, each status/model action moves below its text
  instead of squeezing that text into a narrow column. Wide layouts restore
  side-by-side actions without recreating controls or changing focus order.
- Background model loading and failure remain durable behind microphone opening,
  Listening, queued Processing, and newer errors. Brief result feedback returns
  to the model state when it expires. Warmups serialize and snapshot preferences;
  stale generations and completions after quit cannot publish. A later network
  opt-out is rechecked before native loading; it cannot cancel native work that
  already began. A later opt-in cannot broaden a queued request's permission.
- A microphone check proves only audio detection, never speech-model readiness.
  Refresh and Test must not compete for the same feedback. Changing input clears
  prior results; preserve the named selection even when it disappears. Between
  explicit takes, re-resolve the effective numeric route and reopen a changed
  OS default. Missing or duplicate named selections fail closed. Do not present
  this within-process route key as durable identity or background hotplug support.
- Lead device-list and model-download failures with impact and recovery. Keep
  bounded technical text behind an explicit, local Details action, warn before
  sharing it, and clear it on retry. Do not open an error dialog automatically.
- Use one human-readable speech-model name in summaries, download confirmation,
  and completion/error feedback. Describe language support without unmeasured
  performance recommendations. Model details exposes the last inspected draft's
  identifier, backend, expected folder, and missing files only on request; keep
  it distinct from download-error details. Preserve editable custom identifiers.
- Local model inventory is explicitly refreshed, not part of startup or idle
  polling. List guided installations with factual file state and setup file size;
  never equate these with active identity, load readiness, download size or
  reclaimable space. Keep previous results after a failed refresh and expose
  bounded error details only on request. Choosing an installation stages the
  model only; explain language/backend mismatches without changing other fields.
  Refresh and download callbacks use operation identity to reject stale work.
  Failed worker dispatch must release controls without claiming work ran.
- Stack form labels above their pickers and model download actions vertically
  when their natural widths no longer fit. Restore inline rows when space
  returns; resizing must not recreate controls or discard focus and drafts.
- Keep section reset scope explicit. Recording feedback may reset only the
  floating indicator, live preview and start/stop sounds; it stages changes and
  must not alter the global-reset flag, other drafts, models or vocabulary.
  Saving still applies every pending edit in the form.
- In a short window with larger text, keep every navigation destination intact.
  Show the optional sidebar privacy tagline only when it fits completely and
  restore it when height returns; do not clip it or hide privacy controls.

## Existing desktop tokens

These are the current values in `utterleaf/theme.py`, retained as the starting
point for modernization. Android app surfaces share the primary green, base
surface, primary text, and control surface; keyboard density stays independent.

| Role | Existing token / value |
| --- | --- |
| Brand action | `PRIMARY` `#83DA9A`, `ON_PRIMARY` `#102A1B` |
| Selection | `PRIMARY_CONTAINER` `#203C2D`, `ON_PRIMARY_CONTAINER` `#C1F2CD` |
| Base / recessed / raised | `SURFACE` `#171E20`, `SURFACE_LOW` `#101617`, `SURFACE_CONTAINER` `#283335` |
| Primary / supporting text | `ON_SURFACE` `#E5EEE8`, `ON_VARIANT` `#AABCB1` |
| Borders / disabled | `OUTLINE_VARIANT` `#35483D`, `OUTLINE` `#71897B` |
| Error text | `ERROR` `#FFB4AB` |
| Type hierarchy | System family; title 22 bold, section 13 bold, body 10, support 9, primary action 10 bold |
| Spacing rhythm | Fine 4–6, controls 8–12, groups 16, page inset 24–26 pixels |

Use flat sections and native control geometry. Rounded status pills and app
badges already have distinct roles; the page does not need additional decorative
containers. Status copy remains authoritative and uses non-color cues.

Within Settings, Alt+1–5 (Command+1–5 on macOS) navigates the five destinations;
F1 opens Help. Ctrl+F (Command+F on macOS) opens local Settings search; a visible
Find setting button offers the same action. It searches static labels, sections
and curated help terms, never preference/editor values. The five primary
destinations stay visible. Enter opens a result and reveals its existing control;
dependent controls explain their prerequisite without changing it. Escape first
dismisses search, clears its ephemeral query and restores focus. The shortcut
runs before native editor caret bindings, only within this Settings window.
The Help page lists search, navigation, Save, Close, and focus shortcuts.
Page Up/Down and Home/End scroll long pages when focus is on the sidebar, a
button, or another non-editing page control. Text editors, entries, pickers,
and sliders retain their native keys; modified shortcuts are not intercepted.
These bindings do not register global shortcuts or change dictation activation.
When a text editor is taller than the visible page, reveal its insertion or
validation line instead of trying to fit the entire editor. Follow local cursor
input, including held-arrow repeats, without adding a background monitor. The
read-only device report participates in Tab order but does not accept edits.

File transcription, decoder setup and automatic-dictation review use the same
native control styling. Their fixed action rows wrap at measured control widths;
long content scrolls instead of pushing actions outside the existing minimum
window size. Read-only transcript previews participate in Tab order and retain
native text navigation. Page Up/Down and Home/End scroll the surrounding content
from ordinary action buttons; inner text/scrollbar input stays local. Layout is
event-driven, with coalesced idle geometry work rather than periodic polling.

Backup review retains separate scrollable choices and a read-only preview. Its
choices, vocabulary controls and action row wrap at their natural control widths;
Tab and Shift+Tab leave the preview in logical order. Copy wraps to allocated
width rather than widening the dialog. Layout must not rebuild the import review,
change selection, alter overwrite protection or imply confirmation.

Icons & artwork keeps five stable reference tabs with concise labels: Tray,
Badges, Marks, Utterling and Wordmark. Page Up/Down and Home/End scroll the
selected reference without replacing notebook traversal or native editing keys.
Wrapped text and a fixed action row keep Export and Close available at the
existing minimum size. Export feedback is inline, with bounded technical Details
only on request. Closing cancels the UI poll, not an already-consented export;
late results cannot reopen the window. Artwork generation and atomic archive
replacement are unchanged.

Help's device-report and GPU-guidance checks share a single operation. A failure
retains the previous read-only report and selection; a stale completion
cannot replace a newer operation or update a closed window. Checks use saved
configuration and leave drafts untouched. Inline recovery and explicit Details
reveal together without moving focus or changing the current page. Report export
snapshots the chosen preview before the native picker, preserves cancellation
and blocks reentrant writes. Its existing direct file write is not atomic, so
failure copy must not promise an unchanged destination. No automatic sharing,
new probing or additional polling is introduced.
If a newer report arrives while the native save picker is open, feedback
distinguishes the earlier exported report from the newer visible preview.

Microphone refresh/test and app-status refresh distinguish dispatch failure from
a completed check's error. Each restores its existing controls and busy flag,
with safe retry copy; initial background failures still finish constructing
Settings. Microphone technical text remains in explicit Details, while the
app-status surface retains safe text only. No probe, recording or IPC action
runs for a worker that did not start, and no automatic retry or polling is added.
Selection, drafts, Stop, input-change cancellation and close behavior are retained.

Settings saves keep their native alert, with confirmed Saved / Not saved /
Not attempted progress and retry guidance. Unknown progress is explicitly
uncertain. Raw causes stay behind an error-only **Save details…** footer action;
its bounded text is local and may contain private paths. Retry, new edits,
defaults and close clear obsolete details. A failed app-notification step does
not erase confirmed local writes or partial progress. Successful writes update
the captured baseline even when notification fails; later edits remain unsaved.
Save-start failure restores controls, and stale/closed callbacks are ignored.
Storage order, staged reset and validation are unchanged; there is no implied
multi-file transaction or automatic retry.

File transcription/export and decoder setup failures use the shared recovery
pattern: problem, impact, next action, and an explicit Details button. Raw
exceptions are not primary copy. Details are bounded, control characters are
removed, and changing status or closing clears obsolete details. Technical text
can still contain private paths; it stays local and is never automatically
exported or copied. Export failure keeps the preview for retry without claiming
that the destination was untouched. Native Details dialogs retain a separate
accessibility acceptance gate.

## Platform evidence

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

Use `python tests/capture_settings.py` for real app screenshots with sample data,
deterministic presentation states, and no microphone, model download, network
operation, or personal config writes. Output lives under
`artifacts/screenshots/desktop-baseline`; see the
[baseline inventory](desktop-ui-baseline.md#deterministic-capture-inventory).
Inspect results before replacing images in `docs/assets/screenshots`; mocked
presentation states are visual evidence only and must not be presented as native
device or save-flow acceptance. Do not append outdated variants to the gallery.
Keep the README to one app screenshot and clear download/setup links. Detailed
screens belong in the gallery, and historical investigations stay marked as such.

Use the primary wordmark on light surfaces and the inverse on dark surfaces.
GitHub's README selects the appropriate image with a `picture` element. Keep
text descriptions and useful links available without images.
