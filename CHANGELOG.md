# Changelog

## 0.2.5

- Record at the input device's native sample rate and convert to 16 kHz for transcription, including anti-alias filtering.
- Prevent Xorg tray title encoding crashes at startup and on status changes.
- Report microphone initialization failures separately from model failures and continue model initialization.
- Test extracted Linux binaries with the tray both enabled and disabled.

## 0.2.4

- Bundle both pynput Xorg backends and the correct pystray Xorg backend in Linux binaries.
- Use compositor-configured desktop shortcuts (`utterleaf --toggle`) on Wayland instead of unreliable XWayland global key listening.
- Gate Linux releases on frozen Settings and app startup, IPC control, and clean shutdown tests under X11 and the Wayland session branch.

## 0.2.2

- Renamed Mindict to Utterleaf before the first public release, including commands and application data paths.

- Fixed Windows indicator corner clipping and long captions in the Tk indicator.
- Preserved contractions and sentence spacing, including after long recordings; kept list mentions as prose.
- Improved Linux paste selection and cross-platform checks.
- Removed PyAV/FFmpeg and its GPL codec payload from Windows distributions.
- Automated third-party notices and license collection for binary builds.
- Relicensed from MIT to Apache License 2.0.
