# Separate build, app and secret configuration

The configuration has three responsibilities. The real secrets file is local and ignored; only its blank template is tracked and packaged.

| File | Purpose | Git / release policy |
|---|---|---|
| [config/build.toml](../config/build.toml) | 26 build, access, deployment and acceptance settings. | Track non-secret values; keep out of the installed runtime application. |
| [config/app.toml](../config/app.toml) | 68 settings used by the running app. | Track non-secret defaults and deliberate deployment settings; validate before enabling live actions. |
| `config/.env`, created from [config/.env.example](../config/.env.example) | Nine service login/key/token/password fields shared by build checks and runtime. | Ignore in Git; exclude from release archives, checksums and routine evidence. |

[.gitignore](../.gitignore) ignores `.env` and its backup/override variants while allowing `.env.example`. The example always remains blank. A blank local `config/.env` is supplied in the authoring workspace if no file existed; the ZIP contains only `.env.example`. Never overwrite an existing populated file when copying the template.

This is still a documentation delivery. No application config loader, deployment, secret provisioning or service has been implemented.

## File ownership and values

**Build file:** project/repository identity and policy, direct SSH/Proxmox access metadata, install root/service user, destination paths for the app config and secrets, model-download guard, paid build-test budget, reset acceptance mode and dashboard verification details. SSH key material stays in the authorized key/agent system; only a key path belongs in this file.

**App file:** Frigate/cameras/MQTT, local models/identity, portrait generation, ongoing spending/call caps, queue/retries, collage/reset behavior, SMB publication, storage and logs. The runtime needs this file and the selected secrets file, with no dependency on Git settings, SSH aliases, the build budget or the build file.

**Secrets file:** only `FRIGATE_USERNAME`, `FRIGATE_PASSWORD`, `FRIGATE_TOKEN`, `MQTT_USERNAME`, `MQTT_PASSWORD`, `OLLAMA_API_KEY`, `OPENAI_API_KEY`, `SMB_USERNAME` and `SMB_PASSWORD`. Do not embed credentials in URLs, TOML or command-line arguments.

The builder may read app settings during preflight/integration work. Do not duplicate app values in the build file just because a build check uses them.

## Provenance, types and blank placeholders

- **known:** stated in the user conversation. A requested name/path still needs a verified service mapping.
- **default:** a proposed reversible engineering setting, not a discovered fact.
- **unknown:** unconfigured until legitimately supplied or discovered.
- **sensitive:** never supplied in a tracked file or this document.

TOML uses native strings, numbers, booleans and arrays. Known camera display names are an array; unconfigured camera IDs are an empty array. Blank unknown scalar values are `""`, including numeric/boolean values whose real type is not yet known. This is a deliberate placeholder: when filling one in, replace it with the type listed below, such as an integer port or a numeric budget. The loader must report an unconfigured field rather than silently coercing a blank to zero/false.

Parse with `tomllib` on Python 3.11+ or a pinned compatible TOML parser if the verified target Python needs one. Do not upgrade system Python just for this file format. Parse secrets as dotenv data, without shell evaluation or variable interpolation; a dictionary parser such as `dotenv_values(..., interpolate=False)` is suitable. Do not execute/source either file or interpolate model/user strings as commands.

## Loading and precedence contract for the future builder

1. The build workflow reads the explicitly selected build TOML, then app TOML as needed for integration readiness, and only the secrets needed by each check.
2. The normal app reads the selected app TOML and selected `.env` only. It must run from an installed release without the build TOML present.
3. Non-secret app precedence is documented defaults < selected app TOML < explicit allowlisted CLI overrides, if implemented. Do not load ordinary app/build settings from `.env`.
4. Secret precedence is selected `.env` < explicitly supplied process values for the nine allowlisted secret keys. An explicit empty secret remains missing; it does not enable anonymous access. Do not copy all parsed secrets into global process environment or child processes.
5. Reject duplicate keys, unknown/misplaced keys, credentials in either TOML file, build keys in app TOML and ordinary settings in `.env`. Preserve auth-mode exclusivity rather than mixing Frigate password and token modes.
6. Do not search parent directories for a convenient `.env`. Use the selected path. Never log secret values, headers, credential-bearing URLs or unredacted validation input.
7. Runtime commands/services must support explicit config paths. For example, the future CLI should accept `dog-art --config /etc/dog-art/app.toml --secrets-file /etc/dog-art/.env status --redact`. These are proposed interfaces, not installed commands.

