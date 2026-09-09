# Wayland setup and troubleshooting

Utterleaf's Wayland support currently needs manual desktop setup. Recognition
runs locally, but shortcuts, tray visibility, and inserting text depend on the
desktop. Passing Linux CI does not establish working native Wayland dictation:
the existing release smoke test uses Xvfb, including its simulated Wayland run.

## Identify the failing step

From the extracted release directory, run `./utterleaf --doctor`. For a source
install, use `.venv/bin/python -m utterleaf --doctor`. Include the distro, desktop,
and release version when reporting a problem. Diagnostics do not include your
dictated text; review local paths and device names before sharing.

| Symptom | Check |
| --- | --- |
| App or Settings does not open | Launch from a terminal and retain the error. Tk and the current input imports require a working XWayland display (`DISPLAY`); a native Wayland socket alone is insufficient. |
| No tray icon | GNOME needs an AppIndicator extension. Source installs need GI/AppIndicator bindings visible inside their Python environment. Try `./utterleaf --no-tray` in a terminal, then control it with CLI commands from a second terminal; this mode does not open a control window. |
| Configured hotkey does nothing | Set a **desktop custom shortcut** to the absolute executable path followed by `--toggle`. Utterleaf must already be running. |
| Recording works but text never appears | Check clipboard access and a compatible key helper as described below. |
| Microphone check fails | Follow [microphone troubleshooting](microphone-troubleshooting.md); changing a paste helper cannot fix audio capture. |

## Start and stop recording

Bind a custom shortcut in your desktop's keyboard settings, for example:

```text
/home/yourname/Applications/Utterleaf/utterleaf --toggle
```

Use your actual extracted path, quoted if it contains spaces. For source installs,
use the absolute virtualenv Python path followed by `-m utterleaf --toggle`.
Press once to record and again to finish. The in-app hotkey listener is disabled
on Wayland, so push-to-hold and global Escape cancellation are unavailable.
The existing recording time limit still applies.

## Clipboard and inserting text

Install `wl-clipboard` for `wl-copy` and `wl-paste`. Test with harmless sample
text in a disposable document. Avoid switching focus while a take processes:
Utterleaf cannot verify the active native Wayland window with its current backend.

Automatic insertion additionally requires one of these:

- `wtype`: requires the compositor's virtual-keyboard protocol. It is **not a
  universal GNOME/KDE solution**. An unsupported-protocol error means installing
  it succeeded but the desktop cannot use it.
- `ydotool`: requires a running daemon and permission to access its socket/input
  device. Follow your distro's setup instructions; installing only the command
  is insufficient. Run Utterleaf as your ordinary user, not as root.

Starting in v0.3.5, failed Wayland helpers no longer fall back to `xdotool`.
X11's helper can report success without pasting into a native Wayland app. Failed
insertion leaves successfully copied text on the clipboard for manual paste.
`--copy-last` can also recover the most recent take during its two-minute slot.
Installed helper names in `--doctor` are inventory, not an end-to-end paste test.

Upstream details: [wtype protocol requirements](https://github.com/atx/wtype),
[ydotool daemon requirements](https://github.com/ReimuNotMoe/ydotool), and
[wl-clipboard](https://github.com/bugaevc/wl-clipboard).

## Still needed

Native GNOME, KDE, and wlroots desktop tests must cover launch, visible controls,
record/stop shortcuts, clipboard recovery, and actual delivery into a native
Wayland editor. Portal-based shortcuts/input are future work; these fixes do not
implement them or remove the XWayland requirement.
