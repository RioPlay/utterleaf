#!/usr/bin/env bash
set -euo pipefail

# Disposable emulator only: failure reports include window/input/power metadata.
if [[ "$(adb shell getprop ro.kernel.qemu | tr -d '\r')" != "1" ]]; then
  echo 'This CI diagnostic runner requires an Android emulator.' >&2
  exit 2
fi
capture_failure() {
  local test_status=$?
  if [[ "$test_status" != 0 ]]; then
    mkdir -p app/build/reports/ime-environment
    adb shell dumpsys power > app/build/reports/ime-environment/power.txt || true
    adb shell dumpsys window windows > app/build/reports/ime-environment/windows.txt || true
    adb shell dumpsys input > app/build/reports/ime-environment/input.txt || true
  fi
  exit "$test_status"
}
trap capture_failure EXIT

adb shell settings put secure show_ime_with_hard_keyboard 1
adb shell cmd overlay enable-exclusive --category com.android.internal.systemui.navbar.threebutton
adb shell input keyevent KEYCODE_WAKEUP
adb shell wm dismiss-keyguard
adb shell wm size
adb shell wm density
bash gradlew --no-daemon :app:connectedDebugAndroidTest