The build file's `APP_CONFIG_FILE` and `APP_SECRETS_FILE` are **deployment destination paths**, not runtime settings the app must read from a build file. The installer writes those absolute paths into the native worker/reset command lines. For local development, select `config/app.toml` and `config/.env` explicitly from the documented repository working directory.

The build runner enforces `OPENAI_BUILD_BUDGET_USD` in addition to the app's ongoing daily dollar/call caps for controlled paid tests. Pass this bounded policy explicitly through the build/test interface to the shared request ledger; do not make the production worker load the build file. A missing build cap blocks paid build tests, while a completed deployment remains independent of that build-only setting.

## Stage-specific readiness

1. **Offline development:** a verified checkout, build prerequisites and parseable templates; missing external credentials do not block it.
2. **Frigate ingest:** app URL/auth/camera IDs, selected event route and corresponding secrets.
3. **Local description:** app Ollama URL and exact image-capable model tag. The host is known; scheme/port/tag are not. Do not substitute a model to hide this gap.
4. **Automatic identity matching:** app encoder/preprocessing/calibration and thresholds backed by independent-event evaluation.
5. **Paid generation:** selected API model, API key, enabled app flag and finite ongoing budget/call caps. Controlled build tests additionally need the build-only cap.
6. **Publication:** app SMB mapping/owned filename/enabled flag, secrets, staging and readback.
7. **Live acceptance:** build dashboard/view/card/reset-test settings and real UI access, in addition to the runtime checks.

Record unambiguous discovery source/time without disclosing credentials. If essential input is absent, request secure provisioning and continue independent work.

## Complete key catalog

Values below mirror the appropriate file. `""`, `[]` and empty dotenv values are intentionally unconfigured. There is one owner per key; credentials never appear in the TOML catalog sections.

### Build and deployment — config/build.toml

