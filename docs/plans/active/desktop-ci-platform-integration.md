# Desktop CI platform integration

## Goal and area

Keep the post-RC2 desktop integration build reproducible on Windows, Linux x86_64,
and macOS ARM64. This follow-up owns the desktop build workflow, PyInstaller
payload policy, runtime-notice collector and their focused tests, including
platform-specific expectations in `test_app.py` and `test_settings_ui.py`. The published
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
- Wayland tests expect the press-to-stop caption and disabled global-hotkey
  selector, while popup placement remains covered on an enabled control.
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
.\.venv\Scripts\python.exe -m pytest -q tests/test_windows_pipe.py tests/test_packaging_media.py tests/test_packaging_runtime_notices.py tests/test_repo_boundaries.py
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

Replacement run [34743932100](https://github.com/RioPlay/utterleaf/actions/runs/34743932100)
at `7357856` passed Windows tests, packaging and smoke checks. Linux's first suite
passed, but the forced Wayland suite exposed two test assumptions: the hold-mode
caption expected non-Wayland wording, and popup placement tried to open the
disabled global-hotkey selector. Both POSIX builds passed compilation and CLI
smoke, then stopped because unpinned installation selected tokenizers 0.23.2
instead of the retained, reviewed 0.23.1 notice version. These failures remain
open until corrected and independently verified; the exact-version notice gate
must stay in place. The old run 34742420306 was cancelled after its replacement
started.

Run 34743932100 was already unable to pass when its macOS test job remained in
pytest for about 16 minutes. It was cancelled explicitly to release diagnostic
output, not treated as a spontaneous test failure. The configured 120-second
faulthandler dump identifies a Tk `event_generate` wait in
`test_first_combobox_click_does_not_scroll_or_detach_popup`; this is a test-harness
hang rather than application audio capture. The Windows forced-environment check
still exercises the non-Wayland branch because the Windows platform decision
reports `is_wayland=False`. Popup behavior on Wayland and macOS remains pending
replacement CI evidence. The corrected Aqua test intercepts only the final
native menu `post` request and verifies the requested anchor plus two pixels
without replacing production bindings, postcommand or Tk geometry. That is
native placement-request evidence; it does not verify the rendered Cocoa menu,
native visual appearance or physical-device behavior. Because two macOS jobs
have now hung inside pytest, the
macOS test job has a 15-minute job limit while retaining the 120-second
faulthandler dump. Exceeding that resource limit fails or cancels the job; it
does not skip the test or turn the hang into a passing result.

All four POSIX test/build installs now apply `packaging/constraints-posix.txt`,
which constrains CTranslate2 to the reviewed 4.8.2 platform records, Tokenizers
to 0.23.1, and the existing VAD gate to faster-whisper 1.2.1 with ONNX Runtime
1.28.0, without changing the published Windows lock. The failed run had already
selected ONNX Runtime 1.30.0, which would have stopped at the unchanged exact
VAD-runtime gate after the Tokenizers failure was corrected. Exact official
Tokenizers ABI3 wheels were inspected for Linux x86_64 and macOS ARM64. Their
SHA-256 hashes are `5075b405...bda45a4` and `e0948bbb...326324e`; each contains
one native `tokenizers/tokenizers.abi3.so`. Linux loads only the system loader,
glibc, libgcc, libstdc++ and related system libraries; macOS loads libSystem,
libc++, libiconv and its own install-name entry. The full hashes, byte sizes,
source URLs and load-command inventories are retained in
`runtime/tokenizers/wheel-provenance.json`.

The retained 0.23.1 record follows the exact full Cargo lock and is a
conservative license superset across the admitted Windows x86_64, Linux x86_64
and macOS ARM64 targets. The collector now binds the installed source native
file and packaged native membership for each target and rejects other targets.
This is not a hash lock for the complete POSIX Python environment. Dependencies
that carry their own full wheel license files remain unconstrained, while an
unknown missing-text version continues to stop packaging. The Linux CTranslate2
scope label was also corrected from CPython 3.14 to the actually inspected
CPython 3.12 wheel.

The focused command passed **49 tests** after this stabilization:

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_windows_pipe.py tests/test_packaging_media.py tests/test_packaging_runtime_notices.py
```

Runtime-manifest JSON parsing, the current Windows Tokenizers source/package
identity check and `git diff --check` also passed. `tests/test_repo_boundaries.py`
passed **4 tests**. A clean POSIX resolver/build run is still required to prove
that both runners select 0.23.1 and complete notice collection.

Independent integration review verified both retained POSIX Tokenizers wheels'
archive hashes, exact native inventory, byte sizes and native hashes. The final
combined local check passed **149 tests in 27.73 seconds**:

```powershell
$env:PYTHONPATH=(Get-Location).Path
.\.venv\Scripts\python.exe -m pytest -q -o addopts= tests/test_windows_pipe.py tests/test_packaging_media.py tests/test_packaging_runtime_notices.py tests/test_repo_boundaries.py tests/test_app.py tests/test_settings_ui.py
```

The Aqua test boundary follows Tk's
[combobox implementation](https://github.com/tcltk/tk/blob/main/library/ttk/combobox.tcl)
and [synchronous native menu handling](https://github.com/tcltk/tk/blob/main/macosx/tkMacOSXMenu.c).
Local Windows results do not verify Aqua execution or the actual Linux Wayland
test path; the next canonical run must establish those platform results.

## Non-goals and stop

No application runtime, UI, Android, model, CUDA or release-publication changes.
Do not add unsupported architecture records without inspecting their exact wheel
and compiled closure. Stop editing after the focused checks and independent diff
review; CI supplies the clean platform build evidence.
