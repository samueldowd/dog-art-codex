# Native installation

Verified target: direct SSH alias `ct112`, hostname CT112, numeric Proxmox **110**, Debian12, Python3.11.2, systemd252, oneCPU/1GiB RAM. Keep host-key checks and password-protected sudo. If direct SSH fails, verify `proxmox-host`, `pct status 110`, ownership/running status, then execute application work only through `pct exec 110`. Never start a stopped container or change its networking/isolation without separate authorization.

The operator already ran `scripts/bootstrap-ct112.sh` using normal sudo. It verified the hostname, installed FFmpeg/Python venv prerequisites and created dedicated `dog-art` paths. It did not start a service. Root config/code directories are0750 root:dog-art; state0700 dog-art. No Docker runtime is required.

Build a verified delivery using [development](DEVELOPMENT.md). Transfer its archive, verify SHA256, unpack into a protected application staging directory and check every included manifest entry. Provision `/etc/dog-art/.env` separately via a protected container-directed channel; never include it in the artifact or stage it on Proxmox. Preserve an existing secrets file. Use root:dog-art0640 and explicit service paths. Install hashed local model files/manifests under `/var/lib/dog-art/models`; the runtime never downloads weights.

`scripts/install-release.sh DELIVERY_DIR FULL_SOURCE_SHA` is the scoped root installer. Read the exact script first, invoke through normal interactive sudo, and inspect its output. It verifies hostname/artifact checksums/deployment disk headroom, creates a versioned native venv, installs hash-pinned dependencies plus the wheel, preserves existing app config, requires separately provisioned secrets, backs up an existing SQLite catalog, validates systemd units against the actual release executable, then atomically switches `/opt/dog-art/current`. It enables only `dog-art.service` in **shadow** and the midnight reconciliation timer. App generation/publication flags remain disabled.

The source defaults do not represent a completed production promotion. Confirm:

```sh
systemctl status dog-art.service dog-art-reset.timer --no-pager
systemctl list-timers dog-art-reset.timer --no-pager
systemd-analyze calendar '*-*-* 00:00:00 America/New_York'
sudo -u dog-art /opt/dog-art/current/venv/bin/dog-art --config /etc/dog-art/app.toml --secrets-file /etc/dog-art/.env doctor --mode live --redact
```

The installed service must be tested as its dedicated user under its hardening, not merely as root. Live mode needs usable observed appearance facts under the selected source policy and bounded paid/API/SMB/dashboard gates. The selected per_observation mode permits duplicate physical dogs without recognition calibration; calibrated_auto additionally requires the real identity evaluation. Change the service's mode through an app-scoped systemd override only after those pass; keep source, config, models and deployed revision in the receipt. Do not edit HA/Frigate broadly to hide a missing gate.

Storage expansion is verified:40206MiB total/32894MiB available; runtime disk floor2048MiB remains unchanged. The user's later removal of a size floor applies to dog crop dimensions, not disk space.

Provisioning is separate from the release: `sudo sh scripts/provision-ct112.sh /home/chatgpt/dog-art-build` verifies exact local model hashes, preserves existing runtime secrets and creates protected model files. The real dotenv travels directly over SSH to protected CT112 staging and never enters the release or Proxmox staging. Read both provisioning and installation scripts before authenticating.

The installer verifies staged units before live mutation, explicitly restarts the worker on upgrade, checks its running release command/import, and restores previous pointer/units/service if promotion fails. Isolated command-boundary tests cover these cases; actual installed verification is still required.

## Explicit model preparation

The delivery includes public source/hash/preprocessing manifests in `deploy/models/` and `scripts/prepare-models.py`; weights are excluded. On CT112, unpack the verified delivery as the staging user, then run this preparation explicitly as `chatgpt`, before normal sudo provisioning:

```sh
python3 scripts/prepare-models.py --directory /home/chatgpt/dog-art-build/models --manifests deploy/models --max-mb 500
```

This downloads only the two pinned public weights (92,192,341 bytes total), verifies exact length/SHA256 over verified HTTPS, and enforces a 180-second total deadline per missing model plus the unchanged2048MiB free-space floor. Existing identical files are reused without a request; differing existing files/symlinks are preserved and rejected. Interrupted or invalid downloads remove only their own temporary file. These explicit model downloads do not occur at app startup. Prepare the separate protected `runtime.env` through the authorized secret channel; the helper never handles credentials or camera images. Then use the provisioning/installation steps above.

The initial440db67 installation passed dedicated-user offline doctor but failed promotion and rolled back. No current pointer or service remains active. Preserve its release/stage for diagnosis; do not rerun its old activation script. Authenticated journal now shows start followed by clean rollback stop, with no app failure message. The exact failed command is unproven. Recovery uses Type=exec, bounded stable-PID/argv checks and explicit failure-stage diagnostics; transient and permanent mismatch/absentPID/inactive regressions pass.