| Group | Key | Value | Type | Status | Meaning / validation |
|---|---|---|---|---|---|
| Build and access | `PROJECT_NAME` | `"dog-art-pipeline"` | string | default | Proposed application/repository label; not an existing verified repo. |
| Build and access | `DEV_REPO_DIR` | `""` | string | unknown | Dedicated future implementation checkout; discover before edits. |
| Build and access | `GIT_REMOTE_URL` | `""` | string | unknown | Verified target remote URL without embedded credentials; never the FPA reference repo. |
| Build and access | `GIT_BASE_BRANCH` | `""` | string | unknown | Discover from the actual target; a new unborn repository is valid. |
| Build and access | `GIT_AUTHOR_NAME` | `""` | string | unknown | Use existing verified project identity; do not invent. |
| Build and access | `GIT_AUTHOR_EMAIL` | `""` | string | unknown | Use existing verified project identity; do not invent. |
| Build and access | `GIT_REMOTE_POLICY` | `"local_only"` | string | default | local_only or explicitly configured push_branch; merging/releases are separate. |
| Build and access | `CT112_SSH_ALIAS` | `""` | string | unknown | Direct SSH connection/alias on the executing host. |
| Build and access | `CT112_HOST` | `""` | string | unknown | Container address; not the Proxmox host. |
| Build and access | `CT112_SSH_USER` | `""` | string | unknown | Authorized login identity. |
| Build and access | `SSH_IDENTITY_FILE` | `""` | string | unknown | Path to an existing permitted key; never its content. |
| Build and access | `SSH_VERIFIED_HOST_KEY` | `""` | string | unknown | Trusted fingerprint/host-key verification record. |
| Build and access | `PROXMOX_SSH_ALIAS` | `"proxmox-host"` | string | known | User-specified fallback connection name; actual access still needs verification. |
| Build and access | `DEPLOY_TARGET_CTID` | `112` | integer | known | User-specified Proxmox container ID. |
| Runtime paths | `APP_CODE_ROOT` | `"/opt/dog-art"` | string | default | Proposed application release root; inspect existing ownership first. |
| Runtime paths | `APP_CONFIG_FILE` | `"/etc/dog-art/app.toml"` | string | default | Deployed non-secret runtime TOML path; startup receives it explicitly. |
| Runtime paths | `APP_SECRETS_FILE` | `"/etc/dog-art/.env"` | string | default | Single deployed secrets file; provision separately and never commit. |
| Runtime paths | `SERVICE_USER` | `"dog-art"` | string | default | Dedicated unprivileged application user. |
| Video and local AI | `MODEL_DOWNLOAD_MAX_MB` | `500` | integer | default | Per-model download guard; larger/new infrastructure changes need an explicit decision. |
| OpenAI | `OPENAI_BUILD_BUDGET_USD` | `""` | number | unknown | Explicit numeric cap for paid build/evaluation calls; blank blocks paid calls. |
| Collage and reset | `RESET_ACCEPTANCE_MODE` | `"controlled_on_target"` | string | default | Controlled owned-image blank/restore test plus timer/clock tests; natural observation may supplement. |
| Publication and HA | `HA_MEDIA_DIRECTORY` | `"/media/kitchen-tv"` | string | known | Normalized requested HA path; mapping must be verified, not assumed. |
| Publication and HA | `HA_DASHBOARD_URL` | `""` | string | unknown | Actual existing Kitchen TV dashboard URL for visual acceptance. |
| Publication and HA | `HA_DASHBOARD_VIEW_PATH` | `""` | string | unknown | Stable view path if applicable. |
| Publication and HA | `HA_SLIDESHOW_CARD_LOCATION` | `""` | string | unknown | Existing card identification/location; discover read-only. |
| Publication and HA | `HA_SLIDESHOW_REFRESH_SECONDS` | `""` | number | unknown | Observed rescan/cache behavior; validate before claiming live updates. |

### Runtime application — config/app.toml

