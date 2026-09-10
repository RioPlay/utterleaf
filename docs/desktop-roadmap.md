# Desktop roadmap

[Roadmap hub](roadmap.md) ? [Mobile roadmap](mobile-roadmap.md)

Scope: Windows, macOS, and Linux desktop application only.

Updated September 9, 2026. Priorities follow the
[offline STT user research](offline-stt-user-research-2026-09-08.md).
This is an ordered development plan, not a promise of release dates.

See [platform testing](platform-testing.md) for current Windows/WSL results and
the real-device checklist, including macOS testing.

The product goal is simple: press a key, speak, and get dependable text in the
intended field, with understandable local processing and minimal interruption.

## Foundation implemented

- Local recognition and cleanup, with an option to preserve model output.
- One-key toggle recording; microphone released between takes.
- Bounded recording and queued takes, with explicit cancellation.
- Two-minute in-memory recovery, explicit forgetting, and recovery CLI commands.
- Conservative native-field editing and manual fallback when edits cannot be verified.
- Clearer settings, shortcut validation, and partial-save error reporting.
- Dark Settings, optional overlay with countdown, tray-only defaults, and all seven Utterlings in normal UI use (v0.3.3).
- Multiword list fixes and local timing diagnostics (v0.3.3).

## Current delivery status

**Version 0.3.7 usability audit:** direct task headings, compact decorative art,
visible selection/focus marks, responsive footer messages, readable hardware
choices, and validation that returns to the invalid field. The
[quality audit](product-quality.md) records evidence and outstanding platform,
accessibility, and display-scaling checks.
The same release authenticates local control commands and preserves offline and
clipboard preferences during defaults recovery. Security first, privacy second, and convenience third guide
remaining work; all three matter. These priorities take precedence over speed of delivery for remaining roadmap decisions.

**Version 0.3.6 interface and documentation refresh:** grouped Settings controls,
charcoal surfaces, the approved sidebar wordmark, recovery-first Help, and updated
screenshots. A [documentation index](README.md) separates current guides from
historical investigations. [Interface guidelines](interface.md) keep future work consistent.

**Version 0.3.5 changes:** one Settings window per configuration, staged defaults
recovery under Help, and a current Help screenshot. Wayland fixes exclude misleading X11 paste
fallbacks, avoid stale XWayland focus queries, and explain missing desktop setup
in diagnostics. [Wayland setup](wayland.md) documents current limitations.
Native GNOME/KDE/wlroots delivery validation and portal integration remain needed.

