"""Exercise the shipped Linux executable under Xvfb, without audio or downloads.

Run with: xvfb-run -a python tests/smoke_linux_release.py dist/Utterleaf
This tests X11 and the Wayland session branch with an X display. It is not a
test of a real Wayland compositor, its global shortcuts, or native-app paste.
"""
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time


def command(exe, env, *args):
    result = subprocess.run([str(exe), *args], env=env, capture_output=True,
                            text=True, timeout=30, cwd=exe.parent)
    assert result.returncode == 0, (args, result.stdout, result.stderr)
    return result.stdout.strip()


def run(release):
    release = Path(release)
    assert (release / "_internal" / "README.md").is_file(), "readme missing from the release"
    assert (release / "THIRD-PARTY-NOTICES.md").is_file(), "third-party notices missing from the release"
    with tempfile.TemporaryDirectory(prefix="utterleaf-frozen-") as folder:
        root = Path(folder)
        shutil.copytree(release, root / "Utterleaf")
        exe = root / "Utterleaf" / "utterleaf"
        for session, tray in (("x11", False), ("x11", True), ("wayland", False), ("wayland", True)):
            profile_name = f"{session}-tray-{tray}"
            env = dict(os.environ, XDG_CONFIG_HOME=str(root / profile_name),
                       XDG_SESSION_TYPE=session)
            for key in ("PYTHONPATH", "PYNPUT_BACKEND", "PYNPUT_BACKEND_KEYBOARD",
                        "PYNPUT_BACKEND_MOUSE", "PYSTRAY_BACKEND", "WAYLAND_DISPLAY"):
                env.pop(key, None)
            if session == "wayland":
                # Deliberately exercise Wayland detection with an XWayland-like
                # X display; no compositor or paste is being simulated.
                env["WAYLAND_DISPLAY"] = "wayland-ci-session-branch"
            profile = root / profile_name / "utterleaf"
            profile.mkdir(parents=True)
            (profile / "config.toml").write_text(
                'allow_network = false\nbeep = false\nindicator = false\n', encoding="utf-8")
            app = None
            output = None
            try:
                assert command(exe, env, "--polish", "um we should ship it") == "We should ship it."
                doctor = command(exe, env, "--doctor", "--offline")
                assert "hotkey parse: ok" in doctor
                tray_line = next(
                    (line for line in doctor.splitlines() if line.startswith("tray backend: ")), ""
                )
                assert tray_line, doctor
                expected = os.environ.get("UTTERLEAF_EXPECT_TRAY_BACKEND")
                if expected:
                    assert tray_line == f"tray backend: {expected}", tray_line
                with tempfile.TemporaryFile(mode="w+") as output:
                    settings = subprocess.Popen([str(exe), "--settings"], env=env,
                                                cwd=exe.parent, stdout=output, stderr=output)
                    try:
                        time.sleep(3)
                        output.seek(0)
                        assert settings.poll() is None, output.read()
                        # A second frozen launch must activate and exit, not
                        # leave another Settings window/process behind.
                        assert command(exe, env, "--settings") == ""
                        assert settings.poll() is None, "Activation closed the original Settings"
                    finally:
                        if settings.poll() is None:
                            settings.terminate()
                        settings.wait(timeout=10)

                with tempfile.TemporaryFile(mode="w+") as output:
                    args = [str(exe), "--offline"] + ([] if tray else ["--no-tray"])
                    app = subprocess.Popen(args, env=env,
                                           cwd=exe.parent, stdout=output, stderr=output)
                    try:
                        deadline = time.monotonic() + 30
                        while time.monotonic() < deadline:
                            output.seek(0)
                            assert app.poll() is None, output.read()
                            log = profile / "utterleaf.log"
                            ready = "Tray ready" if tray else "Dictation control:"
                            if log.exists() and ready in log.read_text():
                                break
                            time.sleep(.1)
                        else:
                            raise AssertionError("Frozen app did not finish startup")
                        port = json.loads((profile / "instance.json").read_text())["port"]
                        with socket.create_connection(("127.0.0.1", port), timeout=5) as connection:
                            connection.sendall(b"ping\n")
                            assert connection.recv(128).strip() == b"ok"
                        assert command(exe, env, "--stop") == "ok"
                        if session == "wayland":
                            assert "global key listening disabled" in log.read_text()
                            assert command(exe, env, "--toggle") == "ok"
                            assert command(exe, env, "--stop") == "ok"
                        assert command(exe, env, "--quit") == "ok"
                        assert app.wait(timeout=10) == 0
                        print(f"{session}, tray={tray}: frozen imports, Settings, app startup, IPC and shutdown passed")
                    finally:
                        if app.poll() is None:
                            app.terminate()
                            app.wait(timeout=10)
            except BaseException:
                # A dead or misbehaving instance must leave evidence behind:
                # the captured output plus the frozen app's own log.
                print(f"--- diagnostics for {session}, tray={tray} ---", flush=True)
                if "app" in locals() and app is not None:
                    print(f"app.poll(): {app.poll()}", flush=True)
                try:
                    output.seek(0)
                    print("--- captured output ---\n" + output.read(), flush=True)
                except Exception:
                    pass
                app_log = profile / "utterleaf.log"
                if app_log.exists():
                    tail = "\n".join(app_log.read_text().splitlines()[-40:])
                    print("--- utterleaf.log tail ---\n" + tail, flush=True)
                raise


if __name__ == "__main__":
    run(Path(sys.argv[1]).resolve())