| Group | Key | Value | Type | Status | Meaning / validation |
|---|---|---|---|---|---|
| Runtime paths | `APP_DATA_ROOT` | `"/var/lib/dog-art"` | string | default | Local persistent data; SQLite must not live on SMB. |
| Frigate and MQTT | `FRIGATE_BASE_URL` | `""` | string | unknown | Actual authorized Frigate URL and port; verify configured auth/API routes/version. |
| Frigate and MQTT | `FRIGATE_AUTH_MODE` | `""` | string | unknown | Explicit verified auth mode; blank is not anonymous. |
| Frigate and MQTT | `FRIGATE_CA_BUNDLE` | `""` | string | unknown | Optional trusted custom CA path; blank means normal system trust, not verify=false. |
| Frigate and MQTT | `FRIGATE_CAMERA_DISPLAY_NAMES` | `["Backyard East","Driveway PTZ"]` | array[string] | known | Requested camera display names; map uniquely to actual Frigate IDs. |
| Frigate and MQTT | `FRIGATE_CAMERA_IDS` | `[]` | array[string] | unknown | Required verified list of exactly the two selected machine camera IDs. |
| Frigate and MQTT | `FRIGATE_EVENT_SOURCE` | `"auto"` | string | default | Prefer verified MQTT; permit authenticated API polling if equivalent and documented. |
| Frigate and MQTT | `MQTT_HOST` | `""` | string | unknown | Broker address, required for MQTT mode. |
| Frigate and MQTT | `MQTT_PORT` | `""` | integer | unknown | Actual port; do not assume plaintext or TLS. |
| Frigate and MQTT | `MQTT_TLS` | `""` | boolean | unknown | Required explicit true/false when MQTT mode is selected. |
| Frigate and MQTT | `MQTT_TOPIC_PREFIX` | `"frigate"` | string | default | Verify against the actual installation. |
| Frigate and MQTT | `MQTT_CLIENT_ID` | `"dog-art-ct112"` | string | default | Must not collide with an existing active MQTT client. |
| Frigate and MQTT | `EVENT_INITIAL_BACKFILL` | `"today"` | string | default | First startup only: today's available events; remain subject to budget and identity gates. |
| Frigate and MQTT | `EVENT_RECONCILE_OVERLAP_SECONDS` | `120` | integer | default | Overlap around the durable cursor; deduplicate. Do not truncate a long outage to this overlap. |
| Frigate and MQTT | `EVENT_POLL_SECONDS` | `15` | integer | default | Polling/reconciliation interval when applicable; bound request volume. |
| Video and local AI | `MAX_CLIP_SECONDS` | `60` | integer | default | Bound selected media windows; preserve full event metadata and choose useful windows for long events. |
| Video and local AI | `MAX_CLIP_BYTES` | `104857600` | integer | default | Bound each media download; reject/defer oversized media explicitly. |
| Video and local AI | `FRAMES_PER_DOG` | `6` | integer | default | Candidate selected views; benchmark against model context/resources. |
| Video and local AI | `MODEL_INPUT_MAX_EDGE_PX` | `1280` | integer | default | Crop from native resolution first, then resize model inputs; never downscale a distant dog away. |
| Video and local AI | `MIN_DOG_CROP_EDGE_PX` | `""` | integer | unknown | Calibrate from actual quality/evaluation; do not invent a passing threshold. |
| Video and local AI | `OLLAMA_HOST` | `"192.168.7.134"` | string | known | User-supplied local server address. |
| Video and local AI | `OLLAMA_BASE_URL` | `""` | string | unknown | Scheme/port unverified. A common candidate is http://192.168.7.134:11434; verify before filling. |
| Video and local AI | `OLLAMA_MODEL` | `""` | string | unknown | Exact requested Gemma model tag placeholder, intentionally blank. |
| Video and local AI | `LOCAL_IMAGE_ENCODER` | `""` | string | unknown | Reuse a suitable local image encoder if present; otherwise choose within resource/download/license bounds. |
| Video and local AI | `LOCAL_ENCODER_DEVICE` | `"cpu"` | string | default | Safe initial device choice; use verified available acceleration through a documented decision. |
| Identity | `IDENTITY_MODE` | `"shadow"` | string | default | No uncalibrated automatic merges. Switch to calibrated_auto only after acceptance evidence. |
| Identity | `IDENTITY_MATCH_THRESHOLD` | `""` | number | unknown | Model-specific threshold from labeled independent-event calibration. |
| Identity | `IDENTITY_NEW_THRESHOLD` | `""` | number | unknown | Threshold for confidently new identity; distinct from uncertain. |
| Identity | `IDENTITY_SCORE_MARGIN` | `""` | number | unknown | Required separation from the next-best candidate; calibrate. |
| Identity | `IDENTITY_CALIBRATION_PATH` | `""` | string | unknown | Versioned calibration metadata and private held-out dataset reference. |
| OpenAI | `OPENAI_IMAGE_MODEL` | `""` | string | unknown | Verify a currently available image model with transparent PNG support and pricing. |
| OpenAI | `OPENAI_IMAGE_SIZE` | `"1536x1024"` | string | default | Proposed portrait canvas; verify compatibility with the configured model. |
| OpenAI | `OPENAI_IMAGE_QUALITY` | `"high"` | string | default | Proposed final-art setting; test within the configured budget. |
| OpenAI | `OPENAI_IMAGE_FORMAT` | `"png"` | string | known | Required transparent portrait file type. |
| OpenAI | `OPENAI_BACKGROUND` | `"transparent"` | string | known | Required actual alpha background. |
| OpenAI | `OPENAI_STYLE_REFERENCE` | `"assets/style/dog-watercolor-transparent.png"` | string | default | Bundled generated artwork, not a real surveillance crop. |
| OpenAI | `OPENAI_REFERENCE_MODE` | `"artwork_only"` | string | default | Description plus generated style art. camera_crops requires explicit opt-in. |
| OpenAI | `ALLOW_CAMERA_CROP_UPLOAD` | `false` | boolean | default | No private dog-camera stills leave local processing unless explicitly enabled and authorized. |
| OpenAI | `OPENAI_GENERATION_ENABLED` | `false` | boolean | default | Enable only after credential, model, budget, policy and smoke checks. |
| OpenAI | `OPENAI_DAILY_BUDGET_USD` | `""` | number | unknown | Explicit numeric ongoing image-generation cap; blank blocks live generation. |
| OpenAI | `OPENAI_MAX_CALLS_PER_DAY` | `""` | integer | unknown | Explicit numeric hard call count; blank blocks live generation. |
| OpenAI | `OPENAI_MAX_AUTOMATIC_ATTEMPTS_PER_PORTRAIT` | `1` | integer | default | No blind replay after an uncertain paid request outcome. |
| OpenAI | `OPENAI_HTTP_TIMEOUT_SECONDS` | `300` | integer | default | Finite timeout; handle unknown outcome without duplicate automatic billing. |
| Work and reliability | `WORKER_CONCURRENCY` | `1` | integer | default | Conservative CT112 baseline; still test concurrent event submissions and publication races. |
| Work and reliability | `READ_RETRY_ATTEMPTS` | `3` | integer | default | Read/download retries only; not a blanket paid-generation retry policy. |
| Work and reliability | `RETRY_BASE_SECONDS` | `5` | integer | default | Initial bounded exponential retry backoff with jitter. |
| Work and reliability | `RETRY_MAX_SECONDS` | `300` | integer | default | Maximum retry delay; retain deferred jobs and health state. |
| Work and reliability | `JOB_LEASE_SECONDS` | `600` | integer | default | Reclaim expired interrupted work; paid requests need outcome reconciliation. |
| Collage and reset | `COLLAGE_WIDTH` | `1920` | integer | known | Full HD landscape output. |
| Collage and reset | `COLLAGE_HEIGHT` | `1080` | integer | known | Full HD landscape output. |
| Collage and reset | `COLLAGE_BACKGROUND` | `"#F3EBDD"` | string | default | Warm cream proposal matching the requested appearance. |
| Collage and reset | `COLLAGE_LAYOUT` | `"scattered"` | string | known | Requested randomly placed dogs; implement seeded layout and collision checks. |
| Collage and reset | `COLLAGE_MARGIN_PX` | `40` | integer | default | Output safe margin, adjustable with visual evidence. |
| Collage and reset | `COLLAGE_MIN_DOG_HEIGHT_PX` | `120` | integer | default | Readability guard; do not silently omit dogs if all cannot fit. |
| Collage and reset | `DAY_TIMEZONE` | `"America/New_York"` | string | known | User's local timezone; store raw timestamps in UTC. |
| Collage and reset | `RESET_LOCAL_TIME` | `"00:00:00"` | string | default | End-of-day interpretation: local midnight. |
| Publication and HA | `PUBLISH_ENABLED` | `false` | boolean | default | Enable only after target, ownership, Samba and staging checks. |
| Publication and HA | `SMB_HOST` | `""` | string | unknown | Actual HA Samba server name/address; not inferred from the Ollama host. |
| Publication and HA | `SMB_PORT` | `445` | integer | default | Standard SMB candidate; verify accessibility. |
| Publication and HA | `SMB_SHARE` | `"media"` | string | default | Expected HA media share; confirm it maps to the requested directory. |
| Publication and HA | `SMB_SUBDIRECTORY` | `"kitchen-tv"` | string | known | Requested subdirectory, after share mapping is verified. |
| Publication and HA | `SMB_DOMAIN` | `""` | string | unknown | Optional domain; blank is allowed if the server does not require it. |
| Publication and HA | `PUBLISH_FILENAME` | `"dog-collage.png"` | string | default | Only this final image and documented private staging names are app-owned. |
| Storage and logs | `ARCHIVE_COLLAGES` | `true` | boolean | known | Retain historical collages on CT112. |
| Storage and logs | `ARCHIVE_RETENTION_DAYS` | `""` | integer | unknown | Blank means no automatic archive deletion; user requested retention. |
| Storage and logs | `CLIP_RETENTION_DAYS` | `""` | integer | unknown | Raw clip retention policy needs an explicit configured decision; never quietly delete user input. |
| Storage and logs | `MIN_FREE_DISK_MB` | `2048` | integer | default | Pause new expensive/download work before exhaustion; preserve last good output. |
| Storage and logs | `LOG_LEVEL` | `"INFO"` | string | default | Structured redacted logs; no payload/SMB packet/API debug dumps by default. |

