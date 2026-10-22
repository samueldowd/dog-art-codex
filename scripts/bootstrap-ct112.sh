#!/bin/sh
# Run by the operator inside the verified CT112 (numeric Proxmox ID110).
# Creates only Dog Art service identity/directories and installs native video/venv prerequisites.
set -eu
[ "$(id -u)" -eq 0 ] || { echo 'Run through interactive sudo'; exit 1; }
[ "$(hostname)" = CT112 ] || { echo 'Wrong hostname'; exit 1; }
. /etc/os-release
[ "$ID" = debian ] && [ "$VERSION_ID" = 12 ] || { echo 'Unsupported inspected target'; exit 1; }
for path in /opt/dog-art /etc/dog-art /var/lib/dog-art; do
 [ ! -L "$path" ] || { echo 'Unexpected symlink'; exit 1; }
 if [ -d "$path" ] && [ -n "$(find "$path" -mindepth 1 -maxdepth 1 -print -quit)" ]; then
  echo 'Existing Dog Art path requires primary inspection'; exit 1
 fi
done
apt-get update
apt-get --no-remove --no-install-recommends install -y python3-venv ffmpeg
if ! getent passwd dog-art >/dev/null; then
 useradd --system --home-dir /var/lib/dog-art --no-create-home --shell /usr/sbin/nologin dog-art
fi
install -d -o root -g dog-art -m 0750 /opt/dog-art /opt/dog-art/releases /etc/dog-art
install -d -o dog-art -g dog-art -m 0700 /var/lib/dog-art
printf '%s\n' 'Dog Art prerequisites prepared. No worker enabled and no slideshow files changed.'
