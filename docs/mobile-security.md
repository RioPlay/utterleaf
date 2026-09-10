# Mobile keyboard security design

[Mobile roadmap](mobile-roadmap.md) · [Development boundaries](development-boundaries.md)

This document describes **alpha05**, released as a signed preview.
[CI run 34432378047](https://github.com/RioPlay/utterleaf/actions/runs/34432378047)
passed 4 JVM, 32 API 35 emulator and 3 release-contract tests; the emulator report
has zero failures and zero skips. Physical and accessibility acceptance remains open.

## Foundation decision

The initial keyboard uses independently written Kotlin and native Android buttons,
alongside the existing pinned whisper.cpp engine. No FUTO/HeliBoard keyboard code,
models, artwork or layout assets have been imported. This preserves the existing
Apache licensing of Utterleaf's code and avoids taking on an unaudited keyboard fork.
It is a small testable foundation, not evidence of mature predictive typing or full
accessibility. Reevaluate a maintained keyboard engine before expanding prediction,
multilingual composition and swipe input; document provenance before importing it.

## Assets and trust boundaries

| Boundary | Policy / mitigation | Remaining evidence |
| --- | --- | --- |
| Editor ↔ IME | Android binds exported IME services through BIND_INPUT_METHOD. No surrounding-text collection, persisted keystrokes or clipboard history. Field lifecycle clears speech and one-shot modifier state. Optional terminal controls use InputConnection key events. | Real-editor selection, cursor, terminal shortcuts and field-switch tests across apps; dispatch success does not prove editor handling |
| Microphone ↔ inference | Explicit activation, runtime permission, bounded memory, capture cancellation; no saved audio or network fallback | Physical Bluetooth/call/revocation and low-memory tests |
| Document provider ↔ model store | Explicit file picker; tiny.en/base.en/small.en allowlist; selected file size and full SHA-256 checked before atomic replacement; private no-backup storage | Import bounds/rollback and tiny.en/base.en fixture inference passed CI; small.en inference and physical memory/performance unverified; each additional model needs review |
| Preferences ↔ keyboard | Only explicit booleans for appearance/touch/feedback, number row and terminal controls; no entered text, editor identifiers or secrets | Imported layouts/preferences are not supported until validated and bounded |
| Build ↔ release signer | CI artifact identity and successful run checks; main-only signing environment; certificate pin, version progression, non-debug APK and installation checks | Offline signing backup, version-to-version physical updates and stronger supply-chain attestation |
| GitHub ↔ Obtainium | Android title/APK filters; stable package and signer; no in-app network updater | Real Obtainium import/update acceptance |

Password fields support ordinary typing in the keyboard but disable speech. The
auxiliary voice-only provider continues to reject password fields. Future learning,
prediction, read-back and text shortcuts must explicitly respect sensitive-field
boundaries. Native accessibility exposure is necessary for assistive technology;
the keyboard does not request an accessibility-service permission or bypass the
user's operating-system accessibility configuration.

The IME windows use FLAG_SECURE, but setup/preferences contain only public state
and can be captured for documentation. No screenshot or log should contain actual
user input. The app cannot prevent a receiving editor, a compromised OS, or an
authorized third-party accessibility service from observing input at their boundary.

Screen-capture protection has no user-facing disable switch. The live keyboard
screenshots in these docs come from a synthetic debug editor: instrumentation
temporarily clears the secure flag and restores it in a `finally` block. That test
code and editor are excluded from release APKs. Capturing a keyboard for QA does
not require weakening the shipped keyboard's protection. See Android's
[window-security guidance](https://developer.android.com/security/fraud-prevention/activities).

## Model and terminal boundaries

The [model catalog](../mobile/android/README.md#english-speech-models) records direct
publisher links, exact byte sizes and SHA-256 hashes for three English GGML files.
Metadata was checked against the publisher's Git LFS pointers. A browser or
document provider may use the network; the ordinary app still has no Internet
permission, performs no model download and accepts no arbitrary native model.

Imports stream to a bounded temporary file, verify the full digest, sync it, then
atomically replace the single active model. Failure keeps the previous installed
file and removes temporary import bytes. A process-wide lease excludes recording
or inference during replacement. The existing private `tiny.en.bin` path is retained
for upgrade compatibility even when base.en or small.en is installed; unique file
lengths identify the previously verified private model. Length-based identification
is not an integrity check for external input: every import still requires its hash.
There is no claim of resistance to a compromised app sandbox or operating system.

The optional terminal layer sends balanced down/up events with soft-keyboard flags
and explicit modifier metadata. Ordinary printable input uses `commitText`; raw
terminal editors use the special-key route. Modifier state resets on field/panel
lifecycle changes. Failed dispatch does not replay text through another route,
which could duplicate input. No root, accessibility injection, surrounding-text
collection or persistent clipboard history is added. Receiving editors decide
whether Ctrl/Alt/Fn and navigation keys have an effect; real-terminal acceptance
remains open. Speech remains unavailable in raw terminal and password fields.

Alpha05 places system-bar/cutout padding on app content roots, with navigation
padding for the IME. Repeated inset delivery must not accumulate padding or clip
controls; the replacing Fn layer must keep all keys reachable. These changes add no
permissions. Revision f74b862 passed layout/inset regressions, and its actual setup
and synthetic live-IME screenshots were reviewed. The replacing Fn layer also
passed controlled layout/dispatch tests. These checks do not establish phone,
assistive-technology or named terminal compatibility.

## Release discipline

The [successful alpha05 signing/publishing run](https://github.com/RioPlay/utterleaf/actions/runs/34432995380)
verified the unchanged signing certificate, signed alpha03-to-alpha05 emulator
upgrade, same-version reinstallation and setup launch. Preference/model retention,
physical upgrades and real Obtainium updates were not established by that test.

Regular builds never receive signing secrets. Published APKs are immutable;
certificate changes fail the release check until an explicit rotation design is
implemented. Old debug alphas require a one-time reinstall. Keep desktop signing,
versions and release assets independent. Do not mark platform or security gates
complete merely because an emulator test passed.
