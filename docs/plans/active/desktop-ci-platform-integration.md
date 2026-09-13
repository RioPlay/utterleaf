# Desktop CI platform integration

## Goal and area

Keep the post-RC2 desktop integration build reproducible on Windows, Linux x86_64,
and macOS ARM64. This follow-up owns the desktop build workflow, PyInstaller
payload policy, runtime-notice collector and their focused tests. The published
RC2 tag and artifact remain immutable.

## Constraints

Security and privacy behavior in the application does not change. Windows keeps
the reviewed CPython 3.14 dependency lock used for RC2 instead of admitting an
unpinned native runtime after dependency drift. A wheel without full license
text may use retained upstream terms only for its exact reviewed version,
platform and architecture. Other versions and targets fail packaging. Foreign
ASIO DLLs remain excluded and the output scan continues to reject one if a hook
reintroduces it.

The Linux and macOS CTranslate2 reviews are separate from the Windows native
closure. The Linux x86_64 record binds the official CPython 3.12 wheel, its
bundled GCC 8.5 `libgomp`, unchanged CTranslate2 static component inputs and the
Linux oneMKL notice artifact. The macOS ARM64 record binds its smaller
Accelerate/Ruy wheel closure. This engineering inventory is not legal
certification and does not admit Linux ARM64 or macOS x86_64 builds.

## Acceptance

- The Windows test suite can simulate `ctypes.WinDLL` on a POSIX host.
- General Windows CI installs the reviewed, hash-pinned RC dependency set.
- CTranslate2 4.8.2 fallback notices are accepted only on reviewed Linux x86_64
  and macOS ARM64 targets; unknown versions and architectures fail.
- The macOS spec removes the unused Windows ASIO DLL whether PyInstaller
  classifies it as data or a binary, and the final output scan still rejects it.
- Focused pipe, packaging media and runtime-notice tests pass before a new CI run.
- A clean Windows/Linux/macOS integration run is required before this follow-up
  is considered complete.

## Evidence and verification

GitHub Actions run 34742420306 at `e05a2cff` exposed three independent failures:
Linux could not monkeypatch absent `ctypes.WinDLL`; Linux selected CTranslate2
4.8.2 whose wheel omitted full license text; and macOS retained
`libportaudio32bit-asio.dll` as sounddevice data. The Windows build also selected
unreviewed CTranslate2 4.8.2, although its tests and PyInstaller build completed.
The macOS test job was still running when these corrections were prepared.

Official CTranslate2 tag v4.8.2 resolves to commit
`d44d2d069eb88c7b7804da864c10c201501cb4a9`. Its Linux and macOS build scripts
and all compiled dependency revisions relevant here are unchanged from v4.8.1;
the release changes application code and the excluded CLI-only cxxopts submodule.
Inspection of the exact PyPI wheels used by CI (CPython 3.12 on Linux and
CPython 3.14 on macOS) found `libgomp` only in Linux x86_64, while macOS ARM64
links Accelerate and system libraries and bundles no third-party dylib. The
collector hashes every installed native file and requires the exact packaged
native filename inventory before copying fallback terms. PyInstaller can
transform macOS binaries during collection, so this check binds their
source-wheel bytes and packaged membership rather than claiming the
post-processing bytes are unchanged. Retained provenance records carry the
exact wheel, build script, source revision and notice hashes.

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_windows_pipe.py tests/test_packaging_media.py tests/test_packaging_runtime_notices.py
```

Then run the normal desktop CI matrix. Inspect the built macOS payload for ASIO,
verify each platform's generated notice tree, and preserve the existing media
and unknown-version failure checks.

The scoped command passed **52 tests** locally. Python compilation and
`git diff --check` also passed. Independent re-review repeated the focused
pipe/media/runtime-notice checks, verified all 31 platform-variant notice hashes,
and confirmed that each reviewed source and packaged inventory is nonempty.

The obsolete run's macOS test job 103684254533 remained inside pytest for more
than 25 minutes while four sibling jobs had already failed. Its cause was not
diagnosed and the job was not restarted. The macOS pytest command now enables
pytest's `faulthandler_timeout=120` diagnostic dump; this does not impose a test
timeout or turn a hang into a passing result. Replacement CI remains required.

## Non-goals and stop

No application runtime, UI, Android, model, CUDA or release-publication changes.
Do not add unsupported architecture records without inspecting their exact wheel
and compiled closure. Stop editing after the focused checks and independent diff
review; CI supplies the clean platform build evidence.
