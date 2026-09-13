# Windows clipboard operation bounds

## Goal and area

Remove avoidable Windows clipboard reads from final delivery and isolate the one
optional read used to snapshot text for restoration. Put clipboard mutation behind
the same bounded one-shot process boundary because clearing the clipboard can
synchronously enter the previous owner's window procedure. Preserve cancellation,
clipboard ownership, manual copy behavior, privacy and packaged-app operation.
This is a Windows-first D1 follow-up to the
[delivery cancellation plan](desktop-delivery-cancellation.md), not a claim that
all native clipboard calls or other platforms are bounded.

Implementation area is `utterleaf/windows_clipboard.py`, `utterleaf/inject.py`,
the private `--clipboard-worker` route in `utterleaf/__main__.py` and focused
helper/integration tests. The integrator owns injection, CLI routing and docs;
the helper implementer owns the new clipboard module and its unit tests.

## Status

Implemented and independently reviewed in source on September 12. The full
desktop suite passed 936 tests with 12 environment skips in 32.86 seconds. After
a test-only native-process cleanup refinement, the final eight-file focused
suite passed 231 tests in 2.60 seconds, including both native lifecycle checks.
All Tk/UI checks ran. Eleven full-suite skips require an explicitly verified
FFmpeg fixture; one requires Windows symlink privileges.

Two Windows tests use harmless sleeping children: job close terminates its
assigned child, and abrupt parent exit terminates an assigned child whose exact
process handle the test retains before releasing the parent. No clipboard data
or clipboard API is involved. This establishes the tested job lifecycle, not
hostile clipboard-owner behavior. No packaged build or native clipboard mutation
has been performed. Isolated clipboard-owner acceptance and frozen startup
timing remain open.

## Current evidence

The September 12 baseline audit inspected installed Pyperclip 1.11.0 and the
source callers in `inject.py` and `app.py`. Before this change, a normal
restoration-enabled paste could make three synchronous clipboard reads and two
writes. Manual recovery also used a synchronous write. Cancellation was checked
between those calls but could not be observed while one was running.

Pyperclip's Windows backend retries `OpenClipboard` for approximately 500 ms,
then performs `GetClipboardData(CF_UNICODETEXT)` synchronously. Windows permits a
clipboard owner to defer rendering until that read; Microsoft documents a system
wait of up to 30 seconds for delayed data.

The write path is not proven bounded either. `EmptyClipboard` sends
`WM_DESTROYCLIPBOARD` to the previous owner. Microsoft provides a concrete case in
which the new writer hangs while Windows waits for that owner's window procedure.
Ordinary cross-thread `SendMessage` does not return until the receiving window
procedure processes the message. Eager `SetClipboardData(CF_UNICODETEXT, handle)`
avoids making Utterleaf a delayed renderer and transfers the memory handle to the
system, but it occurs after this potentially blocking clear.

