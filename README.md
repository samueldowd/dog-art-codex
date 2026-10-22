# Dog Art Pipeline

Native Python 3.11+ application for Debian container **CT112 (Proxmox ID 110)**. It ingests completed dog tracks from Frigate `backyard_east` and `driveway_ptz`, selects timestamped real dog views locally, describes them with pinned Ollama `qwen3-vl:8b`, and maintains a permanent SQLite identity/reference/artwork catalog. Accepted portraits use the official OpenAI Python SDK and generated style art only. Pillow composes today's accepted appearance entries into an opaque cream 1920×1080 collage; a guarded SMB publisher owns only `media/kitchen-tv/dog-art/dog-collage.png`.

**Implementation and live acceptance are in progress.** The user deferred returning-dog matching: selected per_observation mode permits repeated dogs as separate appearance entries; event replay remains idempotent. See [scope changes](docs/SCOPE_CHANGES.md). Paid generation and production publication remain disabled in the selected app configuration. CT112 installation prerequisites and isolated dependencies have been verified; the production application/service has not yet been promoted. Keep the distinction between implemented modules and observed live acceptance in [validation](docs/IMPLEMENTATION_VALIDATION.md) and the [requirement/evidence matrix](docs/CHECKLIST.md).

The authoritative build assignment is [CODEX_BUILD_BRIEF.md](CODEX_BUILD_BRIEF.md) and docs 01–12. The user's numeric-container clarification supersedes references to container ID112 in those original documents: hostname CT112 means **ID110**.

## Quick start from this repository

```sh
python3 -m venv .venv
.venv/bin/python -m pip install --require-hashes -r requirements.lock
.venv/bin/python -m pip install --no-deps .
# Preserve an existing populated config/.env; never overwrite it with the template.
.venv/bin/dog-art --config config/app.toml --secrets-file config/.env doctor --mode offline --redact
```

A missing dependency blocks only that stage. The runtime never loads `config/build.toml`, searches parent directories for secrets, evaluates dotenv as shell, or sends real camera frames to OpenAI. The nine secret keys belong solely in the explicit ignored `.env`. Native services use `/etc/dog-art/app.toml` and `/etc/dog-art/.env`.

## Behavior and safeguards

- Polling reconciles a durable start-time cursor with pagination, overlap and incomplete-track refresh; duplicate notifications/events/jobs are unique in SQLite. MQTT-shaped notifications are supported by an adapter; production currently uses API polling.
- Native recording frames use verified same-sensor sources and timestamps; Driveway PTZ retains wide recording by user choice and uses clean PTZ snapshots for review. Small crops have no size cutoff. A local hashed YOLOX nano detector generates fresh boxes around each Frigate track anchor during PTZ movement. Missing/ambiguous geometry, other dogs, clipping and occlusion defer to review. No manual fixed video coordinates.
- A hashed DINOv2 small ONNX encoder supplies real-image features on CPU. Descriptions, collars, handlers, backgrounds and generated artwork cannot alone establish identity. Calibration, alternative margins and explicit uncertainty guard automatic matching.
- Identity assignment/merge/split/undo preserve original observations and historical collage bytes. Visibility review is auditable. Review corrections rebuild current-day membership.
- Paid recipe uniqueness is canonical dog plus style version. Persisted reservations, call/dollar limits, a paid-process barrier, disabled SDK retries and indeterminate-outcome recovery prevent blind duplicate submissions. Returned PNGs need alpha checks plus visual anatomy/style/likeness approval.
- Daily generations use America/New_York observation dates, not processing time. Startup/timer catch-up, a cross-process publication barrier and last-moment day/revision checks reject yesterday's jobs. Histories/portraits/catalogs survive reset.
- SMB uploads use hidden non-image temporary names, encrypted/signed sessions, safe replacement, decoded/hash readback and a killable total-deadline worker. Existing slideshow files remain untouched. A failed/ambiguous replacement is reconciled by reading the desired remote hash.
- Layouts save seeds, placements and portrait hashes. They preserve aspect ratios/colors, complete silhouettes and margins; capacity failures never silently omit dogs. Archives are immutable. No automatic retained-artwork/catalog deletion is implemented.

## Guides and evidence

- [Installation](docs/INSTALLATION.md), [configuration](docs/CONFIGURATION.md), [operator guide](docs/OPERATOR_GUIDE.md)
- [Architecture](docs/ARCHITECTURE.md), [privacy and cost](docs/PRIVACY_AND_COST.md), [development](docs/DEVELOPMENT.md)
- [Troubleshooting](docs/TROUBLESHOOTING.md), [backup/recovery/rollback](docs/RECOVERY_AND_ROLLBACK.md)
- [Living implementation plan](docs/IMPLEMENTATION_PLAN.md), [decisions](docs/IMPLEMENTATION_DECISIONS.md), [blockers](docs/BLOCKERS.md), [validation](docs/IMPLEMENTATION_VALIDATION.md), [checklist](docs/CHECKLIST.md)

The final delivery receipt records tested source, artifact and installed revisions separately. A file copied to HA is not a verified dashboard refresh. Offline tests do not establish returning-dog accuracy or an unperformed live gate.
