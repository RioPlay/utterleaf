# Mobile keyboard security design

[Mobile roadmap](mobile-roadmap.md) · [Development boundaries](development-boundaries.md)

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
| Editor ↔ IME | Android binds exported IME services through BIND_INPUT_METHOD. No surrounding-text collection, persisted keystrokes or clipboard history. Field lifecycle clears speech. | Real-editor selection, cursor and field-switch tests across apps |
| Microphone ↔ inference | Explicit activation, runtime permission, bounded memory, capture cancellation; no saved audio or network fallback | Physical Bluetooth/call/revocation and low-memory tests |
| Document provider ↔ model store | Explicit file picker, exact model size/hash, atomic replacement, private no-backup storage | More provider/interruption scenarios; each new model needs its own review |
| Preferences ↔ keyboard | Only explicit booleans for appearance/touch/feedback; no entered text, editor identifiers or secrets | Imported layouts/preferences are not supported until validated and bounded |
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

## Release discipline

Regular builds never receive signing secrets. Published APKs are immutable;
certificate changes fail the release check until an explicit rotation design is
implemented. Old debug alphas require a one-time reinstall. Keep desktop signing,
versions and release assets independent. Do not mark platform or security gates
complete merely because an emulator test passed.
