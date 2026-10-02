#!/usr/bin/env bash
set -euo pipefail
# Run inside the emulator image, with Android volumes mounted, before its first boot.
task_avd="${ANDROID_AVD_HOME:-/data/avd}/WhatsApp_QA.avd"
task_data="$task_avd/userdata-qemu.img"
if [[ -e "$task_data" ]]; then
  echo 'Existing userdata preserved; no formatting performed.'
  exit 0
fi
if [[ ! -f "$task_avd/config.ini" ]]; then
  echo 'Prepare the system image and AVD first.' >&2; exit 1
fi
task_free=$(df -Pk "$task_avd" | awk 'NR==2 {print $4}')
if (( task_free < 1572864 )); then
  echo 'At least 1.5 GiB free is required before preparing userdata.' >&2; exit 1
fi
task_raw="$task_data.partial"
task_qcow="$task_data.partial.qcow2"
if [[ -e "$task_raw" || -e "$task_qcow" ]]; then
  echo 'Existing partial userdata requires operator review.' >&2; exit 1
fi
trap 'rm -f -- "$task_raw" "$task_qcow"' EXIT
task_sdk="${ANDROID_HOME:-/opt/android}"
# AOSP ships empty_data_disk: the emulator also initializes an empty ext4 data volume.
# Preformat a small sparse volume instead of its automatic 6 GiB first-boot minimum.
"$task_sdk/emulator/qemu-img" create -f raw "$task_raw" 1G
"$task_sdk/emulator/bin64/mkfs.ext4" -F -b 4096 -L data -m 0 "$task_raw"
"$task_sdk/emulator/qemu-img" convert -f raw -O qcow2 "$task_raw" "$task_qcow"
sed -i -E 's/^disk\.dataPartition\.size[[:space:]]*=.*/disk.dataPartition.size=1024M/' "$task_avd/config.ini"
mv -n -- "$task_qcow" "$task_data"
echo 'Persistent 1 GiB sparse userdata prepared without replacing existing data.'
