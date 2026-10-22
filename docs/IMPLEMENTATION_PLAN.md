# Living implementation plan

Activated 2026-10-22 by explicit user build assignment. Read brief, docs 01–12, settings/templates, extraction reference and prompt assets before edits.

## Current state
- Base revision: 5dce4f50bf8c41f0df1285553c581ae1ac50659a; initial branch master. Existing user changes: config/app.toml, config/build.toml; preserved and type-normalized only.
- A in progress: direct ct112 SSH verified; Debian 12/Python 3.11.2/systemd 252; 1 CPU/1 GiB RAM/2.5 GiB free. No ffmpeg found; sudo requires password. User clarified CT112 hostname means container ID 110.
- B in progress: primary establishing typed contracts/settings, SQLite/queue/budget, clock/path/redaction and offline tests before worker implementation.
- C–J NOT STARTED. Mandatory live gates remain required.

## Sequence and ownership
Wave 0: primary A then B; preflight_review read-only spec/assets review. Wave 1 starts only after foundation checkpoint: ingest (frigate/, vision/), local AI (description/, identity/), composition (daily/, collage/), publication queued for available slot. Primary retains portraits, integration and shared files. Wave 3 independent read-only integrated review. Wave 4 primary-only deployment/acceptance.

## Commands / observations
- SSH strict known-host verification succeeded; `hostname`, OS, id, resource/time probes observed above. Unprivileged sudo probes failed with password required on container and Proxmox. No sudo policy changes.
- Secrets presence inspected without values: MQTT/OpenAI/SMB populated; Frigate/Ollama empty. Original file 0644 tightened to 0600; ignored/untracked verified.
- Settings had quoted numeric/boolean fields; preserving values with native TOML types. ID 110 preserved per explicit user correction.

## Next actions
Finish preflight/config capability discovery, foundation tests and Git checkpoint; publish shared interfaces, dispatch Wave 1. Obtain narrow interactive administrative authentication when installation is concrete. Do not enable automatic identity decisions without independent evaluation. No paid requests or production publication performed.

Foundation validation: `.venv/bin/python -m pytest -q tests/test_foundation.py`: 6 passed on Python 3.12.8; Ruff repairs then formatting applied. Offline doctor parsed selected app/secrets; only presence metadata emitted. Dependency hash resolution still running; target runtime validation remains separate.
