#!/usr/bin/env bash
set -euo pipefail
if [[ $(uname -s) != Linux ]]; then
  echo 'Run this script on Ubuntu Linux.' >&2
  exit 1
fi
sudo apt-get update
sudo apt-get install -y qemu-kvm cpu-checker openjdk-17-jdk-headless curl unzip python3 python3-venv ffmpeg
sudo usermod -aG kvm "$USER"
echo 'Log out and back in to activate the kvm group. Install Docker Engine and Compose following README.'
