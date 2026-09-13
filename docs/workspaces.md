# Active development workspaces

September 12, 2026: desktop and Android development were accumulating on an old
Android editing branch. Preserve that mixed state as a local checkpoint, then use
separate branches and worktrees for each deliverable.

| Branch | Purpose | Next work |
| --- | --- | --- |
| `checkpoint/mixed-work-20260912` | Preserved mixed development snapshot; not a release or PR | Recovery/reference only; leave the original source environment intact |
| `release/desktop-0.4.6rc1` | Windows x64 CPU prerelease from current main | Finish CI artifact verification, publish an explicit preview, then continue desktop development |
| `feat/android-keyboard-hardening` | Original Android keyboard from current main | Integrate saved Android changes, preserve newer main fixes, verify long-press defaults and complete device gates |

The desktop release uses `desktop-v0.4.6-rc.1`; stable desktop `v*` and Android
`android-v*` releases remain separate. Read the platform roadmap and active plan
in the owning checkout. A green test in one checkout does not validate another.

Machine-specific paths, checkpoint revisions and audit receipts live locally in
`.grok/workspaces.json`. Existing older worktrees and branches are retained until
their unique commits and release evidence have been accounted for. Do not prune
or delete them merely because their names look obsolete.

The shared Python environment remains attached to the original source directory.
Release checks scope `PYTHONPATH` to the release checkout and do not redirect the
editable installation. Build outputs, models, test scratch and user data stay out
of commits. See [development boundaries](development-boundaries.md).
