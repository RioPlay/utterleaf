# Desktop dependency security remediation

## Contract

- Goal: remove the known advisories affecting the four audited Python dependencies and prevent their reintroduction through normal source installs or Windows release inputs; scan resolved desktop graphs in CI.
- Area: `pyproject.toml`, Windows hash pins, desktop workflows/security automation, installation/security documentation and this platform roadmap. Android is handled in a separate branch and plan.
- Constraints: preserve local-only processing, model verification, data/preferences and dirty worktrees. Preserve immutable published releases; no publication or credential changes. Keep native notice checks fail closed.
- Acceptance: patched Windows pins install with hash verification; resolved installed graph has no known scanner advisories; focused/full desktop tests and Windows build/doctor pass, or exact unavailable proof is recorded. Independent review of actual diff and evidence.
- Verification: isolated `.venv` in this checkout; `uv pip sync --require-hashes packaging/requirements-windows-preview.txt`; editable install without dependency/build isolation; `pip-audit` exact pins and installed graph; `python -m pytest`; `packaging/build.ps1`; frozen CLI `--doctor`. Store verbose receipts locally under `.grok/security-audit-20261104` in the preserved root.
- Non-goals: unrelated feature/toolchain updates, new releases, broad architectural changes, claiming all native/optional/platform dependencies are safe from a Python scan.
- Stop: known supported Python findings removed, checks/independent review complete, unresolved platform/native findings recorded explicitly.

## State (2026-11-04)

Started from `ddf7c78d241c15442d40a47e2b855cbfa69e7671` in isolated `audit/dependency-security-20261104`. Original checkpoint and unfinished Android/desktop work remain untouched. Parent owns dependency inputs/integration; specialist owns new dependency-security workflow/config/docs. Android specialist works in separate `fix/android-dependency-security` worktree.

Initial audit: installed inventory and 43 Windows pins reported 54 entries across certifi, filelock, Pillow and setuptools (overlapping IDs/aliases are not distinct exploit counts). Updated certifi to 2026.10.23, filelock to 4.2.9, Pillow to 13.0.0 and setuptools to 84.2.1 using exact non-yanked wheel SHA-256 values from PyPI. Patched Pillow/filelock require Python 3.11; source minimum raised from the end-of-life Python 3.10. Runtime/build lower bounds prevent vulnerable old versions satisfying declared requirements.

## Verified result

- Clean Windows hash-checked installation and editable project install passed; `pip check` passed. Exact Windows pins and the final installed third-party inventory report no known PyPI advisories with `pip-audit==2.10.1` (strict, no ignored IDs).
- Resolved metadata inventories for Windows Python 3.11, Linux Python 3.11 with POSIX constraints, macOS ARM64 Python 3.14 with POSIX constraints and macOS 14 minimum, and Windows CUDA/NPU extras all scanned without known PyPI advisories. These are resolver/advisory checks, not execution on those targets or accelerator acceptance.
- The initial installed CPython 3.14.7 was superseded during this work by the verified latest security release, **3.14.10**. The official Windows runtime ZIP and release manifest were checked against published SHA-256 values; its Python binaries have a valid PSF signature. Only the isolated checkout environment was upgraded; no global Python installation or preserved checkpoint environment was changed.
- Final full desktop regression on Python 3.14.10: **1,675 passed, 14 skipped**. Canonical Windows CPU build passed, including all notice/payload checks and speech-model exclusion; frozen `utterleaf-cli.exe --doctor` exited 0 and selected CPU. GPU libraries are absent in this CPU build, so CUDA execution is unverified.
- Exact runtime manifest binds CPython 3.14.10/OpenSSL 3.5.9 DLLs, SQLite 3.50.4 and Tcl's separate zlib 1.3.2 DLL. Python's built-in zlib module uses zlib-ng 2.2.4 in compatibility mode and its attribution ships with the Python notice. Native notice checks remain fail closed.
- Existing desktop CI actions now use immutable, upstream-verified commits. New strict dependency workflow covers exact Windows pins and resolved base/dev graphs on Windows/Linux at Python 3.11/3.14. YAML/PowerShell structure and equivalent local audit commands passed; remote workflow jobs have not run for these uncommitted changes.
- GitHub dependency alerts and automatic security fixes were enabled and read back successfully. Secret scanning/push protection remain enabled. The initial alert list was empty; that does not establish a completed repository scan. Dependabot configuration suppresses routine version-update PRs and permits security fixes.
- Independent review found no material desktop defects. Reviewer independently checked final packaged DLL/license hashes, runtime provenance/signatures and the runtime/workflow consistency test. Full test/build/audit logs and provenance remain local in the preserved root's `.grok/security-audit-20261104/`.

