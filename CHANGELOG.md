# Changelog

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
