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
