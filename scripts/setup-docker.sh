#!/usr/bin/env bash
set -euo pipefail
if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
  echo 'Docker and Compose already available; left unchanged.'
  exit 0
fi
source /etc/os-release
[[ ${ID:-} == ubuntu ]] || { echo 'This installer requires Ubuntu.' >&2; exit 1; }
sudo apt-get update
sudo apt-get install -y ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
task_arch=$(dpkg --print-architecture)
task_codename=${UBUNTU_CODENAME:-$VERSION_CODENAME}
sudo tee /etc/apt/sources.list.d/docker.sources >/dev/null <<EOF
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: $task_codename
Components: stable
Architectures: $task_arch
Signed-By: /etc/apt/keyrings/docker.asc
EOF
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo usermod -aG docker "$USER"
echo 'Log out and back in before using Docker without sudo.'