**Microphone recovery release:** [v0.3.4](https://github.com/RioPlay/utterleaf/releases/tag/v0.3.4).
Included: Windows shared microphone selection, a bounded retry for
temporary device-unavailable errors, and resetting toggle state after a failed
microphone start. These are included in v0.3.4, not v0.3.3.

**Version 0.4.0:** timestamped file transcription
with a review/export window and explicit TXT/SRT/VTT output, selective preference
and vocabulary backup, clipboard change-identity checks, and microphone interruption
recovery. These changes are not included in older v0.3.8 downloads.
See [file transcription](desktop-file-transcription.md) and
[backup and import](desktop-backup.md) for supported scope and remaining gates.

**Planned, not implemented:** long dictation without the fixed hold-mode cutoff,
system-audio captions, meetings, speaker
labels, and translation. See the [feature plan](feature-plan.md) for dependencies
and acceptance criteria, and [microphone troubleshooting](microphone-troubleshooting.md)
for current behavior and limits.

These are implemented capabilities, not proof of end-to-end quality on every platform.

## Privacy-first convenience milestones

Mobile keyboard development has its own [roadmap](mobile-roadmap.md),
build system, dependencies, acceptance gates, and release versions.

Each milestone must preserve explicit capture, bounded retention, offline use,
and actionable recovery. No accounts, passive listening, automatic transcript
archives, or background reading of other apps are required.

| Order | Deliverable | Acceptance gate |
| --- | --- | --- |
| 1 — active | Microphone recovery, safe delivery, clear readiness | Missing named inputs never open a substitute; reconnect/permission errors offer recovery. Test native device loss and editor delivery before broader reliability claims. Show loading/download/ready states and require explicit download approval. |
| 2 | Comfortable long dictation | Bounded RAM and queued processing, ordered text across chunk boundaries, cancel/discard, elapsed time and optional limits; no automatic disk recording. |
| 3 | Understandable speed choices | Local, user-requested measurements inform Faster/Balanced/More accurate choices; show actual engine/device and explain fallback. Never upload benchmark speech. |
| 4 | Vocabulary helper and selective backup | Explicit local vocabulary additions; preview exported preferences/vocabulary. Exclude recordings, transcripts, device-specific control tokens, and secrets. No contacts or clipboard-history scanning. |
| 5 | Local file transcription | Explicit file selection, text/SRT/VTT export and discard; handle missing models and media support without unexpected downloads. |
| Later | Captions, meetings, speaker labels, translation | Follow the [feature plan](feature-plan.md), with explicit session start, source selection, retention and export controls. |

Wayland desktop-managed shortcuts and safe insertion belong to milestone 1;
shortcut registration does not establish successful or correctly targeted paste.
Keep frequent actions in the tray, preferences in Settings, and repair tools in
Help. Use Utterlings for helpful status and recovery guidance without new popups.

First implementation in v0.3.8: exact saved microphone selection,
failure before capture when it is missing, and refresh guidance that preserves
the selection. Native hotplug recovery and device identity remain open work.

## 1. Reliable delivery — active

Implemented in the current pass: check focus after the shortcut-settling delay;
verify clipboard text before sending paste. If focus moved, leave dictation on
the clipboard. If the clipboard changed or cannot be read, cancel delivery and
retain the existing recovery path. Do not overwrite a user's intervening copy.

Remaining work:

- Preserve rich clipboard formats, not only plain text.
- Investigate restoration timing in slow applications.
- Distinguish sending a paste shortcut from observing successful insertion.
- Test browser fields, native and rich-text editors, terminals, and elevated apps.
- Test window and field changes, held modifiers, busy clipboards, and fast repeated takes.

Completion evidence: a documented OS/editor matrix with observed delivery and
recovery results, including Unicode and selected-text replacement. No unexpected
typing or loss of a newer clipboard copy in the tested scenarios. The final
focus check reduces a race; it cannot make desktop input atomic or detect every
field change inside the same window.

## 2. Effortless first run — next

- Make model availability and download requirements clear before recording.
- Verify interrupted-download retry and model changes after offline initialization.
- Exercise missing microphone permission, unplugged devices, and default-device changes.
- Verify useful CPU fallback when an accelerator cannot initialize.
- Check packaged first launch on a clean user profile without developer tools.

Completion evidence: a new user can reach a successful first dictation using the
visible UI; each failure above offers an actionable recovery without editing config
files. Test denied network access and offline relaunch with installed weights.

## 3. Measured speech quality and speed

- Measure cold start, time until listening, and end-of-speech-to-delivery p50/p95.
- Record CPU, RAM, model, engine, language, and audio conditions for each result.
- Include names, numbers, negation, accents, multilingual text, quiet speech,
  background noise, and silence in a consented or public evaluation set.
- Choose defaults from measured accuracy, responsiveness, and resource use.

Completion evidence: reproducible results on named ordinary CPU hardware, with
explicit accuracy/latency tradeoffs. Set performance budgets from that baseline.

## 4. Accessibility and desktop polish

- Test keyboard-only setup and recovery, screen readers, and high display scaling.
- Verify recording status and errors without relying on sound or color alone.
- Keep real Tk checks running in CI; investigate any unexpected display-related skips.
- Evaluate a different desktop shell only if measured usability, accessibility,
  startup, or packaging limits justify it. Keep the Python speech pipeline unless
  evidence identifies it as the constraint.

Completion evidence: documented accessibility results and release checks that run
reliably in the supported environments.

## Scope discipline

The new user-requested expansion is optional **Transcribe**, **Captions**, and
**Meeting** modes. These share the local speech engine while keeping ordinary
dictation quiet and lightweight. Meeting capture requires a deliberate session
start, clear capture state, and explicit save/discard behavior.

Cloud accounts, bundled chat, team workspaces, engagement statistics, and
automatic permanent recording history remain outside the plan. Optional models
should be installed only for features the user enables.

Live microphones, external editor delivery, clean-install packaging, and speech
benchmarks still require direct validation. Automated unit tests do not substitute
for those checks.
