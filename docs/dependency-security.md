# Dependency security checks

[Desktop roadmap](desktop-roadmap.md) · [Development guide](development.md)

The [desktop dependency workflow](../.github/workflows/dependency-security.yml)
runs on dependency/packaging pull requests, matching pushes to `main`, and manual
dispatch. It has no scheduled trigger. A successful scan means the selected
packages had no known advisories in the service at that time; it is not a security
guarantee or a replacement for application tests and release verification.

The Windows pin job scans every exact version in
`packaging/requirements-windows-preview.txt`, including build and test tools.
It uses `--disable-pip --no-deps` because the file already describes a complete
closure. The audit requires hashes in the input but does not download or verify
wheel bytes; the existing Windows build performs the hash-checked installation.

The resolved jobs install separate base and `[dev]` environments on Windows and
Linux using Python 3.11 and 3.14. Linux uses the same POSIX constraints as the
build. Each job runs `pip check` and audits the installed packages, including
transitive dependencies and environment tooling. `pip list --format=freeze`
exports the installed exact versions, excluding only Utterleaf because it is the
local application. The scanner audits that inventory without resolving again.
The pinned `pip-audit==2.10.1` scanner lives in another environment, so installing
its dependencies cannot replace vulnerable packages in the audited environment.
Scanner errors, collection failures and advisory findings fail the job. No
advisory IDs are ignored, and CI never applies automatic fixes.

For a local Windows scan of an already installed application environment:

```powershell
python -m venv .audit-tools
./.audit-tools/Scripts/python.exe -m pip install pip-audit==2.10.1
./.audit-tools/Scripts/python.exe -m pip_audit --strict --require-hashes --disable-pip --no-deps --progress-spinner off -r packaging/requirements-windows-preview.txt
./.venv/Scripts/python.exe -m pip list --format=freeze --exclude utterleaf | Set-Content -Encoding utf8 resolved-dependencies.txt
./.audit-tools/Scripts/python.exe -m pip_audit --strict --disable-pip --no-deps --progress-spinner off -r resolved-dependencies.txt
```

Run commands individually and stop on a nonzero exit code. On Linux/macOS use
`bin/python` in place of `Scripts/python.exe`. Scan a clean environment resolved
from the intended checkout and profile; an existing `.venv` may represent another
revision. Package names and versions are queried against the public PyPI advisory
service; scanning does not require application recordings or transcripts.

When a check fails, distinguish an advisory from an unavailable service or a
dependency-resolution failure. Repair the declared dependency, platform pin or
constraint as appropriate, regenerate hashes from official package metadata,
then rerun the audit and affected tests/builds. Retry service outages after the
service recovers; do not suppress the job failure. A package without a fix needs
an explicit risk decision or removal/replacement before any exception is added.

The [Dependabot configuration](../.github/dependabot.yml) covers root Python
metadata, packaging requirements, GitHub Actions and Android Gradle metadata.
Every entry sets `open-pull-requests-limit: 0`: version-update PRs are suppressed;
security-update PRs remain possible when repository Dependabot alerts and security
updates are enabled. The mandatory interval field does not enable routine version
PRs. Configuration alone does not establish that repository settings are enabled
or that Dependabot can repair every hash-pinned/transitive dependency. Review
generated updates and regenerate platform hashes/closures where necessary.

Coverage does not include optional CUDA/NPU installations, a macOS-specific
resolved graph, Android/native binaries, FFmpeg/OS libraries, downloaded models,
or unpublished vulnerabilities. Android dependency/native reviews and CI remain
separate. Auditing Python distribution metadata cannot establish the safety of
bundled native payloads. Historical release archives are unchanged by source fixes.

The November remediation's [desktop plan](plans/active/desktop-dependency-security.md)
records the reviewed CPython 3.14.10/OpenSSL 3.5.9 inputs, exact verification and
remaining bundled-runtime advisories. Some upstream fixes are only in the next,
unreleased Python version. Do not equate a clean pip audit with a fully patched
Python standard library, Expat or SQLite. Keep the interpreter at its latest
supported security patch and refresh native provenance before releasing a build.

Tool behavior and pins were checked against primary sources on 2026-11-04:
[pip-audit 2.10.1](https://github.com/pypa/pip-audit/tree/v2.10.1),
[checkout v7.0.1](https://github.com/actions/checkout/releases/tag/v7.0.1),
[setup-python v7.0.0](https://github.com/actions/setup-python/releases/tag/v7.0.0),
and [GitHub security-update configuration](https://docs.github.com/en/code-security/how-tos/secure-your-supply-chain/secure-your-dependencies/configure-security-updates).
