# Build an onedir distribution:  pyinstaller packaging/utterleaf.spec
# Output lands in dist/Utterleaf. The app downloads its own model on first run,
# so nothing heavy is bundled here. Works on Windows, macOS, and Linux hosts.
#
# Windows defaults to a GUI executable. utterleaf-cli is the explicit diagnostic
# console entry, and utterleafw remains a windowless compatibility entry.
# macOS needs a signed .app bundle and Linux an AppImage; both
# wrap this same onedir COLLECT.

import sys
import os
import importlib.util
from pathlib import Path

from PyInstaller.building.api import EXE, COLLECT, PYZ
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

datas = collect_data_files("faster_whisper")
project_root = Path(SPECPATH).parent
# The readme travels with every build so an extracted download explains itself.
datas.append((str(project_root / "README.md"), "."))

# packaging/stubs holds import-time stand-ins (see stubs/av/__init__.py). It must
# come first so modulegraph resolves `import av` to the stub, never to the real
# PyAV — its bundled GPL FFmpeg is excluded by our distribution policy.
pathex = [str(project_root / "packaging" / "stubs"), str(project_root)]

# Platform-specific backends: pystray and pynput both first-class support
# hidden-importing only what the host OS provides.
if sys.platform == "win32":
    hidden = ["pystray._win32", "pynput.keyboard._win32", "pynput.mouse._win32"]
elif sys.platform == "darwin":
    hidden = ["pystray._darwin", "pynput.keyboard._darwin", "pynput.mouse._darwin"]
else:
    # Bundle every Linux pystray backend so runtime selection follows the host.
    # The appindicator backend (StatusNotifierItem) is what KDE and GNOME-with-
    # AppIndicator-extension actually display; XEmbed is the bare-X11 fallback.
    # PyGObject and the AyatanaAppIndicator3 typelib must be installed on this
    # build host for the SNI backend to bundle; otherwise the frozen app quietly
    # falls back to the X11 tray, which Wayland sessions do not display.
    hidden = [
        "pystray._appindicator",
        "pystray._gtk",
        "pystray._xorg",
        "pynput.keyboard._xorg",
        "pynput.mouse._xorg",
    ]

# Optional accelerated edition. DLLs must retain their package layout so the
# runtime's NVIDIA discovery can find them. The default stays a small CPU build.
binaries = []
if os.environ.get("UTTERLEAF_BUNDLE_CUDA") == "1":
    for package in ("nvidia.cublas", "nvidia.cudnn", "nvidia.cuda_runtime", "nvidia.cuda_nvrtc"):
        if importlib.util.find_spec(package) is None:
            raise RuntimeError(f"Install the CUDA extras before bundling: {package} is missing")
        hidden.append(package)
        binaries.extend(collect_dynamic_libs(package))

a = Analysis(
    [str(project_root / "utterleaf" / "__main__.py")],
    pathex=pathex,
    binaries=binaries,
    datas=datas,
    hiddenimports=hidden,
    hookspath=[str(project_root / "packaging" / "hooks")],
    runtime_hooks=[],
    excludes=["matplotlib", "scipy", "pandas", "IPython", "pytest"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exes = [
    EXE(
        pyz,
        a.scripts,
        [],
        name="utterleaf",
        console=sys.platform != "win32",
        exclude_binaries=True,
    )
]
if sys.platform == "win32":
    exes.append(
        EXE(pyz, a.scripts, [], name="utterleaf-cli", console=True, exclude_binaries=True)
    )
    # Only the runw bootloader exists for a windowless exe; macOS/Linux bundle
    # wrappers ship later from the .app / AppImage specs.
    exes.append(
        EXE(
            pyz,
            a.scripts,
            [],
            name="utterleafw",
            console=False,
            exclude_binaries=True,
        )
    )

COLLECT(
    *exes,
    a.binaries,
    a.datas,
    name="Utterleaf",
)
