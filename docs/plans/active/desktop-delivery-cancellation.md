# Bounded desktop delivery and cancellation

## Goal and area

Finish the desktop roadmap's paste responsiveness follow-up. External paste
helpers must finish or fail within a bounded interval, and Esc/quit must signal an
in-flight delivery without waiting for the capture lock. Preserve explicit
recovery when delivery fails or its outcome cannot be established.

The delivery owner edits `utterleaf/inject.py` and `tests/test_inject.py`.
The integrator owns `utterleaf/app.py`, affected app tests and documentation.
Android, capture algorithms, Settings and packaged releases are separate work.

## Constraints

- Preserve existing target checks, clipboard ownership/restore preferences and
  observed-insertion receipts. Never retry a possibly delivered paste automatically.
- Cancellation before dispatch sends no paste shortcut. Once the OS accepted
  a shortcut, cancellation cannot retract inserted text; report uncertainty rather
  than claiming nothing happened or automatically inserting again.
- Bound helper execution, cleanup and waits. Kill/reap owned subprocesses after
  cancellation/timeout; do not kill unrelated processes or log dictated content.
- A new take cannot clear the cancellation state of an older delivery. Keep
  per-job identity separate from app-wide capture locking.
- Keep public callers compatible, avoid new dependencies and retain manual
  clipboard recovery. Test with synthetic content and mocked platform helpers.

## Acceptance and verification

1. A stalled macOS/Linux helper times out, is cleaned up, and triggers no fallback
   paste attempt that might duplicate input.
2. Esc before dispatch and during helper waits propagates promptly; required
   modifier release and clipboard cleanup still run. A later job works normally.
3. New clipboard ownership, changed targets, failed helpers and uncertain dispatch
   preserve the existing safety guarantees and provide truthful recovery/status.
4. Speech-end review and manual dictation use the same delivery contract without
   stale-job insertion or capture-lock cancellation deadlock.

Run `.\.venv\Scripts\python -m pytest tests/test_inject.py` first, then affected
app/review/interruption tests. Run full desktop pytest after app integration and
independent review. Inspect actual failures; mocked platform branches are not
native Windows/macOS/Linux paste evidence.

## Non-goals and stop

No rich-clipboard redesign, compositor/portal integration, new editor adapter,
automatic retry, UI rewrite or release build. Stop editing this slice after the
named cancellation/failure checks and independent review pass, then update the
desktop roadmap and continue the completion gauntlet. Native platform acceptance
remains explicitly open.

## Status

September 12: helper implementation and app integration passed independent
review. App tests use real thread synchronization to check cancellation while
delivery holds the capture lock, queue removal, retained cancellation of older
jobs, review focus waits and shutdown. Review found and verified fixes for Windows
partial-dispatch classification/key release, final target checks, restoration-off
cancellation, late cancellation discarding newer work, and post-shutdown recovery
or receipt commits. Uncertain delivery has visible tray status even with the
floating indicator disabled. The independent focused suite passed 167 tests;
the final full desktop suite passed 860 tests with 12 skips in 31.00 seconds. All
Tk/UI checks ran. Eleven skips require explicit FFmpeg fixtures and one requires
Windows symlink privileges.

### Remaining bound limitations

The subsequent [Windows clipboard follow-up](desktop-clipboard-bounds.md)
replaces Windows data reads/writes with an owned one-shot child and conditional
restoration, independently reviewed in source. Windows foreground,
sequence and settling metadata queries retain their native limits. macOS/Linux
`pyperclip.copy/paste` backends remain synchronous and outside the paste-helper
deadline. Signaling Esc promptly does not establish an end-to-end cancellation
deadline. A detached timeout thread that could write after cancellation is not
an acceptable substitute. Native clipboard/editor acceptance remains open.

`edit_target.replace` uses synchronous native editor calls. The app checks its
job signal immediately before and after the call; cancellation during a dispatched
edit cannot interrupt or retract that native operation. Such a result is treated
as uncertain, without a retry or saved edit receipt. These guards do not make
native delivery atomic or establish an end-to-end cancellation deadline.

If a shortcut may have been dispatched, leave the current dictated clipboard
payload in place rather than restoring unrelated clipboard text that a late
consumer might insert. Preserve newer clipboard ownership. Report uncertainty
and require the user to check the field before choosing recovery; this is not
automatic clipboard clearing after cancellation.
