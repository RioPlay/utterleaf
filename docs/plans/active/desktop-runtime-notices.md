# Windows preview runtime notices

## Goal and area

Produce an auditable Windows 0.4.6 RC2 package with complete license texts for
the actual bundled runtime. Own `packaging/`, the Windows preview workflow,
packaging tests and desktop release documents. RC1 remains an unpublished,
immutable candidate; do not modify its tag or substitute an edited archive.

## Evidence and constraints

Independent inspection of CI run 34737182479 found missing CPython and PortAudio
license texts, an unused ASIO-enabled PortAudio DLL, and metadata-only license
placeholders for CTranslate2, protobuf, pywin32-ctypes, flatbuffers and tokenizers.
The native closure also needs OpenSSL, zlib and Intel OpenMP license/provenance
material and SQLite's public-domain provenance. Existing Tcl/Tk, NumPy, Pillow,
ONNX Runtime and Silero notices were inspected separately.

RC1's downloaded artifact passed ZIP CRC, manifest and three executable hashes,
and offline 88-second file recognition. Those checks do not satisfy the missing
notice gate. Its CI archive step exited before validation because a PowerShell
cmdlet left LASTEXITCODE null. A corrected step was exercised in fresh PowerShell:
valid input produced a checksum; corrupt executable hashes and a missing bundle
failed without producing one. RC2 inherits that fix.

Retain original application code and platform separation. Do not add unreviewed
runtime downloads, alter installed applications/models or copy FUTO/LatinIME code.
No ASIO-enabled binary is needed for the advertised default Windows audio path.
Keep third-party texts verbatim with exact version, immutable source and hashes.
Unknown or missing license material must fail packaging, not become a one-line
license-expression placeholder. No legal certification claim follows from this
engineering review.

## Acceptance

- Every affected package carries full reviewed terms and applicable notices.
- The admitted native payloads match the reviewed versions/identities.
- The unused ASIO DLL is excluded and rejected if it reappears.
- Missing texts, changed resource bytes and unreviewed fallback versions fail.
- Canonical Windows build, exact-tag CI and downloaded-artifact inspection pass.
- Frozen diagnostics, formatting and offline recognition pass on that artifact.
- Independent review clears the payload, notices, source provenance and release
  notes before explicit prerelease publication; stable v0.4.5 stays latest.

## Verification

Run focused packaging pytest after edits, then the full desktop suite in exact
candidate CI. Exercise the actual archive workflow step in a fresh PowerShell
process. Build only in the isolated candidate workspace/CI. Record native payload
and notice hashes from the resulting ZIP, then run its CLI `--doctor --offline`,
`--polish` and the existing verified 88-second fixture with `--transcribe-file`,
`--audio-track 1`, a new `.srt` output and `--offline`.

## Current verification

The RC2 correction passes 23 focused packaging tests. A fresh canonical local
CPU build completed with 43 notice entries and no ASIO DLL. Independent review
checked all 700 retained manifest references against their retained bytes, reviewed native
payload identities, and absence of metadata-only fallbacks. Its two native
summary labels now explicitly include retained third-party terms. A final content
check excluded a Rust source file named `licenses.rs` that was not a license;
provenance maps that crate to the retained Apache and MIT workspace terms.

The local frozen RC2 CLI passes help, offline diagnostics and formatting; an
empty worker request returns unavailable without a clipboard request. Offline
recognition of the existing 88-second PCM fixture completed in 18.455 seconds
and exported SRT using the verified local base.en model. These are local build
checks, separate from the required exact-tag downloaded artifact verification.

An initial full local pytest attempt aborted inside the native Tcl runtime while
a background IPC thread was collecting garbage. Test-only cleanup now collects
Tk objects on their creating thread after destroy or failed initialization;
failed constructors release their exception traceback before collection. The
native root cause was not reproduced deterministically, so this is a lifetime
mitigation rather than a claim to have diagnosed Tcl itself. Independent review
covered the exception path and indicator cleanup on assertion failure.

The final exact working-tree desktop run passes **1,445 tests, 14 skipped in
43.23 seconds**, with JUnit evidence and no Tk initialization skips or native
abort. Skips are 11 external-codec fixture cases, one absent local public-speech
fixture, one Windows symlink privilege case and the opt-in clipboard isolation
probe.

The correction is complete in the [published RC2 preview](https://github.com/RioPlay/utterleaf/releases/tag/desktop-v0.4.6-rc.2).
[Exact-tag CI run 34740809768](https://github.com/RioPlay/utterleaf/actions/runs/34740809768)
passed 1,446 tests with 13 skips at `90d2e14`. Independent inspection of the
downloaded artifact verified 41 license directories with 419 files, no empty or
metadata-only placeholders, 12 exact-source provenance records, 357 retained
references and 10 native payload references. No ASIO DLL or excluded codec/GPU
payload was present. Frozen diagnostics, formatting and the offline 88-second
transcription check passed on that downloaded build. The
[prerelease record](desktop-prerelease.md#published-rc2-evidence) contains the
published ZIP identity and publication checks; stable v0.4.5 remains latest.

## Non-goals and stop

No UI redesign, Android release changes, live OBS implementation or broad
dependency upgrades. Stop this correction when the complete affected runtime
closure is documented, enforced, built and independently reviewed. Preserve
remaining real-microphone, physical-device and platform acceptance limits.
