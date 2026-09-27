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
- A fresh Windows onedir package starts without network consent, passes doctor
  and release smoke checks; its contents, checksums, notices, and absence of
  bundled model weights are verified.
- CI results are tied to the exact candidate commit.
- Remaining native/signing/publication gates are recorded rather than implied away.

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_audio.py tests/test_app_readiness.py tests/test_transcribe_readiness.py
.\.venv\Scripts\python.exe -m pytest tests/test_section_reset_ui.py
.\.venv\Scripts\python.exe -m pytest tests/test_privacy.py tests/test_config.py tests/test_repo_boundaries.py
.\.venv\Scripts\python.exe -m pytest tests/test_packaging_media.py tests/test_packaging_notices.py tests/test_packaging_runtime_notices.py
.\packaging\build.ps1
.\dist\Utterleaf\utterleaf-cli.exe --doctor
```

The complete current-head suite must also run in CI or a clean native environment.
Cross-process tests must import the active checkout explicitly; an ambient package
installation is not accepted as proof for the candidate source.

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
- Microsoft UCRT/MSVC redistributables legitimately vary between the local
  Windows host and GitHub's Windows Server runner. Those 46 host-supplied DLLs
  are therefore bound to the exact reviewed filename inventory and must pass
  Windows Authenticode validation for `Microsoft Corporation`; deterministic
  Python and third-party payloads remain byte-pinned. Unknown names, missing
  files, invalid signatures, unreviewed signers, and changed pinned hashes fail
  packaging before notices or archives are produced.
- A fresh packaged-profile check exposed that the old default could download a
  missing speech model before explicit approval. Fresh profiles now write
  `allow_network = false`; malformed string or numeric values also fail closed,
  while an explicit Boolean `true` survives save/load. Startup tests deny both
  downloader entry points and require actionable missing-model recovery.
- Pre-ledger source revision `06e00279e56aa1b32412947fa1df53baf910b175`
  is on top of `origin/main` `3545a8eca01c81d81d351f41d48303058cecd855`.
  The full desktop suite passed **2,685 tests with 14 documented prerequisite
  skips in 384.11 seconds**. The checkout-local child-process correction also
  passed all six Windows pairing-owner tests alone.
- The rebuilt Windows onedir package passed three isolated fresh-profile starts.
  All wrote `allow_network = false`; polling saw no established external TCP
  socket owned by the parent app process; no download request was logged and no
  model weight was written. All parent app processes reached authenticated IPC
  and quit in 49.85–58.36 ms. The harness did not own the separate first-run
  Settings process, and three such processes remained afterward; the prior
  whole-process shutdown claim is withdrawn. IPC readiness was 1,607 ms for the first
  sequential sample and 562–610 ms for the next two; OS/file cache state was not
  controlled. Ten-second tray-idle samples consumed 0.250–0.313 CPU seconds, or
  0.154–0.194% of this 16-logical-CPU machine.
  Working set was 98.1–98.5 MB. This is bounded Windows evidence, not sustained,
  recognition-latency, macOS or Linux performance clearance.
- The measured `utterleaf.exe` SHA-256 is
  `d546667ab61b06d7f05c6813139e941fdd2d5467ecfc65e5b87fc651c0d4ee36`.
  Its ignored raw receipt is
  `artifacts/packaged-offline-first-run/fixed-20260927T142007/receipt.json`
  (SHA-256 `b600db2bced7874d63460cdf35b32021526260bda85dd60f9ad27097145b1e81`).
  The unforced packaged doctor reports both missing backends as explicit Settings
  installations and `allow_network: False`; local polish, executable checksums,
  48-package notices, and zero bundled `.bin`/`.safetensors`/`.gguf` files pass.
- The updated privacy/help copy has **56 source-matched Settings captures** in
  `artifacts/screenshots/desktop-explicit-model-consent-20260927`. Speech &
  privacy standard/lower, Help, and compact 2× views were inspected without
  clipping. Settings source SHA-256 is `dce20f1e…`; capture-helper SHA-256 is
  `bd88f73d…`. No microphone, model download or preference mutation occurred.
- Revision `978154b3f04e766f1441e9824ad3c9035ce3d17a` passed all five hosted
  jobs in [run 36345884893](https://github.com/RioPlay/utterleaf/actions/runs/36345884893).
  The multilingual model-pack follow-up was added afterward, so this remains a
  historical pre-feature receipt rather than current-head release evidence.
- The local performance receipt embeds the executable hash but not the source
  revision or dirty state; the older local build manifest is stale. It is bounded
  parent-process runtime evidence, not immutable candidate provenance or a
  whole-process lifecycle receipt. The exact-final hosted build and tag-bound
  archive must supply that binding.
- Exact final-candidate hosted CI is still required after the ledger commit is
  pushed. Public tag or prerelease creation remains explicitly unauthorized.

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