## Residual upstream/runtime risk

Python 3.14.10 is a released security update, not a guarantee of zero vulnerabilities. Its current [changelog's unreleased section](https://docs.python.org/3.14/whatsnew/changelog.html) includes Expat 2.10.0 updates for CVE-2026-113351, CVE-2026-115506, CVE-2026-117610 and CVE-2026-118370, Windows tar extraction fix CVE-2026-107784, and asyncio TLS buffering hardening. The verified 3.14.10 runtime still reports Expat 2.9.0. [SQLite's advisory page](https://www.sqlite.org/cves.html) also lists CVE-2026-11824 (fixed in 3.53.2) with arbitrary-SQL/FTS5/defensive-mode prerequisites; bundled SQLite remains 3.50.4.

Bounded source triage found no application call accepting arbitrary SQL/database files, Python XML parsing or tar extraction. The built import graph does include SQLite through filelock's read/write-lock modules and Expat through Pillow/ElementTree. Presence is not proof of exploitability, and direct-source absence is not proof of transitive safety. Removing these extensions without proving all import requirements would risk breaking startup or dependency behavior; no such exclusion was applied. Follow the next supported patched runtime, refresh exact native inputs/notices, and repeat artifact/regression checks. Do not claim all bundled components are free of known advisories or promote this local build as a fully remediated release.

## Handoff and boundaries

Desktop fixes are reviewable in `audit/dependency-security-20261104`. Android fixes and their scanner, native runtime proof and independent review belong to separate `fix/android-dependency-security`; see that checkout's Android security plan. No source was pushed, no signed artifact was published, and existing installations/immutable release archives remain unchanged. The original shared environment retains its old packages and obsolete editable paths as a preserved checkpoint; use the isolated patched checkout for further desktop work, not that environment.

Local contribution preparation is complete. The ignored checkout directory `.grok/submission-security-20261104/` contains a draft PR description, an exact patch including new files, and a SHA-256 manifest of changed files and supporting receipts. Preparation reconciled the actual diff with the existing test/build/audit evidence; it did not repeat the full suite or build or change application behavior. Verify the manifest again after any further edits. The next contribution step is coordinator review and separately authorized submission, followed by hosted platform CI; the local package is neither a submitted PR nor a release.

Remaining work: native upstream fixes above, remote Windows/Linux/macOS CI on the final changes before release, and version/signing/publication as a separate authorized release task. Optional accelerator runtime behavior and physical-device acceptance are not established by metadata scans or emulator tests.

The initial hosted Windows build of draft PR #73 failed the native notice check on
`zlib1.dll`. The GitHub Python 3.14.10 x64 package uses the official executable
installer. Its embedded Tcl/Tk MSI contains zlib 1.3.2 with SHA-256
`f07195206534ebb1fe75093d4ec6c54a7a9227281b0c09d2113465b71da9e900`.
The reviewed Python.org ZIP's Tcl zlib DLL also reports 1.3.2 but has SHA-256
`7be5c2af1d33f631b2962393a088f182a580410173955323ca47a692f76b241d`.
Canonical Windows CI now checks the SHA-256 of the reviewed Python.org ZIP before
extraction. The preview workflow uses that ZIP when the selected tag's manifest
has an archive hash and keeps its installer-based setup for historical tags.
The first preview, `desktop-v0.4.6-rc.1`, used Python 3.14.6 and predates the
manifest, so its original version is selected explicitly when the file is absent.
The packaged payload hashes still have to pass the native notice gate.

An existing AlmaLinux 10 WSL target was probed for additional Linux verification. WSL reported mirrored-network setup failure `0x8007054f` and fell back to no networking; the environment had Python 3.12.12 but no Tk, Xvfb, compiler or uv. No Linux runtime checks or system changes were performed. This is a verification limitation, not a passing Linux result.

Continuation read-back: upstream main remains `ddf7c78`. GitHub's dependency graph
reports 55 open alerts on main across certifi, filelock, Pillow and setuptools
(verified with complete pagination; an earlier first-page read showed only 30);
these refer to the existing unmerged versions, not the patched local inventories.
Dependabot opened overlapping certifi [PR #72](https://github.com/RioPlay/utterleaf/pull/72)
and filelock [PR #71](https://github.com/RioPlay/utterleaf/pull/71). The reviewed
desktop patch covers all four packages and selects certifi 2026.10.23, newer than
the bot's 2026.10.18 trust-store update. Reconcile these PRs when submitting the
complete fix; none was merged, closed or commented on during preparation.
