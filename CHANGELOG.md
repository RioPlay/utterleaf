# Changelog

## 0.3.1

- Find the Linux NVIDIA toolkit installed at `/opt/cuda` (Arch) in addition to `/usr/local/cuda`.
- Frozen builds now tell the truth about CUDA: the hint names the distro toolkit (`sudo pacman -S cuda cudnn`) or the bundle flag, not `pip install 'utterleaf[cuda]'`.
- Added `utterleaf --cuda-setup` and a **Set up NVIDIA GPU…** button in Settings that print distro-aware steps to enable the GPU, plus `scripts/cuda-setup.sh` which installs CUDA automatically.
- Quiet the microphone input-overflow warning that ALSA-to-Pulse bridging fires once at stream open; real overflows still warn.

## 0.3.0

- New brand icon: a leaf with a speaking-mouth cutout, used for the tray, the Settings window, and the Windows executables.
- Show the tray icon on Linux Wayland desktops (KDE, and GNOME with the AppIndicator extension): the frozen build selects the StatusNotifierItem backend, and `--doctor` prints which backend it picked.
- Reply to recording IPC commands before slow microphone probing, so `utterleaf --toggle` no longer reports a false "not running".
- Find NVIDIA CUDA libraries on Linux without setting `LD_LIBRARY_PATH`.
- Ship the readme and third-party license notices with the macOS and Linux binaries as well as Windows.

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
