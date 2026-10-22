# Native deployment, publication and operations

## Install in CT112

The future builder must produce an installation procedure for the actual Debian/Python versions discovered. Use a dedicated native virtual environment and versioned release directory under the configured application root. Do not install application dependencies into system Python or use `--break-system-packages`.

Proposed layout:
~~~text
/opt/dog-art/releases/<version>/       installed code, locked dependencies, style assets
/opt/dog-art/current                  pointer to the active verified release
/etc/dog-art/app.toml                 non-secret runtime configuration
/etc/dog-art/.env                     single protected secrets file
/var/lib/dog-art/catalog.sqlite       local database
/var/lib/dog-art/references/           private real-dog galleries
/var/lib/dog-art/portraits/<dog_id>/   accepted portrait versions
/var/lib/dog-art/archive/<date>/      historical collage PNGs and recipe metadata
/var/lib/dog-art/staging/              local output staging
/var/lib/dog-art/private-fixtures/     ignored, protected test inputs if supplied
/var/lib/dog-art/backups/              application backups
~~~

These paths are proposed defaults. Record actual ownership, space, permissions and existing content before changes.

Keep build-only `config/build.toml` on the build host. Provision the app TOML and secrets separately to the destination paths recorded there; pass absolute config paths to both native worker/reset services. The app must start with no build file installed. Do not include the real `.env` in code artifacts/checksum manifests or transfer it through Proxmox-host staging. If fallback access is the only route, provision secrets through a protected container-directed input channel without exposing values in arguments or logs. Preserve any existing secrets file unless a deliberate update is authorized.

With the Proxmox fallback, execute application commands inside `pct exec 112`. For artifact transfer, use an approved container transfer method such as `pct push` from a narrowly scoped temporary host staging directory, after verifying command/version/permissions. Check hashes before and after transfer and clean only the exact staging files created by this task. This is not permission to install the application on the host or change Proxmox configuration. Never transfer SSH private keys or hard-code secrets in a transport command.

## Services and timer

Produce version-appropriate units for:
- `dog-art.service`: queue worker/ingest and application-owned publication.
- `dog-art-reset.service`: short-lived idempotent current-date reconciliation.
- `dog-art-reset.timer`: explicit America/New_York midnight scheduling plus supported persistent catch-up.

Use the same release/config/service user. Validate units with installed tooling and inspect the next scheduled fire time. A systemd version may affect timezone/calendar options; verify exact syntax locally rather than assuming this document supplies a universal unit.

Reasonable hardening includes a dedicated user, restricted writable directories, no unnecessary listening ports, protected home/system paths, limited resources and restart backoff. Preserve needed network access, model files and FFmpeg execution. Test the actual hardened service; a foreground root run does not prove it works under systemd.

`network-online.target` is not proof that Frigate, Ollama or SMB is available. Keep dependency-specific health/retry states inside the application.

## Promotion sequence

1. Record and back up any existing application state/config/managed output. Preserve unrelated files.
2. Install the exact tested release and verify its artifact hash and import location.
3. Run redacted offline/live doctor checks.
4. Run shadow mode against real events, with paid generation and publication disabled.
5. Resolve calibration/readiness and evidence gaps.
6. Perform bounded paid portrait smoke with the configured budget.
7. Validate a non-production SMB staging operation, including replacement and readback.
8. Enable the owned production publication and inspect actual dashboard refresh.
9. Enable and verify the native service/timer; test application restart and controlled reset recovery.
10. Record the deployed release/config/model fingerprints and final status.

No phase may enable real-image upload simply because a generated style reference works. Respect the configured and authorized cloud input policy.

## Safe SMB publication

Verify mapping explicitly:

~~~text
Home Assistant requested directory:  /media/kitchen-tv
Expected share (verify):             \\HA_SERVER\media
Expected relative subdirectory:      kitchen-tv
Owned final image (default):         dog-collage.png
~~~

Never infer the HA server from the Ollama address. Use supplied authenticated Samba access and modern supported protocol/security settings. Do not enable SMB1 or anonymous sharing as a workaround.

