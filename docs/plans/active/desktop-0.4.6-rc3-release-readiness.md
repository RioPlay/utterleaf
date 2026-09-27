# Desktop 0.4.6 RC3 release readiness

## Goal

Produce an immutable, honestly described Windows x64 CPU release candidate for
the desktop modernization work, then obtain explicit authorization before creating
the public tag or prerelease.

## Area

Desktop source and tests in `utterleaf/` and `tests/`; release identity and notes;
Windows packaging output; CI and release evidence. Android source and releases are
out of scope.

## Constraints

- Preserve local-only processing and the established Tk architecture.
- Do not weaken microphone, IPC, clipboard, model, or filesystem safety checks.
- Do not describe simulated device/UI checks as physical-device acceptance.
- Do not publish, tag, sign, or replace stable downloads without explicit approval.
- Resetting preferences must not remove models or other user data.

## Acceptance

- Version metadata and preview notes consistently identify `0.4.6rc3` and the
  intended `desktop-v0.4.6-rc.3` tag.
- The modernization source is committed on top of current `origin/main`.
- Focused audio, Settings/recovery, privacy/config/boundary, and packaging tests pass.
- A fresh Windows onedir package passes offline doctor and release smoke checks;
  its contents, checksums, notices, and absence of bundled model weights are verified.
- CI results are tied to the exact candidate commit.
- Remaining native/signing/publication gates are recorded rather than implied away.

## Verification

```powershell
C:\Users\unknown\Projects\Utterleaf\.venv\Scripts\python.exe -m pytest tests/test_audio.py tests/test_app_readiness.py tests/test_transcribe_readiness.py
C:\Users\unknown\Projects\Utterleaf\.venv\Scripts\python.exe -m pytest tests/test_section_reset_ui.py
C:\Users\unknown\Projects\Utterleaf\.venv\Scripts\python.exe -m pytest tests/test_privacy.py tests/test_config.py tests/test_repo_boundaries.py
C:\Users\unknown\Projects\Utterleaf\.venv\Scripts\python.exe -m pytest tests/test_packaging_media.py tests/test_packaging_notices.py tests/test_packaging_runtime_notices.py
.\packaging\build.ps1
.\dist\Utterleaf\utterleaf-cli.exe --doctor --offline
```

The complete current-head suite must also run in CI or a clean native environment.
The managed local sandbox's unchanged OBS named-pipe fixture currently exceeds its
eight-second connection watchdog; directory-permission shims are not acceptable
evidence for its security-sensitive ACL tests.

## CI receipts

- Candidate `bf260d044bfb5c7378a36331ef62f74a39fcac11` built successfully on
  Linux and macOS. Its first test pass exposed cross-platform assumptions in the
  test harness, so it is not the final release revision.
- Linux and Windows synthetic audio tests now declare their simulated default
  input explicitly; production capture remains fail-closed when no input exists.
- Hosted Windows and macOS runners cannot always realize the former test window
  sizes. Layout assertions now use realizable compact dimensions and condition
  true-wide expectations on the geometry the window manager actually provides.
- Aqua's readonly combobox still exercises the keyboard-open path, while the
  final native menu post is intercepted in automation to avoid Cocoa's
  synchronous physical-menu loop.
- The Help recovery action was shortened to `Restore defaults…` after the Linux
  high-text-scale check found genuine clipping. A clean CI rerun is required for
  the replacement candidate.
- Candidate `afdbed39a6651dcc3777751f61e2673b3e8b5c92` cleared Linux tests and
  Linux/macOS packaging. Its macOS suite completed without the prior Aqua hang;
  the remaining failures showed the hosted desktop clamps a 700-pixel requested
  height to 645 pixels. Wide-layout fixtures now use a realizable 640 pixels;
  the taller backup review accepts a window-manager clamp above its 620-pixel
  minimum while retaining the 1000-pixel wide-layout stimulus.
- Windows Python 3.14.6 produced two independent native-runtime failures across
  reruns: intermittent Tcl library initialization and a native breakpoint during
  audio-owner garbage collection. Windows validation and preview packaging now
  use Python 3.14.7/Tk 9.0 with refreshed CPython license and DLL hashes. The
  appearance roundtrip passed five fresh-process runs on that runtime; the full
  hosted matrix remains the publication authority.
- macOS can fit the decoder surface at 200% text without body scrolling. The
  auxiliary test still validates Page Down/Home whenever overflow exists, but
  no longer treats the absence of unnecessary scrolling as a failure.
- Hosted run `36318483021` passed Linux tests, Linux packaging, macOS packaging,
  and the complete Windows pytest suite on Python 3.14.7. Its two remaining
  failures were the corrected macOS no-scroll assumption and Windows notice
  review stopping on Python 3.14.7's refreshed native payloads.
- The Python 3.14.7 package retains OpenSSL 3.5.7 and SQLite 3.50.4, while zlib
  advances to 1.3.2. The exact zlib tag, updated license, zlib DLL, and rebuilt
  SQLite DLL are recorded in the runtime manifest. A fresh Windows frozen build
  now collects all 43 package notice trees and its diagnostic CLI starts.
- Candidate `f250818b0ac1cc59fd6bc452f2ffdde76fee4dbf` passed all five hosted
  build/test jobs in run `36319194906`, including Windows packaging and notices.
  A follow-up provenance audit found that the checker validated declared DLLs
  but did not reject an additional root runtime DLL. The final candidate now
  inventories all 58 root DLLs, records Microsoft, libffi, Tcl/Tk, LibTomMath,
  and embedded zlib-ng terms, and fails closed if a future build adds another.

## Non-goals

- Stable v0.4.6 publication.
- Framework migration.
- New model removal/update semantics or tray dictation controls.
- Android changes.
- Claiming macOS/Linux, physical-microphone, screen-reader, mixed-DPI, or signed
  installer acceptance from Windows source/package checks.

## Stop

Stop before public tag/release creation. Present the immutable candidate revision,
local package receipts, CI state, and remaining gates for explicit publication
authorization.
