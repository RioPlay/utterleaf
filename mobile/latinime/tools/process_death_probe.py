"""External, synthetic-only abrupt-death/cold-launch check on a disposable emulator.

Install debug and androidTest APKs first. No app-data clearing or production hooks.
Example: python tools/process_death_probe.py --adb SDK/platform-tools/adb.exe
The ordinary Gradle suite must exclude ProcessDeathProbeTest; this coordinator
explicitly selects it. SIGKILL is expected to abort the prepare instrumentation.
This is not Android saved-task restoration, real IME recovery, or physical QA.
"""

import argparse
from pathlib import Path
import re
import subprocess
import time
import uuid

PACKAGE = "org.utterleaf.keyboard.experimental"
TEST = "org.utterleaf.keyboard.ProcessDeathProbeTest"
RUNNER = PACKAGE + ".test/androidx.test.runner.AndroidJUnitRunner"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--adb", required=True)
    parser.add_argument("--serial", default="emulator-5554")
    parser.add_argument("--logs", type=Path, default=Path("process-death-logs"))
    args = parser.parse_args()
    if not re.fullmatch(r"emulator-[0-9]+", args.serial):
        parser.error("This synthetic destructive-process test requires an emulator serial")
    base = [args.adb, "-s", args.serial]

    def adb(*command, check=True):
        result = subprocess.run(base + list(command), capture_output=True,
                                text=True, timeout=30)
        if check and result.returncode:
            raise RuntimeError(result.stderr or result.stdout)
        return result.stdout.strip()

    if adb("shell", "getprop", "ro.kernel.qemu") != "1":
        raise RuntimeError("Device did not identify itself as an emulator")
    uid = adb("shell", "run-as", PACKAGE, "id", "-u")
    if not uid.isdecimal():
        raise RuntimeError("Could not verify debuggable experimental application UID")
    token = uuid.uuid4().hex
    directory = "no_backup/process-death-" + token
    logs = args.logs.resolve() / token
    logs.mkdir(parents=True, exist_ok=False)

    def instrument(phase):
        return base + ["shell", "am", "instrument", "-w", "-r",
                       "-e", "class", TEST, "-e", "deathPhase", phase,
                       "-e", "deathToken", token, RUNNER]

    def completed_phase(phase):
        result = subprocess.run(instrument(phase), capture_output=True,
                                text=True, timeout=90)
        output = result.stdout + result.stderr
        (logs / (phase + ".log")).write_text(output, encoding="utf-8")
        if result.returncode or "OK (1 test)" not in output:
            raise RuntimeError(f"{phase} failed; see {logs}")

    prepare = None
    try:
        # Runtime state is intentionally replaced; installed assets/data are retained.
        adb("shell", "am", "force-stop", PACKAGE)
        with (logs / "prepare.log").open("w", encoding="utf-8") as output:
            prepare = subprocess.Popen(instrument("prepare"), stdout=output,
                                       stderr=subprocess.STDOUT, text=True)
            deadline = time.monotonic() + 60
            old_pid = ""
            while time.monotonic() < deadline:
                old_pid = adb("shell", "run-as", PACKAGE, "cat", directory + "/ready", check=False)
                if old_pid.isdecimal():
                    break
                if prepare.poll() is not None:
                    raise RuntimeError(f"Prepare exited before readiness; see {logs}")
                time.sleep(0.2)
            if not old_pid.isdecimal():
                raise RuntimeError("Prepare did not reach readiness")
            if old_pid not in adb("shell", "pidof", PACKAGE).split():
                raise RuntimeError("Ready PID is not the experimental package process")
            status = adb("shell", "run-as", PACKAGE, "cat", f"/proc/{old_pid}/status")
            process_uid = re.search(r"^Uid:\s+(\d+)", status, re.MULTILINE)
            if process_uid is None or process_uid.group(1) != uid:
                raise RuntimeError("Prepared process UID mismatch")
            adb("shell", "run-as", PACKAGE, "kill", "-9", old_pid)
            prepare.wait(timeout=30)
            if old_pid in adb("shell", "pidof", PACKAGE, check=False).split():
                raise RuntimeError("Killed PID remains alive")
        completed_phase("verify")
        new_pid = adb("shell", "run-as", PACKAGE, "cat", directory + "/verified")
        if not new_pid.isdecimal() or new_pid == old_pid:
            raise RuntimeError("Verification did not run in a different process")
        (logs / "pid-evidence.txt").write_text(
            f"emulator={args.serial}\nuid={uid}\nkilled_pid={old_pid}\nverified_pid={new_pid}\n",
            encoding="utf-8")
    finally:
        adb("shell", "am", "force-stop", PACKAGE)
        if prepare is not None:
            prepare.wait(timeout=30)
        # Explicit restore phase verifies exact original preference map and removes
        # only this invocation's files. A failed restore leaves its backup for repair.
        completed_phase("restore")
    print(f"PASS: SIGKILL/cold-launch preference/practice probe; logs: {logs}")


if __name__ == "__main__":
    main()