### Secrets template — config/.env.example

| Group | Key | Value | Type | Status | Meaning / validation |
|---|---|---|---|---|---|
| Frigate and MQTT | `FRIGATE_USERNAME` | (blank) | string | sensitive | Supply securely if required by configured auth. |
| Frigate and MQTT | `FRIGATE_PASSWORD` | (blank) | string | sensitive | Supply securely; never log, commit or put in a URL. |
| Frigate and MQTT | `FRIGATE_TOKEN` | (blank) | string | sensitive | Alternative credential if supported; handle expiry correctly. |
| Frigate and MQTT | `MQTT_USERNAME` | (blank) | string | sensitive | Broker account if required. |
| Frigate and MQTT | `MQTT_PASSWORD` | (blank) | string | sensitive | Broker secret; blank is not permission to connect anonymously. |
| Video and local AI | `OLLAMA_API_KEY` | (blank) | string | sensitive | Only if the local proxy requires it; do not invent an auth requirement. |
| OpenAI | `OPENAI_API_KEY` | (blank) | string | sensitive | Use a securely supplied API key or supported credential mechanism; never paste into the build doc. |
| Publication and HA | `SMB_USERNAME` | (blank) | string | sensitive | Authorized Samba account; minimize available write scope. |
| Publication and HA | `SMB_PASSWORD` | (blank) | string | sensitive | Supply in a protected file/secret mechanism where supported. |

