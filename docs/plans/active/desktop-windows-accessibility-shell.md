# Windows accessibility presentation shell

## Goal

Give Windows screen readers and other assistive technology a complete, stable UI
Automation tree for every shipped Utterleaf desktop surface while retaining the
existing speech, privacy, configuration and persistence behavior.

## Area

- New Windows-only presentation code under `utterleaf/windows_ui/`.
- A UI-neutral Settings controller shared by the existing Tk and Windows views.
- Windows dispatch and packaging only after an opt-in prototype passes its gates.
- Out-of-process UI Automation acceptance checks and manual Narrator/NVDA evidence.

Tk remains the macOS/Linux presentation layer. The existing Python recognition,
audio, model, configuration, authenticated local-control and persistence modules
remain authoritative on every platform.

## Evidence and decision

The September 27, 2026 Windows audit inspected 12 current Tk surfaces. Each
exposed a named top-level Window followed only by unnamed Pane descendants, with
zero UIA-focusable or named-focusable controls. Keyboard operation and visual
labels therefore do not establish Windows accessibility.

A Tk bridge is rejected as the release path. A correct custom provider would
need a COM fragment tree, stable runtime identities, focus and property events,
thread-safe lifetime handling, hit testing, and Invoke, Toggle, Value, Selection,
ExpandCollapse, Text and Scroll patterns. Property annotation alone cannot supply
those missing interaction patterns. A client-side proxy would also require every
assistive-technology client to install Utterleaf-specific support.

The first experiment is a same-process Windows shell made from standard Win32
controls through the Python standard library. Microsoft documents UIA client-side
providers for those controls. This introduces no network, telemetry, broker,
elevation, new IPC surface or third-party runtime. It is a presentation-layer
experiment, not a speech-engine rewrite. WPF/WinUI remains the fallback if a
frozen, version-6 common-controls build cannot expose the documented providers.

An isolated development-host prototype created real Static, Button, Edit and
ComboBox HWNDs and passed local draft, action and repeated-teardown checks. The
out-of-process .NET UI Automation client nevertheless reported the children as
non-focusable Pane elements with no interaction patterns. The prototype was not
wired into the product and its dead-end source was removed. Microsoft documents
those Win32 providers as client-side proxies and full support as dependent on
version 6 common controls, so the next bounded check is an instrumented frozen
executable with the release manifest and an independent native UIA client. If
that still lacks semantics, reject raw Win32 and proceed to a server-side-provider
framework such as WPF; do not add a product-specific client proxy.

## Constraints

- Security first, privacy second, convenience third.
- Never expose hidden pages, clipboard contents, OBS secrets, raw exception text
  or undisclosed diagnostics through UI Automation.
- UIA actions must use the same validation, consent and disabled-state guards as
  the current interface.
- No microphone access, model load/download, network access or preference write
  merely from opening the shell or running its automated audit.
- Save, cancellation and Reset to defaults retain current semantics. Reset must
  not remove model files or user data.
- Do not switch the product default, remove Tk, or claim Windows accessibility
  until all shipped Windows surfaces and recovery dialogs meet acceptance.
- No Android changes, release publication, signing or unrelated visual redesign.

## Staged acceptance

### Stage 1 — isolated proof

- Reproduce the standard-control experiment from a frozen, version-6
  common-controls executable and inspect it with an independent native UIA client.
- If those documented providers are absent, stop the raw-Win32 route and record a
  WPF packaging/runtime proof before creating product UI.
- An opt-in, non-default shell opens a named top-level window with stable
  navigation, a Dictation page and explicit Save, Cancel and Reset controls.
- Controls are standard Windows Button, Edit, ComboBox and CheckBox controls.
- A separate UIA client sees human-readable names, correct control types,
  keyboard focus, enabled state and appropriate Invoke, Toggle, Value and
  Selection patterns.
- Hidden-page controls are absent from the UIA control view.
- Repeated open/close leaves no window, thread or process behind.

### Stage 2 — shared behavior

- Extract a UI-neutral Settings draft/controller and Save outcome.
- Existing Tk behavior delegates to it with no persistence, validation,
  cancellation, reset, model/language or device regression.
- The Windows proof uses the same controller and cannot bypass product guards.

### Stage 3 — complete Settings and recovery

- Dictation, Vocabulary, Voice commands, Speech & privacy and Help are complete.
- Search, unsaved changes, downloads, device failures, errors, Details and
  confirmation dialogs expose appropriate UIA semantics and focus behavior.
- Focus order, announcements, large text, minimum size and mixed-DPI behavior pass.

### Stage 4 — remaining shipped surfaces

- File transcription, decoder setup, backup, appearance, OBS pairing, review and
  indicator interaction are migrated or supplied with an equally complete native
  provider.
- Packaging, startup, idle CPU/memory and process-family shutdown stay within the
  existing release gates.

### Stage 5 — release acceptance

- Automated out-of-process UIA checks pass in Windows CI and the frozen package.
- Manual Narrator and NVDA flows pass on a physical Windows system.
- The complete desktop regression, package smoke and documented physical display
  matrix pass at the exact candidate revision.

## Verification

- Focused unit tests for the native control tree and shared controller.
- Out-of-process Windows UIA inventory and interaction tests.
- Existing Settings/config/model/device/privacy tests, then full desktop pytest
  when the shared controller or dispatch changes.
- Fresh Windows onedir build and full frozen smoke after packaging integration.
- Repeated lifecycle plus idle CPU/memory measurement.
- Manual Narrator, NVDA, text scaling and mixed-monitor DPI acceptance.

## Non-goals

- Rewriting the speech engine or configuration format.
- Visual parity across Windows, macOS, Linux and Android.
- A custom UIA framework, client-side proxy, web view or remote settings service.
- Treating synthetic UIA checks as screen-reader certification.

## Stop

Keep the proof opt-in until Stage 1 and Stage 2 pass. Stop and select WPF if the
release-manifest/native-client check still reports standard controls as panes, or
if the required interaction would need substantial custom controls or a bespoke
accessibility provider. Release only after Stages 3–5 pass at one immutable
candidate revision.
