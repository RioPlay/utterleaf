# Product design and usability audit

Reviewed September 9, 2026, for v0.3.7. This is an evidence record and an open
quality backlog, not a declaration that every platform or accessibility scenario
has passed. [Documentation](README.md) · [Interface guidelines](interface.md)

## Findings and changes

| Area | Finding | Resolution and evidence |
| --- | --- | --- |
| Navigation and hierarchy | Marketing headlines made users translate the page title back to its navigation label. | Task names now lead each page. Smaller 80-pixel mascots and a shorter instruction card leave more room for controls; the default Dictation screenshot includes the complete microphone check. |
| Selection state | The selected checkbox mark matched its green background. | A dark mark is visible against green; selected radios also have a contrasting center. Reviewed in real Windows widgets. |
| Keyboard focus | Checkbox focus color matched the page surface. | Contrasting focus colors for checkboxes, radios, and buttons. Tab-order test reaches microphone controls and Close while excluding hidden pages. This is not a screen-reader certification. |
| Footer | Long status messages could compete with Save and Close for width. | Status wraps to the available width. A 760 × 560 regression check verifies both actions remain inside the window and the message does not overlap Close. |
| Error recovery | Save failures left users searching for the invalid field. | Validation errors carry field identity. Settings opens the relevant page, focuses the control, and selects an invalid vocabulary line. Existing validation tests verify that invalid inputs cause no file writes. |
| Choice labels | Hardware and noise controls displayed config tokens such as `auto` and `gpu`. | Readable labels map to the same persisted values. A real-widget test checks selection and programmatic reset synchronization. |
| Feature wording | “Live captions” could be mistaken for system-audio or video captions. | The control is labeled “Preview dictation while recording.” System-audio captions remain planned. |
| Recovery and persistence | Defaults and repeated Settings launches need to preserve work. | Existing cross-process reuse, crash recovery, staged reset, partial-save, and edits-during-save tests remain in the full suite. |
| Privacy during reset | Resetting preferences could re-enable downloads after the user disabled them. | Reset now preserves download and clipboard preferences. A regression test preserves offline mode while other defaults are restored. |
| Local command authentication | The loopback socket accepted control commands without authentication; a read timeout could terminate its listener. | Per-launch secret, bounded requests, atomic endpoint publication, and timeout recovery. Socket tests reject plaintext, wrong-token, and oversized requests, then verify authenticated control still works after a stalled client. |

## Design decisions retained

Privacy and security take precedence over convenience. Do not weaken a privacy
choice as a side effect of repair, add capture without deliberate action, or treat
an unverified destination as evidence of safe text delivery. Audit gaps below
remain open even when the interface appears polished.

- Five stable navigation destinations, explicit Save, and a visible Close action.
- Dark neutral surfaces with green reserved for brand, selection, and action.
- One grouped section per decision; no animation, remote fonts, new UI dependency,
  or decorative control that competes with dictation.
- Utterling remains decorative and secondary to instructions. Recovery precedes
  the artwork catalog in Help.
- The tray stays the default recording indicator; extra overlays are opt-in.
- Platform limitations are stated in setup instructions and release notes.

The default and compact Windows screenshots are reviewed from real Tk widgets
using sample data. The compact window intentionally scrolls; it does not show
every control at once. Save/Close remain outside that scrolling region.

## Remaining release-quality work

| Priority | Work | Evidence needed before claiming completion |
| --- | --- | --- |
| High | Native Wayland shortcuts, focus, and delivery | Actual GNOME, KDE, and wlroots desktops; native editor insertion, failure recovery, and visible recording controls. Xvfb session-branch tests are insufficient. |
| High | Accessibility and display scaling | Screen-reader setup/recovery on supported platforms; keyboard-only microphone and error workflows; 150%/200% scaling and mixed-DPI monitor changes. Current geometry checks cover the tested display environment only. |
| High | Real application delivery | Browser fields, rich-text editors, terminals, focus changes, slow paste consumers, and clipboard format preservation. A sent shortcut is not proof of insertion. |
| High | Microphone interruption recovery | Device removal, Bluetooth reconnection, permission denial, and sleep/wake while capturing. Preserve captured words and make the next action clear. |
| Medium | First-run and performance expectations | Clean user profile, offline relaunch, interrupted model downloads, CPU/GPU failure, and measured cold/warm end-of-speech latency on ordinary hardware. |
| Medium | Long recording behavior | Bounded incremental audio processing and a suitable hold/toggle time policy. Removing the timer alone is not sufficient. |

These items can justify deeper platform integration or a toolkit change. A new
visual framework by itself would not establish dependable dictation or accessible
controls. Keep gaps explicit in [platform testing](platform-testing.md) and
[the roadmap](roadmap.md).

## Local control security boundary

The command socket binds only to loopback and authenticates with a per-launch
secret. Its endpoint file is created with owner-only permissions on POSIX;
Windows uses the user's profile-directory ACLs. This does not protect against
code already running as the same user or an administrator with access to those
files. Do not include endpoint-file contents in diagnostics or bug reports.

Updated clients only use a harmless legacy ping to detect an older instance;
they never downgrade recording, clipboard, or settings commands. Quit and reopen
the updated app after upgrading. The extracted Linux release check uses the
authenticated protocol as well.

## Method

Aden was used for bounded code navigation around Settings state and validation.
Its call relationships were checked against source. Verification combines real
Tk widget tests, full Windows/AlmaLinux suites, screenshots, and packaged CI
checks. Microphone/editor and assistive-technology results must be recorded
separately; they are not inferred from unit-test success.
