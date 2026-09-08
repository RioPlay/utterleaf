"""Generate packaging/utterleaf.ico from the leaf badge renderer.

Run before packaging (build.ps1 does): python packaging/make_icon.py
The committed .ico keeps the repository browsable; regeneration keeps it in
sync with the tray icon drawn by utterleaf.theme.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utterleaf.theme import leaf_master

SIZES = ((16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256))


def main() -> int:
    out = Path(__file__).resolve().parent / "utterleaf.ico"
    leaf_master("idle").save(out, format="ICO", sizes=list(SIZES))
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
