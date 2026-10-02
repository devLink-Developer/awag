#!/usr/bin/env bash
set -euo pipefail
export ANDROID_HOME="${ANDROID_HOME:-$HOME/.local/share/whatsapp-gateway/sdk}"
export ANDROID_AVD_HOME="${ANDROID_AVD_HOME:-$HOME/.local/share/whatsapp-gateway/avd}"
export PATH="$ANDROID_HOME/platform-tools:$ANDROID_HOME/emulator:$PATH"
task_emulator_port="${EMULATOR_PORT:-5554}"
if [[ ! "$task_emulator_port" =~ ^[0-9]{4}$ ]] || (( task_emulator_port < 5554 || task_emulator_port > 5682 || task_emulator_port % 2 != 0 )); then
  echo 'EMULATOR_PORT must be an even port between 5554 and 5682.' >&2
  exit 1
fi
task_emulator_serial="emulator-$task_emulator_port"
if [[ ! -r /dev/kvm || ! -w /dev/kvm ]]; then
  echo 'KVM is unavailable to this user. Activate virtualization and the kvm group.' >&2
  exit 1
fi
if [[ ! -f "$ANDROID_AVD_HOME/WhatsApp_QA.ini" ]]; then
  echo 'Run bash scripts/setup-android.sh first.' >&2
  exit 1
fi
if ! adb version | grep -q '37.0.1'; then
  echo 'ADB must match the containers (37.0.1). Run setup-android.sh.' >&2
  exit 1
fi
adb start-server
if adb -s "$task_emulator_serial" get-state >/dev/null 2>&1; then
  echo "$task_emulator_serial is already occupied; left unchanged." >&2
  exit 1
fi
task_emulator_args=(-avd WhatsApp_QA -port "$task_emulator_port" -accel on -no-snapshot -no-boot-anim -gpu swiftshader)
if [[ ${1:-} == --headless ]]; then task_emulator_args+=(-no-window); fi
emulator "${task_emulator_args[@]}" &
task_emulator_pid=$!
trap 'kill -TERM "$task_emulator_pid" 2>/dev/null || true; wait "$task_emulator_pid" 2>/dev/null || true' EXIT INT TERM
task_deadline=$((SECONDS + 240))
until [[ $(adb -s "$task_emulator_serial" shell getprop sys.boot_completed 2>/dev/null | tr -d '\r') == 1 ]]; do
  if ! kill -0 "$task_emulator_pid" 2>/dev/null || (( SECONDS >= task_deadline )); then
    echo 'Emulator did not complete boot within 240 seconds.' >&2
    exit 1
  fi
  # Bounded boot polling; UI actions use explicit Appium waits.
  sleep 1
done
echo 'WhatsApp_QA booted. Keep this terminal open; Ctrl+C shuts it down without wiping data.'
wait "$task_emulator_pid"
