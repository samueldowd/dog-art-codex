#!/bin/sh
# Operator authenticates through normal sudo. No password/env sourcing or SSH keys.
# Usage: sudo sh install-release.sh VERIFIED_UNPACKED_DELIVERY SOURCE_REVISION
# Provision /etc/dog-art/.env separately through a protected CT112 input channel.
set -eu
umask 027
[ "$(id -u)" -eq 0 ] || { echo 'Interactive sudo required'; exit 1; }
[ "$(hostname)" = CT112 ] || { echo 'Wrong target hostname'; exit 1; }
[ "$#" -eq 2 ] || { echo 'Usage: install-release.sh DELIVERY_DIR SOURCE_REVISION'; exit 1; }
delivery=$(realpath "$1")
revision=$2
case "$revision" in *[!a-f0-9]*|'') echo 'Full source SHA required'; exit 1;; esac
[ "${#revision}" -eq 40 ] || { echo 'Full source SHA required'; exit 1; }
[ -f "$delivery/SHA256SUMS" ] || { echo 'Delivery manifest missing'; exit 1; }
(cd "$delivery" && sha256sum -c SHA256SUMS)
[ "$(cat "$delivery/SOURCE_REVISION")" = "$revision" ] || { echo 'Source revision differs from verified delivery'; exit 1; }
[ "$(df -Pm /var/lib/dog-art | awk 'NR==2 {print $4}')" -gt 2560 ] || { echo 'Insufficient deployment headroom; preserve configured 2048MiB floor'; exit 1; }
release=/opt/dog-art/releases/0.1.0-$revision
[ ! -e "$release" ] || { echo 'Release exists; inspect before reuse'; exit 1; }
for p in /opt/dog-art /etc/dog-art /var/lib/dog-art; do [ ! -L "$p" ] || { echo 'Unexpected symlink'; exit 1; }; done
getent passwd dog-art >/dev/null
install -d -o root -g dog-art -m 0750 "$release"
python3 -m venv "$release/venv"
"$release/venv/bin/python" -m pip install --no-cache-dir --require-hashes -r "$delivery/requirements.lock"
set -- "$delivery"/wheel/*.whl
[ "$#" -eq 1 ] || { echo 'Exactly one runtime wheel required'; exit 1; }
"$release/venv/bin/python" -m pip install --no-cache-dir --no-deps "$1"
"$release/venv/bin/python" -m compileall -q "$release/venv/lib"
chgrp -R dog-art "$release"
chmod -R g+rX,o-rwx "$release"
if [ ! -e /etc/dog-art/app.toml ]; then install -o root -g dog-art -m 0640 "$delivery/config/app.toml.example" /etc/dog-art/app.toml; fi
[ -f /etc/dog-art/.env ] || { echo 'Provision protected /etc/dog-art/.env before promotion; release installed but not activated'; exit 1; }
[ ! -L /etc/dog-art/.env ] || { echo 'Secrets symlink forbidden'; exit 1; }
chown root:dog-art /etc/dog-art/.env
chmod 0640 /etc/dog-art/.env
runuser -u dog-art -- "$release/venv/bin/dog-art" --config /etc/dog-art/app.toml --secrets-file /etc/dog-art/.env doctor --mode offline --redact
# Keep a database backup before promotion; live catalog is never copied without WAL support.
if [ -f /var/lib/dog-art/catalog.sqlite ]; then
 runuser -u dog-art -- "$release/venv/bin/dog-art" --config /etc/dog-art/app.toml --secrets-file /etc/dog-art/.env backup --output "/var/lib/dog-art/backups/pre-$revision.sqlite"
fi
# Stage and verify executable paths before modifying live unit files or pointers.
install -d -o root -g root -m 0700 "$release/systemd" "$release/previous-units"
for unit in dog-art.service dog-art-reset.service dog-art-reset.timer; do
 sed "s|/opt/dog-art/current|$release|g" "$delivery/deploy/systemd/$unit" > "$release/systemd/$unit"
done
systemd-analyze verify "$release/systemd/dog-art.service" "$release/systemd/dog-art-reset.service" "$release/systemd/dog-art-reset.timer"
previous=$(readlink /opt/dog-art/current || true)
worker_enabled=$(systemctl is-enabled dog-art.service 2>/dev/null || true)
timer_enabled=$(systemctl is-enabled dog-art-reset.timer 2>/dev/null || true)
worker_active=$(systemctl is-active dog-art.service 2>/dev/null || true)
timer_active=$(systemctl is-active dog-art-reset.timer 2>/dev/null || true)
for unit in dog-art.service dog-art-reset.service dog-art-reset.timer; do
 if [ -f "/etc/systemd/system/$unit" ]; then cp -p "/etc/systemd/system/$unit" "$release/previous-units/$unit"; fi
done
promoting=0
promotion_step=not-started
rollback() {
 result=$?
 trap - EXIT HUP INT TERM
 if [ "$promoting" -eq 1 ] && [ "$result" -ne 0 ]; then
  echo "Promotion failed during $promotion_step; restoring previous application pointer and units." >&2
  systemctl status dog-art.service dog-art-reset.timer --no-pager --lines=5 >&2 || true
  journalctl -u dog-art.service -u dog-art-reset.timer -n 30 --no-pager -o cat >&2 || true
  systemctl stop dog-art.service dog-art-reset.timer || true
  # Disable newly enabled links while their unit files still exist.
  [ "$worker_enabled" = enabled ] || systemctl disable dog-art.service >/dev/null 2>&1 || true
  [ "$timer_enabled" = enabled ] || systemctl disable dog-art-reset.timer >/dev/null 2>&1 || true
  if [ -n "$previous" ]; then
   ln -s "$previous" /opt/dog-art/.rollback
   mv -Tf /opt/dog-art/.rollback /opt/dog-art/current
  else
   rm -f /opt/dog-art/current
  fi
  for unit in dog-art.service dog-art-reset.service dog-art-reset.timer; do
   if [ -f "$release/previous-units/$unit" ]; then
    cp -p "$release/previous-units/$unit" "/etc/systemd/system/$unit"
   else
    rm -f "/etc/systemd/system/$unit"
   fi
  done
  systemctl daemon-reload || true
  if [ "$worker_active" = active ]; then systemctl start dog-art.service || echo 'Previous worker recovery failed; inspect service' >&2; fi
  if [ "$timer_active" = active ]; then systemctl start dog-art-reset.timer || echo 'Previous timer recovery failed; inspect timer' >&2; fi
 fi
 exit "$result"
}
trap rollback EXIT
trap 'exit 130' HUP INT TERM
[ ! -e /opt/dog-art/.next ] && [ ! -L /opt/dog-art/.next ]
[ ! -e /opt/dog-art/.rollback ] && [ ! -L /opt/dog-art/.rollback ]
promoting=1
for unit in dog-art.service dog-art-reset.timer dog-art-reset.service; do
 if [ -f "/etc/systemd/system/$unit" ]; then systemctl stop "$unit"; fi
done
for unit in dog-art.service dog-art-reset.service dog-art-reset.timer; do
 install -o root -g root -m 0644 "$release/systemd/$unit" "/etc/systemd/system/$unit"
done
ln -s "$release" /opt/dog-art/.next
mv -Tf /opt/dog-art/.next /opt/dog-art/current
printf '%s\n' "$revision" > "$release/SOURCE_REVISION"
promotion_step=reload-and-enable
systemctl daemon-reload
systemctl enable dog-art.service dog-art-reset.timer
# Restart upgrades, and wait for successful exec via Type=exec.
promotion_step=restart
systemctl restart dog-art.service dog-art-reset.timer
promotion_step=stable-running-release
attempt=0
stable=0
last_pid=
while [ "$attempt" -lt 20 ]; do
 attempt=$((attempt + 1))
 pid=$(systemctl show dog-art.service --property MainPID --value)
 case "$pid" in ''|*[!0-9]*) pid=0;; esac
 if [ "$pid" -gt 0 ] && systemctl is-active --quiet dog-art.service &&
    [ -r "/proc/$pid/cmdline" ] &&
    tr '\000' '\n' < "/proc/$pid/cmdline" | grep -Fx "$release/venv/bin/dog-art" >/dev/null; then
  if [ "$pid" = "$last_pid" ]; then stable=$((stable + 1)); else stable=1; fi
  last_pid=$pid
  [ "$stable" -lt 2 ] || break
 else
  stable=0
  last_pid=
 fi
 sleep 1
done
[ "$stable" -ge 2 ] || { echo 'Running worker did not stabilize on expected release within 20 checks' >&2; exit 1; }
promotion_step=timer-active
systemctl is-active --quiet dog-art-reset.timer
promotion_step=installed-import
runuser -u dog-art -- "$release/venv/bin/python" -c 'import dog_art; print("Installed import:", dog_art.__file__)'
promotion_step=timer-schedule
systemctl list-timers dog-art-reset.timer --no-pager
promoting=0
printf '%s\n' 'Installed shadow service. Reviewed live promotion and actual dashboard acceptance remain separate.'
