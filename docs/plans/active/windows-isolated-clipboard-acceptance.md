# Isolated Windows clipboard acceptance

## Goal and area

Establish native evidence for the Windows clipboard worker's ownership,
cancellation and deadline behavior without reading or changing the interactive
user's clipboard. This follows [clipboard bounds](desktop-clipboard-bounds.md).
Test implementation belongs under `tests/`; production changes require a
separate demonstrated defect and integrator ownership. No desktop packaging,
Android change, user input injection, actual editor paste or microphone capture.

## Status and staged acceptance

September 12: the independently reviewed stage 1 probe could not establish a
private noninteractive window station on this host. Windows rejected the one
randomly named `CWF_CREATE_ONLY` station with access denied (error 5). The root
process's station and thread-desktop identity remained exactly unchanged. The
probe did not retry, elevate, alter an ACL, select an existing station or call a
clipboard API. Stage 1 is unavailable in this environment, so stages 2 and 3
remain gated and were not implemented or run.

1. **Names-only isolation probe:** root test process records its own station and
   thread-desktop identity through read-only metadata queries, creates an owned
   kill-on-close job and a request-gated child. After job assignment, that child
   creates a new randomly named, non-inheritable window station, selects it in that child
   only, creates a named desktop inside it, and selects that thread desktop.
   Verify station/desktop identity and noninteractive flags. Launch a second
   request-gated child with explicit `STARTUPINFO.lpDesktop=station\\desktop`,
   no inherited station/desktop handles, and repeat identity verification there.
   Emit bounded names/flags only. Root rechecks its original station/desktop
   identity afterward and requires equality. **No clipboard APIs in stage 1.**
2. **Synthetic ordinary clipboard:** after stage 1 passes review, run the real
   clipboard implementation only inside identity-checked children in that same
   private station. Validate text/sequence receipts, conditional writes and
   same-text changes using synthetic content. Root stays in its original station.
3. **Synthetic stalled owners:** after ordinary isolation evidence, run a real
   hidden owner window/message loop with controlled delayed rendering and
   `WM_DESTROYCLIPBOARD` stalls. Exercise timeout, cancellation, no late mutation,
   new-owner preservation and cleanup. Record timings and statuses, not content.

This is staged evidence, not user permission polling: the existing task authorizes
necessary reversible development and tests. The stages prevent accidental fallback
to the interactive clipboard before the isolation mechanism is verified.

## Invariants

- Root never calls `SetProcessWindowStation`, `SetThreadDesktop`, `SwitchDesktop`
  or any clipboard API. Do not capture the desktop or inspect WinSta0 clipboard
  content before/after as an isolation check.
- A payload-capable child must be owned before it receives a request. Retain
  exact process handles through cleanup; never reopen an exited child's PID to
  terminate it. Use hidden processes, bounded IPC/waits and job close plus
  terminate/kill/reap fallback.
- Stage 1 uses `CWF_CREATE_ONLY` with a generated `UtterleafIsolation-<UUID>` name
  to create a new station. Require the queried name to match exactly; reject an existing-object result or unexpected
  default identity. Its name must differ from WinSta0; `WSF_VISIBLE` must be false;
  the desktop must match the requested name and report `UOI_IO=false`.
- Named creation requires Windows authorization. Access denied is unavailable,
  with no elevation, ACL/token mutation, unnamed retry or existing-station
  fallback. Inspect `GetLastError` only when a creation call returns NULL.
- Verify identity inside every child before any later-stage clipboard call.
  No retry with an omitted/empty desktop, no opening WinSta0, no ambiguous
  inheritance of multiple station/desktop handles. A failed creation, assignment,
  binding or identity query is an explicit failed/unavailable result.
- Every fixture is synthetic. This is not an isolation boundary against hostile
  same-user processes with sufficient object access, and is never suitable for
  sensitive user fixtures under a permissive default object descriptor.
- All resources belong to the test. Keep the process-lifetime teardown for its
  selected station/desktop; close unselected owned handles. Do not switch the
  active input desktop. Preserve unrelated processes and user data.
- Native tests must be explicitly opt-in and Windows-gated. Ordinary desktop CI
  must not unexpectedly create test desktops or access any clipboard.

## Verification

Independent source review confirmed stage 1 has no clipboard call path,
root-station mutation or default-desktop fallback, and all subprocesses are
request-gated and owned. Mocked tests cover exact identity, API and job failure,
strict IPC, timeout, restricted inherited handles and cleanup without native
clipboard access.

The reviewed opt-in command was:

```powershell
$env:UTTERLEAF_RUN_WINDOWS_CLIPBOARD_ISOLATION='1'
.\.venv\Scripts\python -m pytest -q tests/test_windows_clipboard_isolation.py -k native_names_only_isolation_probe
Remove-Item Env:UTTERLEAF_RUN_WINDOWS_CLIPBOARD_ISOLATION
```

The final native attempt stopped in 0.68 seconds with the bounded receipt
`status='unavailable', parent_preserved=True, reason='station-create',
win32_error=5`. It created no desktop or nested child and performed no clipboard
operation. Access denial is an expected unsupported-host result, but it is not
isolation evidence and cannot unlock stages 2 or 3.

Earlier names-only attempts also stopped before desktop creation. Diagnostics
established that the OS-generated unnamed station already exists (`NULL`, error
183). A stale-error handling bug in the test was fixed, with NULL/error and
successful-handle cases tested, before the single explicit-name attempt above.
None of these results unlocked clipboard tests; parent identity remained unchanged.

## Primary evidence and limits

Microsoft documents that a [window station owns a clipboard](https://learn.microsoft.com/en-us/windows/win32/winstation/window-stations)
and [`SetProcessWindowStation`](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-setprocesswindowstation)
assigns the station used by subsequent clipboard operations. Its
[connection rules](https://learn.microsoft.com/en-us/windows/win32/winstation/process-connection-to-a-window-station)
make a generic child launch unsafe to assume isolated: absent inherited station
handles or explicit desktop routing, an interactive user's child can connect to
WinSta0. [`STARTUPINFO.lpDesktop`](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/ns-processthreadsapi-startupinfow)
can specify both station and desktop. A
[created desktop](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-createdesktopw)
belongs to the calling process's current station.

This test boundary does not establish a clean Windows installation, a frozen
build, interactive native editor behavior, every session policy or all native
kernel deadlines. Keep those release gates explicit. Stop each stage when its
recorded acceptance passes, update evidence, then review the next stage.
