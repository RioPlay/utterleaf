# Android alpha18 phone acceptance

## Goal and area

Verify the signed alpha18 candidate on the reported Pixel 8 Pro/GrapheneOS and
named everyday editors before claiming comfortable daily use. This is the next
Android product gate after signing; no physical phone is connected to the current
development session. Status remains in the [mobile roadmap](../../mobile-roadmap.md).

## Constraints

Use synthetic text for recorded evidence. Keep screenshot protection enabled;
do not record personal typing, passwords, clipboard contents or microphone input
without an explicit test action. Preserve installed preferences and models. Test
an in-place signed update; do not uninstall the user's existing signed preview.
Record emulator and physical results separately. Expand code only for a reproduced
failure with a bounded fix and regression check.

## Acceptance journey

1. Record phone, exact OS/build, APK version/checksum, navigation mode, font/display
   size and editor names/versions. Verify the signer and update from alpha17.
   Confirm the user's existing theme/layout, voice preference and model selection.
2. In practice, messaging and browser fields, type `hello world`, repeated letters,
   punctuation and `zzzzq`. Move the cursor into the first word, select text,
   delete/retype, tap a valid completion, switch symbols, and hide/reopen the IME.
   Check exact output, stable key positions and responsiveness. Password/raw
   fields must retain their restrictions.
3. Change theme, alignment and letter layout, then return to the original choice.
   Verify immediate preview updates. Try voice and preview quick controls, then
   Cancel and reopen. Confirm Reset followed by Cancel preserves preferences;
   Reset followed by Apply restores defaults while keeping models.
4. Repeat navigation and typing in portrait/landscape, with gesture and
   three-button navigation and large text. Check bottom spacing, reachable Apply,
   practice scrolling, Back behavior and pending preferences across rotation.
5. With TalkBack and Switch Access, traverse categories, choices, suggestion
   chips, toolbar, Apply/Cancel and Reset. Record missing labels, focus loss or
   gesture-only paths. Visual captures alone do not close this gate.
6. Test app/field switches and interruptions. Verify the real Obtainium update
   route and preference/model retention separately from emulator installation.

## Evidence, verification and stop

For each journey record pass/fail/unperformed, exact reproduction, expected and
observed output, and the tested configuration. Measure touch-to-text latency only
with a repeatable method and synthetic text; no subjective observation becomes a
P50/P95 claim. Source fixes use the AGENTS.md Android validation ladder and their
own focused instrumentation, then exact-revision CI before another candidate.

All physical checks are currently **unperformed**. Stop this gate when the named
journeys are recorded and blocking failures are fixed or explicitly documented.
No new prediction/swipe engine, language expansion or desktop work belongs here.
