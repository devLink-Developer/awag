#!/usr/bin/env bash
set -euo pipefail
# Optional disk optimization for Habitmundo's immutable AOSP SDK image. Stop the AVD first.
task_root=$(realpath -e "${1:-/opt/awag/android}")
task_source="$task_root/system-images/android-35/default"
task_archive="$task_root/aosp-35.sqfs"
task_backup="$task_source.unpacked"
task_check="$task_root/.pack-check"
if mountpoint -q "$task_source"; then
  [[ $(findmnt -n -o FSTYPE --target "$task_source") == squashfs ]] || exit 1
  echo 'Existing compressed system image preserved.'; exit 0
fi
[[ $(realpath -e "$task_source") == "$task_source" ]] || exit 1
[[ -f "$task_source/x86_64/.image-complete.json" ]] || exit 1
if [[ -e "$task_archive" || -e "$task_backup" ]]; then
  echo 'Existing archive or backup needs operator review.' >&2; exit 1
fi
if pgrep -f 'qemu-system.*-avd WhatsApp_QA' >/dev/null; then
  echo 'Stop WhatsApp_QA before packing its system image.' >&2; exit 1
fi
task_free=$(df -Pk "$task_root" | awk 'NR==2 {print $4}')
(( task_free >= 1572864 )) || { echo 'At least 1.5 GiB free required.' >&2; exit 1; }
mkdir -p "$task_check"
(cd "$task_source"; find . -type f -print0 | sort -z | xargs -0 sha256sum) > "$task_root/aosp-before.sha256"
nice -n 10 mksquashfs "$task_source" "$task_archive.partial" -comp zstd -Xcompression-level 5 -b 1048576 -processors 1 -mem 128M -noappend -no-progress
mount -t squashfs -o loop,ro "$task_archive.partial" "$task_check"
if ! (cd "$task_check"; sha256sum -c "$task_root/aosp-before.sha256"); then
  umount "$task_check"
  echo 'Packed image differs; original left unchanged.' >&2; exit 1
fi
umount "$task_check"
mv -- "$task_archive.partial" "$task_archive"
mv -- "$task_source" "$task_backup"
mkdir "$task_source"
mount -t squashfs -o loop,ro "$task_archive" "$task_source"
# Leave the original until the caller installs the persistent mount and confirms it.
echo "Compressed image mounted. Verified original retained at $task_backup."
