Compiled Utterleaf binaries for Windows, macOS, and Linux. Python is bundled; no Python installation or source build is required.

| Platform | Download | Run after extracting the entire archive |
| --- | --- | --- |
| Windows x64 | `Utterleaf-windows-x64-cpu.zip` | `Utterleaf/utterleaf.exe` |
| macOS Apple Silicon (arm64) | `Utterleaf-macos-arm64.tar.gz` | `./Utterleaf/utterleaf` |
| Linux x64 (Ubuntu 24.04 or compatible) | `Utterleaf-linux-x64.tar.gz` | `./Utterleaf/utterleaf` |

Keep the `_internal` directory beside the executable. First launch downloads the speech model; speech recognition then runs locally on the CPU. Model weights and optional CUDA libraries are not bundled.

Windows uses Ctrl+Win for dictation. macOS and Linux use Ctrl+Shift+Space. macOS requires Microphone and Accessibility permissions. Linux requires a desktop session and a paste helper (`xdotool` on X11, `wtype` on Wayland). Wayland users can bind a desktop shortcut to `utterleaf --toggle`.

These builds are unsigned; macOS is not notarized. The macOS and Linux packages are portable executable directories, not installers. The macOS download is for Apple Silicon, not Intel Macs. Native macOS/Linux microphone and paste interactions have not been manually verified.

All three binaries were built and passed frozen CLI smoke checks on native GitHub Actions runners. Windows, macOS, and Linux source test jobs passed. Publication verifies that the build revision matches the release tag and all five build/test jobs succeeded.

`SHA256SUMS.txt` verifies the three downloadable archives. The Windows archive also contains executable checksums.
