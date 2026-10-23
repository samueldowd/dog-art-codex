# Implemented configuration

The runtime reads only explicit app TOML plus the selected dotenv. Build settings remain on the build host. Native numeric/boolean/array types are required; blank placeholders stay unconfigured. Unknown/duplicate/wrong-file keys fail without echoing values. Secret precedence: selected file then explicit allowlisted process values; no interpolation or shell evaluation. No parent-directory dotenv search.

Current source settings select per_observation appearance entries and disable automatic generation/publication; the operational worker starts in shadow mode. User-selected best_effort_partial permits usable partial source references, with explicit limitations and observed facts required. Recognition thresholds/calibration apply only if calibrated_auto is explicitly selected later. `LOCAL_IMAGE_ENCODER` and `LOCAL_DOG_DETECTOR` point to explicit protected JSON manifests, not a network model name; the app never downloads weights. Verified target uses CPU. Source camera mapping and SMB target were discovered read-only. See original [catalog and semantics](03-CONFIGURATION.md), [current app file](../config/app.toml), [build file](../config/build.toml), [blank secret template](../config/.env.example), and [actual decisions](IMPLEMENTATION_DECISIONS.md).

## Runtime app keys

| Key | Type |
|---|---|
| `OLLAMA_MODEL_DIGEST` | string |
| `LOCAL_DOG_DETECTOR` | string |
| `VISIBILITY_CALIBRATION_PATH` | string |
| `APP_DATA_ROOT` | string |
| `FRIGATE_BASE_URL` | string |
| `FRIGATE_AUTH_MODE` | string |
| `FRIGATE_CA_BUNDLE` | string |
| `FRIGATE_CAMERA_DISPLAY_NAMES` | array[string] |
| `FRIGATE_CAMERA_IDS` | array[string] |
| `FRIGATE_EVENT_SOURCE` | string |
| `MQTT_HOST` | string |
| `MQTT_PORT` | integer |
| `MQTT_TLS` | boolean |
| `MQTT_TOPIC_PREFIX` | string |
| `MQTT_CLIENT_ID` | string |
| `EVENT_INITIAL_BACKFILL` | string |
| `EVENT_RECONCILE_OVERLAP_SECONDS` | integer |
| `EVENT_POLL_SECONDS` | integer |
| `MAX_CLIP_SECONDS` | integer |
| `MAX_CLIP_BYTES` | integer |
| `FRAMES_PER_DOG` | integer |
| `MODEL_INPUT_MAX_EDGE_PX` | integer |
| `MIN_DOG_CROP_EDGE_PX` | integer |
| `OLLAMA_HOST` | string |
| `OLLAMA_BASE_URL` | string |
| `OLLAMA_MODEL` | string |
| `LOCAL_IMAGE_ENCODER` | string |
| `LOCAL_ENCODER_DEVICE` | string |
| `IDENTITY_MODE` | string |
| `SOURCE_REFERENCE_POLICY` | string |
| `IDENTITY_MATCH_THRESHOLD` | number |
| `IDENTITY_NEW_THRESHOLD` | number |
| `IDENTITY_SCORE_MARGIN` | number |
| `IDENTITY_CALIBRATION_PATH` | string |
| `OPENAI_IMAGE_MODEL` | string |
| `OPENAI_IMAGE_SIZE` | string |
| `OPENAI_IMAGE_QUALITY` | string |
| `OPENAI_IMAGE_FORMAT` | string |
| `OPENAI_BACKGROUND` | string |
| `OPENAI_STYLE_REFERENCE` | string |
| `OPENAI_REFERENCE_MODE` | string |
| `ALLOW_CAMERA_CROP_UPLOAD` | boolean |
| `OPENAI_GENERATION_ENABLED` | boolean |
| `OPENAI_DAILY_BUDGET_USD` | number |
| `OPENAI_MAX_CALLS_PER_DAY` | integer |
| `OPENAI_MAX_AUTOMATIC_ATTEMPTS_PER_PORTRAIT` | integer |
| `OPENAI_HTTP_TIMEOUT_SECONDS` | integer |
| `WORKER_CONCURRENCY` | integer |
| `READ_RETRY_ATTEMPTS` | integer |
| `RETRY_BASE_SECONDS` | integer |
| `RETRY_MAX_SECONDS` | integer |
| `JOB_LEASE_SECONDS` | integer |
| `COLLAGE_WIDTH` | integer |
| `COLLAGE_HEIGHT` | integer |
| `COLLAGE_BACKGROUND` | string |
| `COLLAGE_LAYOUT` | string |
| `COLLAGE_MARGIN_PX` | integer |
| `COLLAGE_MIN_DOG_HEIGHT_PX` | integer |
| `DAY_TIMEZONE` | string |
| `RESET_LOCAL_TIME` | string |
| `PUBLISH_ENABLED` | boolean |
| `SMB_HOST` | string |
| `SMB_PORT` | integer |
| `SMB_SHARE` | string |
| `SMB_SUBDIRECTORY` | string |
| `SMB_DOMAIN` | string |
| `PUBLISH_FILENAME` | string |
| `ARCHIVE_COLLAGES` | boolean |
| `ARCHIVE_RETENTION_DAYS` | integer |
| `CLIP_RETENTION_DAYS` | integer |
| `MIN_FREE_DISK_MB` | integer |
| `LOG_LEVEL` | string |

