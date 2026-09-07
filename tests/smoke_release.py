"""Check an owned Windows build with isolated settings, then close the test window."""
from pathlib import Path
import os
import subprocess
import time
import sys
import struct

root = Path(__file__).resolve().parents[1]
release = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else root / "artifacts" / "release-final" / "Utterleaf"
cli = release / "utterleaf-cli.exe"
if not cli.exists():
    cli = release / "utterleaf.exe"
else:
    for name in ("utterleaf.exe", "utterleafw.exe"):
        binary = (release / name).read_bytes()
        pe = struct.unpack_from("<I", binary, 0x3C)[0]
        assert struct.unpack_from("<H", binary, pe + 24 + 68)[0] == 2, f"{name} must use Windows GUI subsystem"
    print("Both app executables use the Windows GUI subsystem (no launch console)")
env = dict(os.environ, APPDATA=str(root / "artifacts" / "smoke-profile"))
for args in (["--help"], ["--polish", "um we should ship it"], ["--doctor", "--offline"]):
    result = subprocess.run([str(cli), *args], env=env,
                            capture_output=True, text=True, timeout=45)
    print(f"{' '.join(args)}: exit {result.returncode}")
    if args[0] == "--polish":
        assert result.stdout.strip() == "We should ship it.", (result.stdout, result.stderr)
    elif args[0] == "--help":
        assert result.returncode == 0, result.stderr
    else:
        (root / "artifacts" / "doctor.txt").write_text(result.stdout + result.stderr, encoding="utf-8")
        assert result.returncode == 0, result.stdout + result.stderr

result = subprocess.run([str(cli), "--polish", "Make a bolded list 1 2 3."], env=env,
                        capture_output=True, text=True, timeout=20)
assert result.returncode == 0 and result.stdout.strip() == "- 1\n- 2\n- 3", (result.stdout, result.stderr)
print("Packaged spoken list formatting: passed")

process = subprocess.Popen([str(release / "utterleaf.exe"), "--settings"], env=env)
try:
    time.sleep(4)
    assert process.poll() is None, "Settings exited unexpectedly"
    print("Frozen settings window: launched and remained open")
finally:
    if process.poll() is None:
        process.terminate()
    process.wait(timeout=5)
