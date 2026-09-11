"""Exercise debug-only dictionary publication pauses across abrupt emulator process death.

Install foundation debug and androidTest APKs first. Six synthetic cases cover formats
402/403 before exchange, after exchange, and after directory synchronization. SIGKILL
tests process death, not power loss or physical storage durability. Failed token data
is retained for investigation; no preferences, real dictionaries or models are removed.
"""
import argparse
import json
from pathlib import Path
import re
import subprocess
import time
import uuid

PACKAGE = "org.utterleaf.keyboard.experimental"
TEST = "org.utterleaf.keyboard.DictionaryStorageCrashProbeTest"
RUNNER = PACKAGE + ".test/androidx.test.runner.AndroidJUnitRunner"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--adb", required=True)
    parser.add_argument("--serial", default="emulator-5554")
    parser.add_argument("--logs", type=Path, default=Path("dictionary-storage-crash-logs"))
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
    uid = adb("shell", "run-as", PACKAGE, "id", "-u")
    if not uid.isdecimal():
        raise RuntimeError("Cannot verify debuggable experimental application UID")
    run_directory = args.logs.resolve() / uuid.uuid4().hex
    run_directory.mkdir(parents=True, exist_ok=False)
    evidence = {"emulator": args.serial, "uid": int(uid), "cases": [], "result": "fail"}

    def check_identity(state, token, stage, version):
        if not isinstance(state, dict) or state.get("token") != token:
            raise RuntimeError("Probe token mismatch")
        for key, value in (("uid", int(uid)), ("stage", stage), ("format", version)):
            if type(state.get(key)) is not int or state[key] != value:
                raise RuntimeError(f"Probe {key} mismatch")
        if type(state.get("pid")) is not int or state["pid"] <= 0:
            raise RuntimeError("Invalid probe PID")

    def check_live_pid(pid):
        if str(pid) not in adb("shell", "pidof", PACKAGE, check=False).split():
            raise RuntimeError("Probe PID is not the experimental application process")
        status = adb("shell", "run-as", PACKAGE, "cat", f"/proc/{pid}/status")
        match = re.search(r"^Uid:\s+(\d+)", status, re.MULTILINE)
        if match is None or match.group(1) != uid:
            raise RuntimeError("Probe process UID mismatch")

    try:
        for version in (402, 403):
            for stage in (4, 5, 6):
                token = uuid.uuid4().hex
                remote = "no_backup/storage-crash-probe/" + token
                case_directory = run_directory / f"{version}-{stage}-{token}"
                case_directory.mkdir()
                case = {"format": version, "stage": stage, "token": token, "result": "fail"}
                evidence["cases"].append(case)

                def command(method):
                    return base + ["shell", "am", "instrument", "-w", "-r",
                                   "-e", "class", TEST + "#" + method,
                                   "-e", "storageProbeToken", token,
                                   "-e", "storageProbeStage", str(stage),
                                   "-e", "storageProbeFormat", str(version), RUNNER]

                prepare = None
                try:
                    adb("shell", "am", "force-stop", PACKAGE)
                    with (case_directory / "prepare.log").open("w", encoding="utf-8") as output:
                        prepare = subprocess.Popen(command("prepareAndPause"), stdout=output,
                                                   stderr=subprocess.STDOUT, text=True)
                        deadline = time.monotonic() + 60
                        ready = None
                        while time.monotonic() < deadline:
                            raw = adb("shell", "run-as", PACKAGE, "cat", remote + "/ready.json", check=False)
                            try:
                                ready = json.loads(raw)
                            except (ValueError, TypeError):
                                ready = None
                            if ready is not None:
                                break
                            if prepare.poll() is not None:
                                raise RuntimeError("Prepare exited before native pause confirmation")
                            time.sleep(0.2)
                        check_identity(ready, token, stage, version)
                        check_live_pid(ready["pid"])
                        case["ready"] = ready
                        (case_directory / "ready.json").write_text(json.dumps(ready, indent=2), encoding="utf-8")
                        adb("shell", "run-as", PACKAGE, "kill", "-9", str(ready["pid"]))
                        prepare.wait(timeout=30)
                        if str(ready["pid"]) in adb("shell", "pidof", PACKAGE, check=False).split():
                            raise RuntimeError("Killed PID remains alive")

                    verification = subprocess.run(command("verifyAfterDeath"), capture_output=True,
                                                  text=True, timeout=90)
                    output = verification.stdout + verification.stderr
                    (case_directory / "verify.log").write_text(output, encoding="utf-8")
                    if verification.returncode or "OK (1 test)" not in output:
                        raise RuntimeError("Fresh-process dictionary verification failed")
                    verified = json.loads(adb("shell", "run-as", PACKAGE, "cat", remote + "/verified.json"))
                    check_identity(verified, token, stage, version)
                    if verified.get("result") != "pass" or verified["pid"] == ready["pid"]:
                        raise RuntimeError("Fresh-process verification evidence is invalid")
                    case["verified"] = verified
                    (case_directory / "verified.json").write_text(json.dumps(verified, indent=2), encoding="utf-8")
                    adb("shell", "am", "force-stop", PACKAGE)
                    # Constant private root plus generated hex token; never delete a computed parent.
                    adb("shell", "run-as", PACKAGE, "rm", "-rf", remote)
                    case["result"] = "pass"
                finally:
                    adb("shell", "am", "force-stop", PACKAGE, check=False)
                    if prepare is not None and prepare.poll() is None:
                        try:
                            prepare.wait(timeout=10)
                        except subprocess.TimeoutExpired:
                            prepare.terminate()
                            try:
                                prepare.wait(timeout=10)
                            except subprocess.TimeoutExpired:
                                prepare.kill()
                                prepare.wait(timeout=10)
        evidence["result"] = "pass"
    except Exception as error:
        evidence["error"] = str(error)
        raise
    finally:
        (run_directory / "evidence.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(f"PASS: six dictionary publication process-death cases; logs: {run_directory}")


if __name__ == "__main__":
    main()
