# Working on Utterleaf

- Security first, privacy second, convenience third. Do not add ambient recording,
  passive typing collection, or unverified model loading as convenience options.
- Sane defaults, useful customization and repeatable behavior are product
  requirements. Keep explicit preferences local, group related controls, and
  provide a clear Reset to defaults. Reset preferences must not delete models or
  other user data. Verify persistence, cancellation and reset when changing settings.
- **Aden is required** for code navigation whenever the Aden MCP or CLI is
  connected. Do not skip it. Follow [Aden](#aden) below and pass it to subagents.
- Keep desktop and mobile dependencies, source, tests, roadmaps and releases
  separate as described in [development boundaries](docs/development-boundaries.md).
- Prefer useful, accessible controls over extra menus. Document unsupported
  editor/platform behavior and distinguish implemented features from verified
  device behavior. Do not claim emulator tests establish physical-phone usability.
- Follow the [development guide](docs/development.md),
  [mobile capability plan](docs/android-keyboard-capabilities.md) and applicable
  platform roadmap. Run checks appropriate to the changed behavior.
- Do not commit AI prompts, chat dumps, or harness scratch. Those stay local
  (`.grok/` is gitignored). `AGENTS.md` is the repo contract.

## Aden

If Aden is connected, use it **before** broad filesystem search or reading whole
trees. Familiarity with `grep` is not a reason to skip it. If Aden is not
connected, say that in the first reply and use source plus tests.

Required order:

1. `tree` on the owning subtree (`utterleaf/`, `tests/`, or `mobile/android/`)
2. `grep` for independent evidence (not one lucky hit)
3. `locate` to resolve ambiguous names
4. `understand` (and `query` / callers) before editing a known symbol
5. Read the located source range; confirm callers before changing signatures

Rules that keep getting skipped:

- Pass this section and file ownership to every subagent.
- Omit `gen`, budgets, and tuning arguments in normal Aden calls.
- At most two distinct Aden calls at a time; wait if the server is busy.
- Graph results are heuristic. No hit is not proof of absence — retry with
  `grep` and read the file.
- Use git/filesystem/build/test tools for history, inventory, and verification.

## Start

1. This file, then Aden as above, then any matching plan in
   [docs/plans/active/](docs/plans/active/).
2. `git status`, `git diff`, and the platform roadmap for the files you will touch.

Use [active workspaces](docs/workspaces.md) to select the owning branch before
editing. The mixed checkpoint is recovery/reference only; desktop release and
Android implementation work belong in their separate worktrees.

Status lives in the platform roadmaps, not in chat. [Roadmap hub](docs/roadmap.md)
is the index. [Execution plan](docs/execution-plan.md) assigns packages; it is not
release status.

| Need | Authority |
| --- | --- |
| Desktop setup, tests, packaging | [development.md](docs/development.md) · [installation.md](docs/installation.md) |
| Android setup, tests, APK | [mobile/android/README.md](mobile/android/README.md) |
| Desktop vs Android isolation | [development-boundaries.md](docs/development-boundaries.md) |
| Product invariants | this file · [consumer-experience.md](docs/consumer-experience.md) |
| Desktop work | [desktop-roadmap.md](docs/desktop-roadmap.md) · `utterleaf/` · `tests/` |
| Android work | [mobile-roadmap.md](docs/mobile-roadmap.md) · `mobile/android/` |
| Substantial in-flight work | [docs/plans/active/](docs/plans/active/) |

## Validation ladder

Run the smallest check that covers the change. PowerShell: no `&&`; quote paths.

| Change | First check | Then |
| --- | --- | --- |
| Desktop module `foo` | `.\.venv\Scripts\python -m pytest tests/test_foo.py` | `.\.venv\Scripts\python -m pytest` |
| Privacy/config/boundaries | `.\.venv\Scripts\python -m pytest tests/test_privacy.py tests/test_config.py tests/test_repo_boundaries.py` | full desktop pytest |
| Desktop UI | `.\.venv\Scripts\python tests/capture_settings.py` (writes `artifacts/screenshots`; no mic) | affected UI tests |
| Android JVM | `python -m unittest discover -s mobile/android/tools -p test_*.py` | `mobile/android` `gradlew testDebugUnitTest` (needs `JAVA_HOME`) |
| Android emulator | `gradlew connectedDebugAndroidTest` | not physical-device proof |
| Desktop package | `.\packaging\build.ps1` then `.\dist\Utterleaf\utterleaf-cli.exe --doctor` | CI / signed release |
| Launch desktop from source | `Start-Process ".\.venv\Scripts\pythonw.exe" -ArgumentList "-m","utterleaf"` | — |

Do not run the full suite or packaging unless the change can break them. CI owns
Windows/macOS/Linux pytest and Android emulator jobs.

**Done when:** the named acceptance checks pass; docs that describe the behavior
match the source; unsupported/emulator-only limits stay explicit; no extra scope.

## Ownership (do not collide)

One writer per group. Integrator-owned files stay off parallel agents unless
reassigned: `utterleaf/app.py`, `config.py`, `settings.py`, `settings_ui.py`,
`__main__.py`. Android: do not edit `DeviceTest.kt` and `PrivacyCoreTest.kt` in
parallel with other Android work.

| Area | Source | Tests |
| --- | --- | --- |
| Capture | `utterleaf/audio.py`, `audio_owner.py` | `tests/test_audio*.py` |
| Transcription | `transcribe.py`, `models.py` | `test_transcribe.py`, `test_models.py` |
| Cleanup | `clean.py`, `polish.py` | `test_clean.py`, `test_polish.py` |
| Paste/clipboard | `inject.py`, `edit_target.py` | `test_inject.py`, `test_edit_target.py` |
| Tray/status | `indicator.py`, `host.py` | `test_indicator.py`, `test_host.py` |
| Settings | `settings.py`, `settings_ui.py`, `config.py` | `test_settings*.py`, `test_config.py` |
| Packaging | `packaging/` | `test_packaging_media.py`, smoke scripts |
| Android IME | `mobile/android/app/src/main/java/org/utterleaf/voice/` | `src/test`, `src/androidTest`, `tools/` |

## Substantial-task contract

Skip this for one-line fixes. For meaningful work, keep the answers in the PR
or in `docs/plans/active/`:

- **Goal** — behavior that should exist
- **Area** — modules/files
- **Constraints** — what must not change (privacy, platforms, public behavior)
- **Acceptance** — observable success
- **Verification** — exact commands
- **Non-goals** — what not to expand into
- **Stop** — when to stop editing

## Review

Implementation and review are separate. A reviewer reads the contract, diff,
and test output — not the implementer's rationale as proof. Check correctness,
regression risk, privacy/security, platform claims, failure behavior, test
quality, extra complexity, stale docs, and unrelated edits.

## Plans

Use [docs/plans/](docs/plans/README.md) so work survives a new session. A later
agent should need this file, the active plan, affected source, and git status.