The publisher:
- Validates local output dimensions, decode and hash before upload.
- Uses a uniquely owned non-image temporary filename on the same server filesystem.
- Writes/closes/verifies the staged bytes.
- Rechecks current day/generation/revision under serialized publication ownership.
- Safely replaces the final owned file using server/client-supported behavior.
- Reads back the final image and verifies expected bytes/hash/dimensions.
- Records success only after verification and retains the archive on CT112.

If replacement is denied by an open handle or unsupported server semantics, retain the last valid image and defer. Do not delete the old image first or broaden file permissions without a scoped reason and authority.

## Existing slideshow and cache behavior

The runtime publishes one image into the already used folder; it does not create a new card or redesign the dashboard.

Measure:
- How the existing card enumerates media and filters temporary filenames.
- Whether a stable filename updates through its ordinary cycle.
- How browser/HA/media caching affects refresh.
- Whether the configured dashboard URL/view corresponds to the actual Kitchen TV display.

If the card requires a configuration change, prepare the smallest specific change and evidence first, then request that scope under the critical-decision policy. Do not silently edit storage files or replace the dashboard.

## Daily archive and midnight recovery

Archive each published collage revision with date, revision, PNG hash, member IDs, portrait hashes and saved layout. Keep previous archives and permanent portraits on CT112. A daily reset changes the owned HA output and today's active membership/generation only.

On startup and before publication:
- Reconcile the actual current local date.
- Prioritize the current generation over old outbox entries.
- Never publish previous-day content as if it were today's.
- Rebuild from the persistent current-day ledger after crashes or restart.

During an HA/SMB outage, local midnight reconciliation still occurs. The remote display may retain its last image until connectivity returns; record this observable limitation and publication lag. On recovery, publish the current valid desired state, not every queued historical revision.

## Operational failure policy

| Failure | Required behavior |
|---|---|
| Frigate unavailable/media expired | Retain source cursor/job state, bounded retry, mark missing evidence; no invented description. |
| Ollama/model unavailable | Pause dependent description/matching jobs; keep other health/queue work alive. |
| Unsupported/missing vision model | Report the actual capability gap; no silent cloud captioning/model replacement. |
| Ambiguous identity | Queue review/better evidence; no forced merge or duplicate confident claim. |
| OpenAI limit/auth/outcome unknown | Respect caps; distinguish rejected, not-submitted and indeterminate outcomes; no blind paid replay. |
| Invalid portrait/collage | Do not publish; preserve last valid image and archive the failure context without secrets. |
| SMB offline/denied/replace conflict | Defer current desired revision; coalesce stale revisions and verify before retry. |
| Low disk | Pause new downloads/generation before exhaustion; keep last good output and surface the required retention/capacity decision. |
| Schema/model version mismatch | Refuse incompatible comparison/migration; preserve backups and explain recovery. |

Do not silently delete retained archives or the identity catalog to regain disk space. Raw input/download retention is separately configured and must not touch the user's original attachments.

## Diagnostics and operator guide

Document service/timer status, current day/revision, last successful publish and hash, last reset, queued/blocked jobs, identity-review count, encoder/model versions, remaining call budget and meaningful sanitized errors.

Use structured logs with IDs/codes and private details kept out of public evidence. Avoid verbose API/SMB packet dumps and captured authorization URLs. Provide examples for safely inspecting status, retrying a resolved dependency, reviewing an identity and restoring service.

## Backup and rollback

Before a schema migration or release promotion, take a supported SQLite backup plus referenced asset/config inventory. Store secrets only in protected backups.

Rollback procedure must:
1. Stop only the application worker/timer as needed.
2. Identify the prior release and compatible state backup.
3. Restore or migrate according to explicit schema compatibility; never open a newer schema with older code blindly.
4. Verify service readiness and current-day ledger.
5. Re-publish the correct current-day image, preserving archives and unrelated HA images.
6. Record the rollback source/config/state revisions and test evidence.

A Proxmox snapshot, host reboot, container privilege change or broader HA/Frigate change is a separate critical action, not an automatic rollback shortcut.