## Paths, deployment and Git

- Keep the real local `config/.env` out of Git from the beginning. Verify `git check-ignore config/.env` and confirm the blank example and TOML files remain trackable. Ignore rules do not untrack an already committed file: if one was committed, remove it from tracking without deleting the local file and assess exposed credentials before publication.
- Deploy the app file to `/etc/dog-art/app.toml` and the same logical secrets file to `/etc/dog-art/.env` through a separate protected provisioning step. Do not ship populated secrets in source artifacts, put them in remote command arguments or stage them on the Proxmox host.
- Protect the deployed `.env` using restrictive ownership/mode, such as root-owned with only the dedicated service group allowed to read, or service-owned mode 0600. Both worker and reset service must read only the necessary configuration.
- Build/app TOML files contain no passwords, keys or tokens. Non-secret network addresses are still private deployment metadata; the default Git policy remains local-only.
- Resolve relative style/model assets from a documented installed resource root, independent of Git/build settings and the service's incidental working directory.
- Canonicalize owned paths and reject traversal, unexpected symlinks and broad roots before writes. Keep SQLite/private media/models/archives local on CT112.
- The former combined `build.env.example` is retired. `APP_CREDENTIALS_DIR` and `SMB_CREDENTIALS_FILE` are removed in favor of the single `.env`. Camera arrays are native TOML keys `FRIGATE_CAMERA_DISPLAY_NAMES` and `FRIGATE_CAMERA_IDS`; the old `_JSON` names are removed.
- Unknown budgets remain blank. Zero is an explicit disable value. Reserve conservatively and enforce call/attempt caps; estimated dollars are not guaranteed billing amounts.
- Camera-crop upload remains disabled by default and requires actual authorization, not just a flag change.

## Configuration evidence

The future `doctor` command reports selected config paths, key presence/readiness, camera mappings, model versions and publication mapping without secret values. Fingerprint only non-secret settings plus secret presence/source metadata; do not persist secret values or hashes of low-entropy passwords.

The implementation must test three-file separation, wrong-file keys, blank/type validation, secret redaction, real `.env` Git/archive exclusion and runtime startup with the build file absent. A missing required credential should block only its dependent feature, not unrelated offline work.

