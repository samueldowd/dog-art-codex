# Development and reproducible delivery

Python>=3.11; target actually verified Debian12/Python3.11.2. Runtime versions and distribution hashes are pinned in requirements.lock; requirements-dev.lock records the tested authoring tools. setuptools80.9.0/wheel0.45.1 are the build backend pins. No global Python installs, Docker runtime, disabled host/TLS checks or build TOML at startup.

```sh
.venv/bin/python -m pytest -q
.venv/bin/python -m ruff check src tests scripts
.venv/bin/python -m ruff format --check src tests scripts
.venv/bin/python -m compileall -q src
SOURCE_DATE_EPOCH=1792700000 .venv/bin/python -m build --wheel --no-isolation
.venv/bin/python scripts/release.py --wheel dist/dog_art_pipeline-0.1.0-py3-none-any.whl --output dist/dog-art-pipeline-0.1.0.tar.gz --source-revision "$(git rev-parse HEAD)"
```

Pytest explicitly includes src for checkout tests and autouse-denies sockets; live/local-model markers do not silently run. Controlled acceptance uses separate explicit scripts/commands with real readiness/budget/path guards and private receipts. Fresh-wheel tests must run from outside the checkout with installed imports; checkout tests cannot establish that.

The release builder uses an explicit allowlist, sorted members, normalized owners/modes/timestamps and gzip mtime0. It includes the wheel, hashed runtime lock, non-secret app example, blank secret template, units, installer, provisioning and explicit installed-verification helpers, approved HA card/module examples and documentation/evidence. Real dotenv, build-only settings, private media/model weights/state/caches are excluded. Public pinned model JSON manifests and an explicit build-only preparation helper are included; the runtime never imports the helper. Inspect ZIP/tar member names and scan with seeded secret values without printing them. Build twice and compare actual hashes. Keep source/tested/artifact/final/deployed revisions distinct; record final receipt after the final source commit instead of a self-referential hash.

Tests cover config separation, path guards, SQLite backup/schema rejection, queue leases, event/pagination/media failures, real-image feature-space compatibility, shadow/abstention/corrections, paid uniqueness/crash outcomes, alpha checks, layout/capacity, midnight/DST/races, SMB fault/readback/isolation and runtime orchestration. The assertion must prove the behavior, not merely count a row while its job failed. Independent review findings and regression evidence are in IMPLEMENTATION_VALIDATION.md.

Local models are protected files with exact SHA256/preprocessing/source/license manifests. DINOv2-small converts native RGB crops to producer256-short-edge/224-center-crop normalization and CLS384 features. YOLOX nano official0.1.1rc0 export uses416RGB letterbox114 with unit/ImageNet normalization and producer grid decoding; per-frame anchors associate dog detections conservatively. These are generic image/detection models; no dog re-identification accuracy is claimed without labeled independent events, held-out visits/cameras/dates and hard negatives. Calibration cannot use neighboring frames or generated art as independent return ground truth.

The primary owns contracts/schema/config/locks/Git/integration/deployment/spending. Internal workers followed docs05 ownership; independent read-only review inspected actual integration. No other user-owned chats were created. Preserve user settings/artwork/unrelated changes. Remote policy is configured push_branch, but verify intended repository identity/visibility/access before pushing. Never force-push, merge default automatically, publish releases or change visibility as a routine shortcut.

## Real identity evidence workflow

Use protected CT112 shadow observations, never generated artwork or augmented neighboring frames as return labels. `review list` and `review show OBSERVATION_ID` expose pending IDs and private evidence locally. A human assigns physical dog/visit labels and marks genuinely recognizable versus expected-abstention examples. Keep this labels file private:

```json
{"schema":2,"samples":[{"observation_id":"REAL_OBSERVATION_ID","visit_id":"HUMAN_PHYSICAL_VISIT","dog_label":"HUMAN_DOG_LABEL","split":"reference","hard_negative_group":null,"recognizable":true,"expected_abstention":false,"abstention_reason":null}]}
```

Each label identifies an actual observation; the exporter reads its event/camera/date/quality, genuine vectors and successful local description from the catalog. It never infers dog/visit labels. Expected-abstention examples use `recognizable=false`, `expected_abstention=true`, and `abstention_reason="low_quality"` or `"ambiguous"`. Keep reference/calibration/evaluation events **and physical visits disjoint**. Both calibration and held-out splits need recognizable returns, novel/lookalike dogs, both selected cameras, cross-camera/day returns, and genuine low-quality plus ambiguous examples. Both splits must pass≥90% recognizable-return reuse, zero false merges and zero unsafe acceptances of expected-abstention examples. Counts/rates and limitations are recorded; minimal code coverage is not statistical certainty.

```sh
PYTHONPATH=src .venv/bin/python scripts/export_identity.py --catalog /PROTECTED/catalog.sqlite --labels /PROTECTED/human-labels.json --output /PROTECTED/features.json
PYTHONPATH=src .venv/bin/python scripts/evaluate_identity.py --manifest /PROTECTED/features.json --output /PROTECTED/evaluation-receipt.json --calibration-output /PROTECTED/approved-calibration.json --reviewed-by ACTUAL_REVIEWER --version ACTUAL_VERSION --cameras backyard_east driveway_ptz
```

The evaluation receipt is a report wrapper. Only a passing real evaluation writes the separately requested flat runtime calibration file. Missing fields/labels, synthetic evidence, failed coverage/quality or provisional thresholds cannot enable runtime matching. Set app threshold keys to the measured file's values and its exact path only after review. A separately approved visibility policy still needs independent positive/negative crops from both cameras; identity labels do not prove full-body visibility. No crop dimension floor is used.
