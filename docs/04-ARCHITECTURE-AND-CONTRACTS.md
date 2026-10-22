# Architecture and shared implementation contracts

This is a proposed modular design, not existing code. The primary agent may make documented internal adjustments while preserving all requirements.

## Runtime shape

One native Python application on CT112 owns a local SQLite database, durable jobs, permanent real-image reference galleries, portrait files, daily membership and archives. Ollama remains on the supplied host. OpenAI is used for portrait generation. Home Assistant serves the published image through its existing slideshow.

~~~mermaid
flowchart LR
  A[Frigate MQTT or verified API polling] --> B[Durable event queue]
  B --> C[Clip and snapshot selection]
  C --> D[Native-resolution dog crops]
  D --> E[Ollama structured description]
  D --> F[Local visual encoder]
  E --> G[Identity decision]
  F --> G
  G --> H[Existing portrait cache]
  G --> I[New portrait job through OpenAI]
  H --> J[Today's unique identities]
  I --> J
  J --> K[Pillow cream collage]
  K --> L[Archive and latest-only publication outbox]
  L --> M[Samba owned image]
  M --> N[Existing HA slideshow]
~~~

No separate web server is required for this scope. Local asset folders satisfy CT112 storage; Home Assistant's existing media/slideshow path supplies display hosting.

## Module responsibilities and ownership seams

| Proposed module | Responsibility / contract |
|---|---|
| `settings.py` | Parse/validate separate build TOML, app TOML and allowlisted secrets; runtime loads only app TOML plus the selected `.env`. Reject wrong-file keys. Pure validation must not contact paid APIs or publish. |
| `contracts.py` | Typed records for events, observations, dog descriptions, match decisions, portrait recipes, collage revisions and publication receipts. |
| `storage/` | SQLite migrations, transactions, uniqueness, backup/restore and artifact references. Database remains on a local filesystem. |
| `jobs/` | Durable queue, leases, retries, dependency waits, cancellation and at-least-once delivery handling. |
| `frigate/` | Version-aware authenticated event/media access, MQTT adapter, optional equivalent polling and reconciliation. |
| `vision/` | FFmpeg decoding/sampling, per-dog tracking/crops, quality assessment and preprocessing. |
| `description/` | Ollama transport, strict JSON schema, per-frame facts/aggregation and uncertainty. |
| `identity/` | Local image features, galleries, calibrated match/new/uncertain logic and correction audit. |
| `portraits/` | Versioned watercolor prompt, API adapter, budget reservations, request outcome ledger and alpha/visual checks. |
| `daily/` | Local-date membership, idempotent rollover, generation ownership and startup catch-up. |
| `collage/` | Seeded scattered layout and Pillow composition with dimensions/margins/collision checks. |
| `publishing/` | SMB path policy, temporary upload, safe replacement, remote readback and latest-generation rules. |
| `diagnostics/` | Redacted health/status, evidence and error summaries, without private raw payload dumps. |
| `cli.py` | Human/operator entrypoints, review/correction and safe dry runs. No hidden implicit live side effects. |

Candidate dependencies: standard-library `sqlite3`/`zoneinfo`/`pathlib`, FFmpeg, Pillow, a typed validation library, a maintained MQTT client, the official OpenAI Python SDK, an HTTP client/Ollama client and `smbprotocol`'s high-level `smbclient` interface. Choose a local encoder implementation only after inventory and benchmarking. Pin chosen versions and record licenses. Reusing a system-installed library without a version receipt is not reproducibility.

## Shared records

Define these before delegated modules implement against them:

- **EventRef:** source event ID, actual camera ID, label, UTC start/end/observation times, media capability flags and private source reference.
- **DogObservation:** event ID + local track/dog index, real-crop hashes/paths, source timestamps, box coordinates with their source resolution, quality/visibility, and camera.
- **DogDescription:** coat base/colors/markings, proportions/approximate size, fur length/texture, muzzle, ears, tail, accessories, pose, visible/occluded areas and uncertainty. Breed is optional/unknown unless justified; it is not a required classifier result.
- **IdentityDecision:** known/new/uncertain, candidate IDs/scores, model/preprocessing/calibration versions, rationale facts and abstention reason.
- **PortraitRecipe:** dog ID, stable style version, prompt/recipe hash, generated-art reference hashes, allowed input policy, API model/settings, budget reservation and job/request ID.
- **CollageRevision:** day, generation, monotonically increasing revision, ordered accepted dog IDs, portrait hashes, layout seed/placements, dimensions/background, output path/hash and creation time.
- **PublishReceipt:** local generation/revision/hash, verified remote server/share/relative path, upload/replace/readback times and success/failure state.

Use timezone-aware UTC timestamps internally and `zoneinfo.ZoneInfo("America/New_York")` for day boundaries. Do not compare naive datetimes or infer event time from a file's modification timestamp.

## Persistent data

At minimum persist logical entities for:
- Events and observations, with durable source cursor and replay/dedup state.
- Dog identities and reversible identity aliases/corrections.
- Real-image reference gallery and local visual features.
- Portrait recipes/assets/outcomes, including in-flight and indeterminate paid requests.
- Per-date membership with a unique `(day, canonical_dog_id)` key.
- Durable jobs with attempt state, lease and retry/dependency timing.
- Collage revisions, archived metadata and latest desired publication.
- Publication receipts, daily budget reservations/usage and operational audit entries.

Store file content hashes and explicit schema/model versions. Unique event/observation and portrait recipe keys must enforce behavior even when two workers race. Database transactions must not be held open during a long AI or network operation.

Use SQLite's supported backup/checkpoint facilities; do not copy a live WAL database file alone and call it a complete backup.

## Ingest and frame selection

1. Record the source event before expensive work; acknowledge MQTT only according to the chosen library's verified delivery behavior. Do not rely on MQTT delivery guarantees to replace database deduplication.
2. Filter dog label, false-positive state, allowed actual camera IDs and required completed media.
3. Retrieve clip and Frigate's best object snapshot. Wait/retry boundedly for delayed recording availability.
4. Select native-resolution frames around useful observations; do not resize an entire 4K image before finding a distant dog.
5. Use actual tracking boxes with their correct frame/resolution/time mapping. A fixed box from one frame must not be reused blindly during PTZ movement. Re-detect or use a validated local tracker when source metadata is insufficient.
6. Separate multiple dogs and associate crops over time; reject unresolvable merged tracks. Preserve enough context locally to audit association.
7. Rank full-body visibility, crop size, sharpness and pose. Save a bounded selection, not an invented sharpened high-detail face.
8. Validate the media content independently of its extension; bound bytes, dimensions and decoder execution.
9. Resume/reconcile from a durable cursor with overlap and pagination. Track missed events whose recordings expired; never silently claim complete coverage.

## Description and identity matching

Send selected image views to the configured vision-capable Ollama model. Do not send MP4 bytes to an image-only endpoint or assume an arbitrary Gemma tag supports vision. Validate structured output locally and retry malformed responses within bounded local limits. Separate repeated visible facts from uncertain or conflicting observations.

Use a genuine **image** encoder for real-crop similarity. An Ollama text embedding of a description alone is not a visual re-identification system. Reuse an available suitable encoder; do not claim the descriptive Gemma model exposes image embeddings without verifying its actual API.

Combine multiple reference views and descriptive constraints. Downweight camera background and mutable accessories. Different lighting, grooming, poses and cameras must be represented in evaluation. Store model digest, preprocessing and feature dimension; do not compare incompatible feature spaces after an encoder change.

Identity decisions:
- **Known:** sufficiently strong calibrated agreement and separation from alternatives; add a sighting and reuse the portrait.
- **New:** sufficiently good observation with evidence inconsistent with existing accepted identities; establish a candidate/accepted identity according to the measured policy.
- **Uncertain:** inadequate evidence, conflicting views or lookalikes. Retain for review or another event, with no confident merge or forced generic portrait.

Serialize compare-and-create identity decisions or use an equivalent transactional design so simultaneous cross-camera arrivals do not each enroll the same recognizable dog. A later cross-camera duplicate may require reviewed merging; expose that correction and retain provenance.

Support CLI review, attach observation to identity, merge/split identities and reverse an incorrect merge. Preserve original observation records and historical collage bytes. Rebuild current membership through canonical identity mappings without rewriting historical evidence or automatically regenerating every portrait.

## Portrait job and paid-request state

Proposed states:
`planned → budget_reserved → submitting → submitted → succeeded → validated`,
with explicit `failed_before_submission`, `indeterminate` and `needs_review` branches.

- Unique recipe key: canonical dog identity + style/recipe version. Reserve it before sending a paid request.
- Record the request intent and budget before network submission. Save returned data promptly, then validate and finalize.
- Configure SDK retries explicitly. Default automatic SDK retries must not cause unintended duplicate paid image submissions.
- Only retry when it is established that submission did not occur, or the service provides a verified usable idempotency/retrieval mechanism. Do not invent API idempotency guarantees.
- A timeout after possible acceptance is **indeterminate**. Reconcile supported response/request metadata where available; otherwise require a bounded operator decision before spending again.
- Save model/request/usage metadata without secrets. An estimated dollar budget is supplemented by hard call/attempt/concurrency limits.
- Build/evaluation calls apply the build-file cap through an explicit test-budget interface as well as ongoing app limits. The production worker never reads the build TOML or requires its build-only budget.
- Reuse the first accepted saved portrait on returns and future days. Regeneration is an explicit versioned action within remaining authority, not an automatic response to every new frame.
- Default external input is structured description plus generated style art. Real camera crops require explicit opt-in and dog-only isolation. If handlers cannot be excluded, do not upload that frame.

Prompt content is data. Neither a model response nor visible text in a source frame may execute commands, choose filesystem paths, grant permissions or alter budgets.

## Daily state and publication ordering

Each day has a persistent generation ID. Each accepted membership change creates a new desired revision. A late portrait can append a new revision for the appropriate archived day without overwriting historical bytes, but it can publish only if that day is the current local day and its revision is still desired.

The reset operation:
1. Reconciles the current local date from an injected/testable clock.
2. Establishes the new day/generation exactly once.
3. Creates and archives an empty cream image when there are no accepted current-day memberships.
4. Queues the latest desired current-day output with priority over old revisions.
5. Preserves catalog, portraits and historical days.

Both timer and startup run the same idempotent reconciliation. Before final SMB replacement, re-check current wall-clock day and desired generation/revision under a publication serialization boundary shared with rollover. Use finite network timeouts; do not let a hung SMB call hold midnight state indefinitely.

The outbox coalesces obsolete revisions. One publisher owns the target. Across a crash after remote replacement but before recording success, read back the remote hash and reconcile; do not blindly replay an older image. Test overlapping workers and two publication attempts even if initial deployment uses one worker.

## Collage renderer

Use Pillow to alpha-composite already accepted portrait PNGs onto a cream RGB canvas. Preserve aspect ratios and original asymmetrical markings. Seed random placement from saved day/revision metadata, store actual placements and resolve collisions deterministically.

Handle zero dogs as a valid opaque blank image. Scale/layout all accepted members while enforcing minimum readability, complete silhouettes and margins. If all dogs cannot be placed, surface a capacity issue and retain the prior valid image; do not silently truncate the membership set. Any pagination policy is a scope decision to resolve explicitly.

## Publication contract

Prefer the high-level Python SMB client with supplied protected credentials; this avoids requiring a kernel CIFS mount in LXC. Verify modern authenticated SMB behavior and the actual share mapping.

Use an app-owned non-image temporary name on the same server filesystem, close it, verify content, and perform a supported atomic/safe replacement. Never delete the old final image first just to make rename succeed. If the watched slideshow reads temporary names, establish an approved same-filesystem staging location or stop that path with an actionable blocker.

Read back the final remote file, decode it, check its expected hash and dimensions, and record the receipt. This proves publication, not dashboard refresh. The browser check proves the latter.

## Proposed CLI to implement

These commands are a contract for the future builder, not installed commands:

~~~text
dog-art doctor --mode offline --redact
dog-art doctor --mode live --redact
dog-art run --mode shadow
dog-art run --mode live
dog-art replay --manifest PRIVATE_MANIFEST --sandbox SANDBOX_DIR
dog-art review list
dog-art review show OBSERVATION_ID
dog-art review assign OBSERVATION_ID DOG_ID
dog-art review merge SOURCE_DOG_ID TARGET_DOG_ID
dog-art review split DOG_ID --observations OBSERVATION_ID_LIST
dog-art review undo CORRECTION_ID
dog-art collage render --day YYYY-MM-DD --output LOCAL_PREVIEW
dog-art rollover
dog-art status --redact
dog-art backup --output PROTECTED_BACKUP
~~~

Replay/render default to a sandbox with paid APIs and production SMB disabled. Production rollover derives the current date itself; arbitrary past/future time injection is test-only. Review mutations must be explicit, auditable, transactionally safe and reversible where applicable.

All runtime subcommands must support explicit `--config` and `--secrets-file` global options, as defined in doc 03. Native services use absolute `/etc/dog-art/app.toml` and `/etc/dog-art/.env` paths; local examples run from the documented repository directory. Never pass secret values as CLI arguments.

