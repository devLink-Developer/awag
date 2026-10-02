#!/usr/bin/env bash
set -euo pipefail
export ANDROID_HOME="${ANDROID_HOME:-$HOME/.local/share/whatsapp-gateway/sdk}"
export ANDROID_AVD_HOME="${ANDROID_AVD_HOME:-$HOME/.local/share/whatsapp-gateway/avd}"
export JAVA_HOME="${JAVA_HOME:-/usr/lib/jvm/java-17-openjdk-amd64}"
mkdir -p "$ANDROID_HOME/cmdline-tools" "$ANDROID_AVD_HOME"
task_tmp=$(mktemp -d)
trap 'rm -f "$task_tmp/tools.zip" "$task_tmp/adb.zip"; rmdir "$task_tmp" 2>/dev/null || true' EXIT
if [[ ! -x "$ANDROID_HOME/cmdline-tools/latest/bin/sdkmanager" ]]; then
  curl -fsSL https://dl.google.com/android/repository/commandlinetools-linux-16111833_latest.zip -o "$task_tmp/tools.zip"
  echo "e025545c62a8e64c7559119566a569fb1dec5f60  $task_tmp/tools.zip" | sha1sum -c -
  unzip -q "$task_tmp/tools.zip" -d "$ANDROID_HOME/cmdline-tools"
  mv "$ANDROID_HOME/cmdline-tools/cmdline-tools" "$ANDROID_HOME/cmdline-tools/latest"
fi
export PATH="$ANDROID_HOME/cmdline-tools/latest/bin:$ANDROID_HOME/platform-tools:$ANDROID_HOME/emulator:$PATH"
sdkmanager --sdk_root="$ANDROID_HOME" --licenses
sdkmanager --sdk_root="$ANDROID_HOME" 'emulator' 'platforms;android-35' 'build-tools;35.0.0' 'system-images;android-35;google_apis;x86_64'
# Match the container ADB version; a mismatch can kill the shared host ADB server.
if [[ ! -x "$ANDROID_HOME/platform-tools/adb" ]] || ! "$ANDROID_HOME/platform-tools/adb" version | grep -q '37.0.1'; then
  curl -fsSL https://dl.google.com/android/repository/platform-tools_r37.0.1-linux.zip -o "$task_tmp/adb.zip"
  echo "477254aa5f903c15cf51001717bdf347fb6b53e0  $task_tmp/adb.zip" | sha1sum -c -
  unzip -qo "$task_tmp/adb.zip" -d "$ANDROID_HOME"
fi
if [[ ! -f "$ANDROID_AVD_HOME/WhatsApp_QA.ini" ]]; then
  echo no | avdmanager create avd --name WhatsApp_QA --package 'system-images;android-35;google_apis;x86_64' --device pixel_6
fi
echo "SDK: $ANDROID_HOME"
echo "Persistent AVD: $ANDROID_AVD_HOME/WhatsApp_QA.avd"
