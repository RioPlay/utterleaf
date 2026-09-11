"""Verify IME process recovery against a separate synthetic editor on an emulator.

Install the foundation debug/test APKs and opt-in recoveryHost debug APK first.
The controller kills only the verified experimental IME process. No instrumentation
is started after that kill: subsequent input comes from actual keyboard touches.
"""
import argparse
import json
from pathlib import Path
import re
import subprocess
import time
import uuid

IME = "org.utterleaf.keyboard.experimental"
HOST = "org.utterleaf.keyboard.recoveryhost"
COMPONENT = IME + "/org.utterleaf.keyboard.UtterleafIme"
TEST = "org.utterleaf.keyboard.ImeProcessRecoveryProbeTest"
RUNNER = IME + ".test/androidx.test.runner.AndroidJUnitRunner"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--adb", required=True)
    parser.add_argument("--serial", default="emulator-5554")
    parser.add_argument("--logs", type=Path, default=Path("ime-recovery-logs"))
    args = parser.parse_args()
    if not re.fullmatch(r"emulator-[0-9]+", args.serial):
        parser.error("This synthetic process-kill probe requires an emulator serial")
    base = [args.adb, "-s", args.serial]

    def adb(*command, check=True):
        result = subprocess.run(base + list(command), capture_output=True, text=True, timeout=30)
        if check and result.returncode:
            raise RuntimeError(result.stderr or result.stdout)
        return result.stdout.strip()

    if adb("shell", "getprop", "ro.kernel.qemu") != "1":
        raise RuntimeError("Device did not identify itself as an emulator")
    uids = {package: adb("shell", "run-as", package, "id", "-u") for package in (IME, HOST)}
    if any(not uid.isdecimal() for uid in uids.values()) or uids[IME] == uids[HOST]:
        raise RuntimeError("Could not verify separate debuggable host and IME UIDs")
    previous = adb("shell", "settings", "get", "secure", "default_input_method")
    if previous not in ("", "null") and not re.fullmatch(r"[A-Za-z0-9_.]+/[A-Za-z0-9_.]+", previous):
        raise RuntimeError("Unsupported prior IME component spelling")
    previous_enabled = set(adb("shell", "ime", "list", "-s").splitlines())
    enabled = COMPONENT in previous_enabled
    scales = {name: adb("shell", "settings", "get", "global", name) for name in
              ("window_animation_scale", "transition_animation_scale", "animator_duration_scale")}
    if any(value != "null" and not re.fullmatch(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)", value)
           for value in scales.values()):
        raise RuntimeError("Unsupported animation scale setting")
    token = uuid.uuid4().hex
    relative = "no_backup/ime-recovery-" + token
    logs = args.logs.resolve() / token
    logs.mkdir(parents=True, exist_ok=False)

    def state(package, file):
        value = adb("shell", "run-as", package, "cat", relative + "/" + file, check=False)
        try:
            return json.loads(value)
        except (ValueError, TypeError):
            return None

    def wait_for(description, predicate, timeout=30):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            value = predicate()
            if value:
                return value
            time.sleep(0.2)
        raise TimeoutError(description)

    def verified_pid(package, pid):
        pid = str(pid)
        if not pid.isdecimal() or pid not in adb("shell", "pidof", package, check=False).split():
            raise RuntimeError("PID does not belong to expected fixture package")
        status = adb("shell", "run-as", package, "cat", f"/proc/{pid}/status")
        match = re.search(r"^Uid:\s+(\d+)", status, re.MULTILINE)
        if match is None or match.group(1) != uids[package]:
            raise RuntimeError("Fixture process UID mismatch")
        return pid

    def tap(point):
        x, y = point["x"], point["y"]
        if not isinstance(x, int) or not isinstance(y, int) or min(x, y) < 0:
            raise RuntimeError("Invalid measured touch coordinates")
        adb("shell", "input", "tap", str(x), str(y))

    def host_text(expected):
        current = state(HOST, "state.json")
        if (current and current["text"] == expected and
                current["selection_start"] == len(expected) and current["selection_end"] == len(expected)):
            return current
        return None

    def visible_empty_host():
        current = host_text("")
        return current if current and current["ime_visible"] else None

    prepare = None
    evidence = {"emulator": args.serial, "token": token, "uids": uids,
                "previous_ime": previous, "previous_enabled": sorted(previous_enabled),
                "previous_animation_scales": scales}
    try:
        # Match the real-touch suite: settled surfaces and framework visibility precede input.
        for name in scales:
            adb("shell", "settings", "put", "global", name, "0")
        with (logs / "prepare.log").open("w", encoding="utf-8") as output:
            prepare = subprocess.Popen(base + ["shell", "am", "instrument", "-w", "-r",
                "-e", "class", TEST, "-e", "recoveryToken", token, RUNNER],
                stdout=output, stderr=subprocess.STDOUT, text=True)
            wait_for("Prepare did not start", lambda: state(IME, "waiting.json"))
            adb("shell", "ime", "enable", COMPONENT)
            adb("shell", "ime", "set", COMPONENT)
            adb("shell", "am", "start", "-W", "-n", HOST + "/.RecoveryHostActivity",
                "--es", "probeToken", token)
            ready = wait_for("Real IME keyboard did not become ready",
                             lambda: state(IME, "ready.json"), timeout=60)
            if ready["token"] != token:
                raise RuntimeError("IME readiness token mismatch")
            old_pid = verified_pid(IME, ready["ime_pid"])
            baseline = wait_for("Synthetic editor/IME did not become visible", visible_empty_host)
            verified_pid(HOST, baseline["host_pid"])
            keys = ready["keys"]
            tap(keys["a"])
            tap(keys["space"])
            baseline = wait_for("Pre-kill keyboard touches did not reach host", lambda: host_text("a "))
            evidence.update({"ready": ready, "before_kill": baseline, "killed_ime_pid": old_pid})
            if adb("shell", "settings", "get", "secure", "default_input_method") != COMPONENT:
                raise RuntimeError("Experimental keyboard is no longer selected")
            verified_pid(IME, old_pid)
            adb("shell", "run-as", IME, "kill", "-9", old_pid)
            prepare.wait(timeout=30)
        if old_pid in adb("shell", "pidof", IME, check=False).split():
            raise RuntimeError("Killed IME PID remains alive")

        def rebound():
            candidates = [pid for pid in adb("shell", "pidof", IME, check=False).split() if pid != old_pid]
            current = host_text("a ")
            if (candidates and current and current["ime_visible"] and
                    current["generation"] > baseline["generation"]):
                return candidates[0], current
            return None

        # Android clears input-shown state on IME disconnection; a user re-show is separate evidence.
        try:
            new_pid, rebound_host = wait_for("No automatic visible rebound", rebound, timeout=10)
            evidence["recovery_mode"] = "automatic_visible_rebound"
        except TimeoutError:
            current = wait_for("Host lost pre-kill text", lambda: host_text("a "))
            tap(current["field_center"])
            evidence["recovery_mode"] = "same_field_user_reshow"
            new_pid, rebound_host = wait_for("IME did not rebind after same-field re-show", rebound)
        verified_pid(IME, new_pid)
        if adb("shell", "settings", "get", "secure", "default_input_method") != COMPONENT:
            raise RuntimeError("Experimental keyboard selection changed during recovery")
        for field in ("host_pid", "instance", "window_width", "window_height", "ime_bottom"):
            if rebound_host[field] != baseline[field]:
                raise RuntimeError("Host process/activity/geometry changed across IME death")
        evidence["rebound_ime_pid"] = new_pid
        evidence["after_rebind"] = rebound_host
        tap(keys["b"])
        tap(keys["space"])
        typed = wait_for("Post-rebind touches did not type into original host", lambda: host_text("a b "))
        tap(keys["delete"])
        deleted = wait_for("Post-rebind delete did not edit original host", lambda: host_text("a b"))
        if deleted["host_pid"] != baseline["host_pid"] or deleted["instance"] != baseline["instance"]:
            raise RuntimeError("Host was recreated during post-rebind typing")
        verified_pid(IME, new_pid)
        evidence.update({"typed": typed, "deleted": deleted, "result": "pass"})
    except Exception as error:
        evidence.update({"result": "fail", "error": str(error)})
        raise
    finally:
        # Stop a still-running prepare before restoring IME settings. A successful
        # recovery leaves the new IME process under normal framework management.
        restore_errors = []
        if prepare is not None and prepare.poll() is None:
            try:
                adb("shell", "am", "force-stop", IME)
                prepare.wait(timeout=30)
            except Exception as error:
                restore_errors.append(str(error))
                try:
                    prepare.terminate()
                    prepare.wait(timeout=10)
                except Exception as termination_error:
                    restore_errors.append(str(termination_error))
        for command in (["shell", "ime", "set", previous] if previous not in ("", "null") else
                        ["shell", "settings", "delete", "secure", "default_input_method"],
                        *([] if enabled else [["shell", "ime", "disable", COMPONENT]]),
                        ["shell", "am", "force-stop", HOST]):
            try:
                adb(*command)
            except Exception as error:
                restore_errors.append(str(error))
        try:
            restored_default = adb("shell", "settings", "get", "secure", "default_input_method")
            restored_enabled = set(adb("shell", "ime", "list", "-s").splitlines())
            if restored_default != previous or restored_enabled != previous_enabled:
                restore_errors.append("Default/enabled IME settings did not restore exactly")
        except Exception as error:
            restore_errors.append(str(error))
        for name, value in scales.items():
            try:
                if value == "null":
                    adb("shell", "settings", "delete", "global", name)
                else:
                    adb("shell", "settings", "put", "global", name, value)
                if adb("shell", "settings", "get", "global", name) != value:
                    restore_errors.append("Animation scale did not restore: " + name)
            except Exception as error:
                restore_errors.append(str(error))
        for package in (IME, HOST):
            try:
                adb("shell", "run-as", package, "rm", "-rf", relative)
            except Exception as error:
                restore_errors.append(str(error))
        evidence["restore_errors"] = restore_errors
        if restore_errors:
            evidence["result"] = "fail"
        (logs / "evidence.json").write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
        if restore_errors:
            raise RuntimeError(f"Fixture restoration failed; see {logs}")
    print(f"PASS: real IME process recovery ({evidence['recovery_mode']}); logs: {logs}")


if __name__ == "__main__":
    main()