`GetClipboardSequenceNumber` increments when clipboard contents change or are
emptied. With delayed rendering it does not increment until the changes are
rendered, so the snapshot must capture the sequence after its text read. The API
documentation gives no application deadline for sequence acquisition. Snapshot
and write receipts are captured inside the child. Final dispatch retains the
existing direct metadata query in the parent, alongside native foreground and
clipboard-settling queries. Those checks do not read clipboard data or ask an
owner to render it, but this change does not establish that every native query,
process-launch call or input dispatch has a hard deadline.
See Microsoft's
[clipboard operations](https://learn.microsoft.com/en-us/windows/win32/dataxchg/clipboard-operations)
[WM_RENDERFORMAT](https://learn.microsoft.com/en-us/windows/win32/dataxchg/wm-renderformat),
[sequence number](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-getclipboardsequencenumber),
[SendMessage](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-sendmessage)
and Microsoft engineering's
[hung-owner example](https://devblogs.microsoft.com/oldnewthing/20121224-00/?p=5763).

## Constraints

- Never put dictated or pre-existing clipboard text in argv, environment
  variables, temporary files, logs or diagnostics. Keep bounded IPC in memory.
- Do not start a detached timeout thread. A timed-out operation must not later
  mutate the clipboard.
- Do not send a paste shortcut after an unconfirmed clipboard write, and never
  retry an operation that may already have changed the clipboard or editor.
- Preserve a newer user clipboard change. Text equality is not an ownership
  token, including when the user copies identical text.
- Keep `copy_text(text) -> bool` and `paste(...)` outcomes compatible unless the
  app integrator explicitly accepts a caller change.
- Keep restoration best-effort. Failure to obtain the optional previous-text
  snapshot must not lose the dictated result or block manual recovery.
- Add no dependency, ambient clipboard watcher, persistent transcript service or
  clipboard history. Reset/settings behavior is outside this change.

## Windows contract

### 1. Private one-shot helper boundary

Use one private child route with versioned read and conditional-write requests.
Each invocation owns its clipboard data handles and mutation calls. Before
sending a request, the parent must place the child in an unnamed,
non-inheritable Windows job configured with `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`.
Ownership setup failure sends no request and returns unavailable. Closing the
parent's last job handle requests termination of all associated processes;
retain the handle through normal completion and use it during deadline/cancel
cleanup. The parent also performs bounded terminate/kill/reap fallback.
See Microsoft's [job objects](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects)
and [job assignment](https://learn.microsoft.com/en-us/windows/win32/api/jobapi2/nf-jobapi2-assignprocesstojobobject).

A write child that times out after mutation may have emptied or replaced the
clipboard. Its private result is `uncertain`; do not dispatch a shortcut or retry.
This is uncertainty about the clipboard, not evidence of editor insertion.

The private child protocol must:

- receive operation, expected sequence and any text through bounded inherited
  stdin; expose no clipboard text or authentication material in argv;
- return a versioned result containing status, sequence number and, for a read,
  at most 1 MiB of UTF-8 text over stdout;
- reject malformed or oversized frames, write no stderr containing clipboard
  data, and never perform an operation other than the requested read or
  conditional write;
- finish within a one-second parent deadline or be terminated, killed if needed
  and reaped;
- reject incomplete or trailing requests at EOF; launch invisibly, using the
  packaged `utterleaf-cli.exe` companion for inherited Python standard streams.

The one-second operation deadline starts after process launch; stop/reap/join
cleanup adds bounded waits. It does not bound the underlying Win32 call or reverse
an existing native side effect. Job ownership covers payload-capable children
if the parent exits abruptly. Before assignment, the child receives no request
and parent exit closes its request pipe; a child stalled in startup might remain
alive in that short gap but cannot reach a clipboard operation through this
protocol. Do not claim universal process-exit timing or successful reaping when
the OS reports failure.

### 2. Optional prior-text snapshot

Read previous clipboard text only when `restore_clipboard` is true and delivery
has not already been cancelled. Run `GetClipboardData(CF_UNICODETEXT)` in one
owned, hidden, one-shot child because another application's delayed renderer is
outside Utterleaf's control. Capture the sequence after `GetClipboardData` returns
and while the clipboard is still open so delayed rendering is reflected in the
snapshot token.

If the clipboard is empty, non-text, larger than the cap, changes during the
snapshot, the child fails, or the deadline expires, continue with no restoration
snapshot. Recheck cancellation before any clipboard mutation. A moved target
retains the existing recovery behavior: copy the result but send no shortcut.

### 3. Dictation write and ownership token

Send a conditional-write request to an owned one-shot child. It opens the
clipboard, verifies the expected sequence while it has exclusive access, then
calls `EmptyClipboard`, writes eager `CF_UNICODETEXT`, obtains the resulting
sequence and closes the clipboard. For a restoration-enabled delivery, the
expected sequence comes from the snapshot. Without restoration, omit the expected
sequence and preserve the current explicit-copy behavior. Recheck cancellation
before sending the request and target before dispatch. When an expected
sequence is present, a mismatch means the user or another app changed the
clipboard; do not overwrite it and do not dispatch paste.

Successful eager `SetClipboardData` plus a nonzero captured sequence is the write
receipt. Do not call `GetClipboardData` merely to compare the text afterward.
If cancellation is observed before mutation, return `cancelled`. If mutation may
have happened but completion or sequence acquisition cannot be established,
return private `uncertain`, leave recovery available and do not dispatch paste.
The public `paste()` result is `fail` (or `cancelled` when the take was cancelled)
because no shortcut was sent. It does not promise that the clipboard is unchanged.
Only uncertainty during or after shortcut dispatch uses the public `uncertain`
outcome that tells the user to check the original editor before copying again.

Cancellation after a confirmed write starts no restoration child. Dictation may
remain on the clipboard; cancellation does not clear OS clipboard history.

Do not claim that `CreateWindowEx`, `EmptyClipboard`, `GlobalAlloc`, `GlobalLock`,
`SetClipboardData`, `CloseClipboard`, `DestroyWindow` or
`GetClipboardSequenceNumber` themselves have an application deadline. The
one-shot process bounds the parent's wait around the group. Killing and reaping a
timed-out write child maps a possibly committed write to `uncertain`.

### 4. Atomic restoration

After a confirmed paste and settling period, restoration may proceed only when:

1. a prior-text snapshot exists;
2. the original target still matches;
3. cancellation has not made delivery uncertain; and
4. the current clipboard sequence still equals the dictation write receipt.

Send a conditional-write child request containing the dictation write receipt and
saved text. The child acquires the clipboard first, rechecks the sequence while it
is exclusively open, then replaces it before releasing the clipboard. A separate
token check followed by a later write leaves a race in which a user's new copy can
be overwritten. Do not read the dictated text again to authorize restoration. If
the sequence changed or cannot be verified, leave the clipboard untouched.

`restore_clipboard=False` performs no snapshot or restoration read. `copy_text`
also performs no snapshot: it uses the same verified eager-write path and the
deadline decision above, then returns true only for a confirmed write. Existing
recovery text remains in memory when a manual copy cannot be confirmed.

## Acceptance

1. A normal Windows delivery with restoration disabled performs no clipboard
   reads. With restoration enabled it performs exactly one optional prior-text
   read and no read after Utterleaf writes dictation.
2. A delayed renderer or an owner stalled in `WM_DESTROYCLIPBOARD` cannot hold the
   delivery worker beyond the child deadline plus bounded terminate/kill/reap
   cleanup in the tested scenarios. A child receives no clipboard request before
   job ownership succeeds. Exercise abrupt parent exit with a harmless owned
   child and distinguish that from the requestless startup gap described above.
3. Snapshot timeout, invalid output, oversized text and non-text clipboard content
   skip restoration without dispatching duplicate shortcuts or losing in-memory
   recovery.
4. Cancellation observed before launching a write makes no clipboard change. A
   cancellation, timeout or failure after launch returns private `uncertain`
   unless the child proves no mutation began, and sends no paste shortcut. Public
   insertion status must distinguish clipboard uncertainty from editor dispatch.
5. A user copy between snapshot and dictation write prevents the write. A user
   copy between dictation write and restoration prevents restoration, even when
   its text equals the dictated or previous text.
6. Sequence verification and restoration replacement are exercised as one
   clipboard-open critical section; a barrier test proves no intervening user
   write is overwritten.
7. Manual **Copy**, **Copy last dictation**, focus-moved recovery and
   `restore_clipboard=False` retain their current observable behavior and do not
   require a read child; their writes still use the bounded child boundary.
8. Child stdin/stdout are bounded and contain no diagnostic echo. Tests inspect
   argv, environment, logs and filesystem use to confirm clipboard text is absent.
9. Source and packaged child routing both terminate cleanly. The frozen smoke test
   confirms the private mode does not open the main app or expose clipboard data
   without its inherited request channel.

## Verification

Start with mocked unit tests; they must not access or mutate the real clipboard:

```powershell
.\.venv\Scripts\python -m pytest tests/test_windows_clipboard.py tests/test_windows_delivery.py tests/test_inject.py tests/test_inject_clipboard_identity.py tests/test_delivery_cancellation.py tests/test_review_ui.py -ra
```

Then run affected app/CLI and privacy/packaging tests chosen by the integrator.
Final source verification used:

```powershell
.\.venv\Scripts\python -m pytest -ra
.\.venv\Scripts\python -m pytest tests/test_windows_clipboard.py tests/test_windows_delivery.py tests/test_inject.py tests/test_inject_clipboard_identity.py tests/test_delivery_cancellation.py tests/test_review_ui.py tests/test_app.py tests/test_speech_end_app.py -ra
git diff --check
```

The final focused suite followed the full suite because review replaced the
native test's PID-based cleanup with a retained-handle handshake. Production
code was unchanged between those runs. Independent review covered source,
protocol/failure tests, callers and native lifecycle evidence; findings fixed
included malformed response handling, pipe-close ownership, frozen stdio,
native resource cleanup, job assignment before payload, portable mocks and
accurate **Copy could not be confirmed** recovery wording.

After independent source review, use a separate Windows test session or virtual
machine whose clipboard never contains user data. Seed that isolated clipboard
with synthetic content to check contention, a deliberately slow delayed-rendering
owner, a stalled `WM_DESTROYCLIPBOARD` handler, same-text sequence changes,
cancellation barriers, hidden child startup and packaged routing. Report timings
without clipboard content. Replacing a real clipboard with a synthetic sentinel
and restoring only its plain text would discard rich formats and is not a valid
way to preserve a user's clipboard. Do not run the hostile-owner harness in the
active user's clipboard session. Unit tests do not establish native behavior.

## Cross-platform notes and non-goals

The macOS and Linux observations remain design input, not this implementation:
Pyperclip's `pbcopy`, `pbpaste`, `xclip`, `xsel`, `wl-copy` and `wl-paste` paths
wait without application deadlines. X11 and Wayland writers may keep a process
alive to serve selection data. A process id or process-group id only shows that a
process exists; it does not prove that it still owns the current selection, so it
must not authorize restoration. Token-check and replacement need a platform
ownership primitive or another atomic mechanism.

Do not add Linux process-group restoration, a cross-platform IPC daemon, rich
clipboard formats or native editor cancellation in this pass. Each platform needs
its own ownership evidence and native acceptance before changing restoration.

## Remaining acceptance and stop

- Measure the one-second deadline against frozen companion startup. Source
  `pythonw.exe` invalid-input routing passed without clipboard API access; that
  does not establish a packaged build.
- In an isolated Windows session, verify bounded waiting and cleanup while a
  clipboard owner delays rendering or stalls in `WM_DESTROYCLIPBOARD`.
- Verify same-text sequence changes, conditional replacement and slow-editor
  behavior natively. Mocked critical sections do not establish OS behavior.

Stop after Windows behavior meets the acceptance checks, focused tests pass,
native limitations are recorded truthfully and independent review is clean. Do
not expand into macOS/Linux ownership or claim complete clipboard atomicity.