## Build-only keys

| Key | Type |
|---|---|
| `PROJECT_NAME` | string |
| `DEV_REPO_DIR` | string |
| `GIT_REMOTE_URL` | string |
| `GIT_BASE_BRANCH` | string |
| `GIT_AUTHOR_NAME` | string |
| `GIT_AUTHOR_EMAIL` | string |
| `GIT_REMOTE_POLICY` | string |
| `SSH_IDENTITY_FILE` | string |
| `SSH_VERIFIED_HOST_KEY` | string |
| `PROXMOX_SSH_ALIAS` | string |
| `DEPLOY_TARGET_CTID` | integer |
| `APP_CODE_ROOT` | string |
| `APP_CONFIG_FILE` | string |
| `APP_SECRETS_FILE` | string |
| `SERVICE_USER` | string |
| `MODEL_DOWNLOAD_MAX_MB` | integer |
| `OPENAI_BUILD_BUDGET_USD` | number |
| `RESET_ACCEPTANCE_MODE` | string |
| `HA_MEDIA_DIRECTORY` | string |
| `HA_DASHBOARD_URL` | string |
| `HA_DASHBOARD_VIEW_PATH` | string |
| `HA_SLIDESHOW_CARD_LOCATION` | string |
| `HA_SLIDESHOW_REFRESH_SECONDS` | number |

## Secrets

Only FRIGATE_USERNAME, FRIGATE_PASSWORD, FRIGATE_TOKEN, MQTT_USERNAME, MQTT_PASSWORD, OLLAMA_API_KEY, OPENAI_API_KEY, SMB_USERNAME and SMB_PASSWORD are allowed. Keep local config/.env0600 and deployed /etc/dog-art/.env root:dog-art0640. Never commit/hash/export values. Wrong auth-mode mixtures fail. `none` is the explicitly verified internal Frigate API mode, not a fallback for missing credentials.

## Operational policy

CLI global `--config`, `--secrets-file`, and optional `--data-root` are explicit. Relative generated style artwork resolves from installed resources; runtime does not require checkout/build settings. Production image input is artwork_only; camera uploads are rejected until separately authorized/implemented. Archive-retention values do not trigger destructive cleanup. The free-space floor remains2048MiB per user; CT112 capacity was subsequently increased and verified. Source/model/config changes invalidate affected evidence and require revalidation.

The legacy `MIN_DOG_CROP_EDGE_PX` key is ignored; the selected value is0. No minimum crop dimensions reject observations. Retain small crops for local description/identity review; size does not prove visibility or identity. Maximum decoder byte/pixel bounds protect resources. `MIN_FREE_DISK_MB=2048` remains the independently authorized disk-space guard.

`IDENTITY_MODE="per_observation"` is the explicitly selected mode after the user deferred duplicate prevention. It needs the genuine encoder but no recognition thresholds/calibration. Each qualifying immutable observation becomes one separate appearance ID, not a claim about physical identity. `calibrated_auto` retains all real evaluation gates; `shadow` retains operator identity review. Human rejection/invalid quality/conflicts/wholly unknown facts remain blocked in every mode. SOURCE_REFERENCE_POLICY defaults to full_body; explicit best_effort_partial is supported only for per_observation, preserves original crop flags and records limitations. Generated output still needs full-body visual QA.
