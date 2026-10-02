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
task_accel_mode="${EMULATOR_ACCEL_MODE:-on}"
case "$task_accel_mode" in on|off) ;; *) echo 'EMULATOR_ACCEL_MODE must be on or off.' >&2; exit 1 ;; esac
task_boot_timeout="${EMULATOR_BOOT_TIMEOUT_SECONDS:-240}"
if [[ ! "$task_boot_timeout" =~ ^[1-9][0-9]{1,3}$ ]] || (( task_boot_timeout < 30 || task_boot_timeout > 7200 )); then
  echo 'EMULATOR_BOOT_TIMEOUT_SECONDS must be between 30 and 7200.' >&2
  exit 1
fi
task_memory="${EMULATOR_MEMORY_MB:-}"
task_cores="${EMULATOR_CORES:-}"
if [[ -n "$task_memory" ]] && { [[ ! "$task_memory" =~ ^[1-9][0-9]{2,4}$ ]] || (( task_memory < 512 || task_memory > 16384 )); }; then
  echo 'EMULATOR_MEMORY_MB must be between 512 and 16384.' >&2; exit 1
fi
if [[ -n "$task_cores" ]] && { [[ ! "$task_cores" =~ ^[1-9][0-9]?$ ]] || (( task_cores > 32 )); }; then
  echo 'EMULATOR_CORES must be between 1 and 32.' >&2; exit 1
fi
case "${1:-}" in ''|--headless) ;; *) echo 'Usage: start-emulator.sh [--headless]' >&2; exit 1 ;; esac
if [[ "$task_accel_mode" == on && ( ! -r /dev/kvm || ! -w /dev/kvm ) ]]; then
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
task_emulator_args=(-avd WhatsApp_QA -port "$task_emulator_port" -accel "$task_accel_mode" -no-snapshot -no-boot-anim -gpu swiftshader -no-audio -no-metrics -camera-back none -camera-front none)
if [[ "$task_accel_mode" == off ]]; then
  task_emulator_args+=(-lowram -append-userspace-opt androidboot.config.low_ram=true -prop ro.hw_timeout_multiplier=10 -feature -Vulkan -vsync-rate 15 -show-kernel)
fi
if [[ -n "$task_memory" ]]; then task_emulator_args+=(-memory "$task_memory"); fi
if [[ -n "$task_cores" ]]; then task_emulator_args+=(-cores "$task_cores"); fi
if [[ ${1:-} == --headless ]]; then task_emulator_args+=(-no-window); fi
if [[ "$task_accel_mode" == off ]]; then task_emulator_args+=(-qemu -tb-size 64); fi
emulator "${task_emulator_args[@]}" &
task_emulator_pid=$!
trap 'kill -TERM "$task_emulator_pid" 2>/dev/null || true; wait "$task_emulator_pid" 2>/dev/null || true' EXIT INT TERM
task_deadline=$((SECONDS + task_boot_timeout))
task_guest_timeouts_configured=false
until [[ $(timeout 15s adb -s "$task_emulator_serial" shell getprop sys.boot_completed 2>/dev/null | tr -d '\r') == 1 ]]; do
  if ! kill -0 "$task_emulator_pid" 2>/dev/null; then
    echo 'Emulator process exited before completing boot.' >&2
    exit 1
  fi
  if (( SECONDS >= task_deadline )); then
    echo "Emulator did not complete boot within $task_boot_timeout seconds." >&2
    exit 1
  fi
  if [[ "$task_accel_mode" == off && "$task_guest_timeouts_configured" == false ]] &&
     [[ $(timeout 15s adb -s "$task_emulator_serial" get-state 2>/dev/null) == device ]]; then
    task_guest_multiplier=$(timeout 15s adb -s "$task_emulator_serial" shell getprop ro.hw_timeout_multiplier | tr -d '\r')
    if [[ "$task_guest_multiplier" != 10 ]]; then
      # Some SDK images reject this host boot property. AOSP permits a bounded
      # bootstrap with temporary root; restore normal ADB before UI automation.
      timeout 30s adb -s "$task_emulator_serial" root
      sleep 2
      timeout 30s adb -s "$task_emulator_serial" wait-for-device
      timeout 30s adb -s "$task_emulator_serial" shell setprop ro.hw_timeout_multiplier 10
      timeout 30s adb -s "$task_emulator_serial" shell setprop ctl.restart zygote
      timeout 30s adb -s "$task_emulator_serial" unroot
      sleep 2
      timeout 30s adb -s "$task_emulator_serial" wait-for-device
      if [[ $(timeout 15s adb -s "$task_emulator_serial" shell getprop ro.hw_timeout_multiplier | tr -d '\r') != 10 ]]; then
        echo 'Could not configure bounded Android hardware timeouts.' >&2; exit 1
      fi
    fi
    task_guest_timeouts_configured=true
  fi
  # Bounded boot polling; UI actions use explicit Appium waits.
  sleep 2
done
echo 'WhatsApp_QA booted. Keep this terminal open; Ctrl+C shuts it down without wiping data.'
wait "$task_emulator_pid"
