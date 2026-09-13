# Desktop CI platform integration — completed

The integration fixes merged through [PR #26](https://github.com/RioPlay/utterleaf/pull/26)
at `bf4dfda012e541870ff4ecda7b9c2c0c01a83904`. See the
[desktop roadmap](../../desktop-roadmap.md) for current product work.
The published Windows RC2 tag remains `90d2e147c6c84af2639317b427a2f5135b3ff997`;
this later integration evidence does not describe a replacement release artifact.

## Result

Windows CI uses the reviewed CPython 3.14 dependency hash lock. Linux x86_64
(CPython 3.12) and macOS ARM64 (CPython 3.14) constrain each version-sensitive
notice and VAD admission: CTranslate2 4.8.2, faster-whisper 1.2.1, FlatBuffers
25.12.19, ONNX Runtime 1.28.0, Protobuf 7.35.1 and Tokenizers 0.23.1. The POSIX
constraints are not a hash lock for the complete Python environment.

The notice collector selects exact version/platform/architecture records,
verifies full notice bytes and reviewed source-native hashes, and checks the
packaged native inventory. Unknown versions or targets, changed retained terms
and unexpected native members fail packaging. Retained provenance under
`packaging/notices/runtime/` records the exact wheels, upstream inputs, notice
hashes and native dependency inventories. This engineering review is not legal
certification. No new architecture is admitted without its own review.

The Linux ONNX source review includes its versioned standalone C API library.
PyInstaller does not package it: neither packaged ELF member depends on it and
the hook's `lib*.so` selection does not match that versioned filename. Source
inventory and the deliberate packaged subset are recorded separately. The VAD
notice path uses the same target and payload verification. Unused ASIO DLLs
are excluded on every host, whether classified as data or binaries.

Platform tests now simulate Windows ABI availability explicitly on POSIX and
establish the Wayland microphone selector's visible focus position before
checking popup anchoring. Aqua's final synchronous menu-post boundary is
intercepted in the unattended test while retaining production bindings and
geometry. This verifies the placement request, not rendered Cocoa menus.
The separate [backup dialog correction](desktop-backup-compact.md) preserves
preview and action geometry when native font metrics grow.

## Verification

[CI 34746938663](https://github.com/RioPlay/utterleaf/actions/runs/34746938663)
passed from exact tested HEAD `3f1bd6c5c3200d01ee0d4121ffb34d636b6530d8`:

- Windows: 1,459 passed, 13 skipped.
- macOS: 1,440 passed, 32 skipped.
- Linux X11 and forced Wayland: each 1,440 passed, 32 skipped.
- All platform builds, notice collection, package uploads and frozen CLI checks passed.
- Linux extracted-release startup passed with X11 and forced Wayland session settings, with tray enabled and disabled.

Independent source and exact-wheel review preceded CI. Downloaded POSIX archive
review then confirmed safe member paths, all selected provenance/notice hashes,
and exact CTranslate2, Tokenizers and ONNX native membership. No ASIO, FFmpeg or
CUDA-family foreign native payload was found. Full logs and engineering receipts
remain locally under `.grok/release/ci-rc2`; the consolidated receipt is
`release-review-34746938663.json`.

Earlier failing runs 34742420306, 34743932100, 34745147128 and 34746487487 remain
historical failures or explicit cancellations. Their diagnostics and resolver
inventories are retained in the local audit receipts and Git history; the final
successful run supplies acceptance evidence. Broader device/editor behavior,
assistive-technology usability and new desktop publication are outside this
completed CI slice.
