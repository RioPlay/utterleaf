# Utterleaf roadmap

Updated September 8, 2026. Priorities follow the
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

These are implemented capabilities, not proof of end-to-end quality on every platform.

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
- Resolve the Tk test-order initialization issue so UI checks cannot silently skip.
- Evaluate a different desktop shell only if measured usability, accessibility,
  startup, or packaging limits justify it. Keep the Python speech pipeline unless
  evidence identifies it as the constraint.

Completion evidence: documented accessibility results and release checks that run
reliably in the supported environments.

## Scope discipline

Cloud accounts, bundled chat, meeting workspaces, engagement statistics, and
permanent recording history are not planned priorities. New features should make
everyday dictation more dependable without adding unnecessary setup or retention.

Live microphones, external editor delivery, clean-install packaging, and speech
benchmarks still require direct validation. Automated unit tests do not substitute
for those checks.
