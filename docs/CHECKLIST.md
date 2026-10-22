# Requirement and evidence matrix

Statuses refer to actual implementation; NOT RUN is not PASS.

| ID | Behavior / scenario | Status | Evidence |
|---|---|---|---|
| R01 | Runs directly as Python on Debian CT112, with no Docker runtime dependency. | NOT RUN | Pending implementation and actual verification |
| R02 | Uses direct CT112 SSH when available; otherwise reaches the same running CT112 through `proxmox-host` and `pct exec 112`. | NOT RUN | Pending implementation and actual verification |
| R03 | Selects Backyard East and Driveway PTZ using verified machine camera IDs. | NOT RUN | Pending implementation and actual verification |
| R04 | Accepts dog events only, deduplicates repeated notifications, and handles completed-event media availability. | NOT RUN | Pending implementation and actual verification |
| R05 | Downloads available clip/snapshot data using verified authorized Frigate access and its explicitly configured authentication mode. | NOT RUN | Pending implementation and actual verification |
| R06 | Finds each dog independently and extracts clear, full-body real-image references. | NOT RUN | Pending implementation and actual verification |
| R07 | Obtains a detailed local description from a verified vision-capable configured Ollama model at the supplied host. | NOT RUN | Pending implementation and actual verification |
| R08 | Keeps uncertain appearance facts explicit; does not turn unknown breed/markings into asserted identity facts. | NOT RUN | Pending implementation and actual verification |
| R09 | Maintains permanent identities and matches recognized returning dogs across visits/days and both cameras. | NOT RUN | Pending implementation and actual verification |
| R10 | Abstains on ambiguous lookalikes or inadequate evidence and supports reviewed corrections. | NOT RUN | Pending implementation and actual verification |
| R11 | Creates no duplicate identity/portrait when simultaneous events represent the same recognized dog. | NOT RUN | Pending implementation and actual verification |
| R12 | Uses the OpenAI API for a newly established dog's watercolor portrait and reuses it on returns. | NOT RUN | Pending implementation and actual verification |
| R13 | Matches the supplied pencil/watercolor style and produces a complete isolated dog with actual transparency. | NOT RUN | Pending implementation and actual verification |
| R14 | Applies configured cost/call/concurrency limits and handles ambiguous billed request outcomes conservatively. | NOT RUN | Pending implementation and actual verification |
| R15 | Keeps full videos and recognition/description processing local; camera-crop upload is opt-in. | NOT RUN | Pending implementation and actual verification |
| R16 | Shows each accepted distinct dog seen today exactly once, including previously cataloged dogs returning today. | NOT RUN | Pending implementation and actual verification |
| R17 | Creates an opaque cream `1920x1080` collage with scattered placement, preserved proportions and complete silhouettes. | NOT RUN | Pending implementation and actual verification |
| R18 | Saves reproducible layout metadata and portrait content hashes for each collage revision. | NOT RUN | Pending implementation and actual verification |
| R19 | Publishes the current image through Samba into the verified equivalent of `media/kitchen-tv`. | NOT RUN | Pending implementation and actual verification |
| R20 | Shows the updated image in the actual existing Home Assistant dashboard slideshow. | NOT RUN | Pending implementation and actual verification |
| R21 | Resets the owned display to an empty cream image at local midnight in America/New_York. | NOT RUN | Pending implementation and actual verification |
| R22 | Prevents old-day jobs, retries and publisher races from restoring yesterday's collage after reset. | NOT RUN | Pending implementation and actual verification |
| R23 | Retains portrait assets, identity references and historical collages on CT112 across daily resets. | NOT RUN | Pending implementation and actual verification |
| R24 | Recovers from process/container restart and Frigate/Ollama/OpenAI/SMB outage with bounded retries and durable work. | NOT RUN | Pending implementation and actual verification |
| R25 | Changes only application-owned CT112 paths/services and the single owned HA publication file. | NOT RUN | Pending implementation and actual verification |
| R26 | Provides useful redacted health, queue, recognition, model, publication, reset and error diagnostics. | NOT RUN | Pending implementation and actual verification |
| R27 | Uses project-local Git history, coherent checkpoints and tested/deployed artifact provenance. | NOT RUN | Pending implementation and actual verification |
| R28 | Ships modular documentation and a reproducible, installable release with an executable operator guide. | NOT RUN | Pending implementation and actual verification |
| R29 | Continues autonomously through routine failures and records material decisions; escalates critical blockers. | NOT RUN | Pending implementation and actual verification |
| R30 | Uses properly sequenced internal delegation where available, with integrated independent review. | NOT RUN | Pending implementation and actual verification |
| R31 | Handles growth without silently omitting today's dogs or deleting retained data. | NOT RUN | Pending implementation and actual verification |
| R32 | Handles event-time/day membership, DST, midnight catch-up and crossed-midnight tracks consistently. | NOT RUN | Pending implementation and actual verification |
| R33 | Preserves secrets, private fixtures and existing user work; separates build settings, app settings and the single ignored secrets `.env`. | NOT RUN | Pending implementation and actual verification |
| R34 | Separates offline, on-target, live API, identity-quality and dashboard evidence. | NOT RUN | Pending implementation and actual verification |
| T01 | Separate build/app TOML and allowlisted `.env` parse with correct types; unknown/duplicate/wrong-file keys fail, blank placeholders cannot enable live actions, runtime works without build config, and real `.env` stays out of Git/releases. | NOT RUN | Pending implementation and actual verification |
| T02 | Path traversal, broad target roots, symlink surprises and unsafe source/SMB paths are rejected. | NOT RUN | Pending implementation and actual verification |
| T03 | SQLite migration and backup/restore preserve identity, recipe, queue and day invariants; incompatible schema fails visibly. | NOT RUN | Pending implementation and actual verification |
| T04 | Duplicate new/update/end notifications, reconnect replay and overlapping backfill create one event/observation/job set. | NOT RUN | Pending implementation and actual verification |
| T05 | Non-dog, false-positive and unselected-camera inputs are excluded; each selected machine ID is accepted. | NOT RUN | Pending implementation and actual verification |
| T06 | Delayed clip, expired recordings, auth expiry, malformed media, byte/duration limits and decoder failures are explicit and retry boundedly. | NOT RUN | Pending implementation and actual verification |
| T07 | Real crop selection respects native resolution, changing PTZ boxes, multiple dogs, occlusion and blur. | NOT RUN | Pending implementation and actual verification |
| T08 | An actual configured Ollama vision request returns validated structured facts; malformed output/conflicting views/unknown fields are handled. | NOT RUN | Pending implementation and actual verification |
| T09 | Match/new/uncertain decisions use compatible real-image features, calibrated thresholds and alternative-candidate margins. | NOT RUN | Pending implementation and actual verification |
| T10 | Independent same-dog return visits across dates and cameras reuse canonical identity; same-color lookalikes do not merge. | NOT RUN | Pending implementation and actual verification |
| T11 | Simultaneous cross-camera observations cannot create duplicate accepted enrollments or duplicate portrait submissions. | NOT RUN | Pending implementation and actual verification |
| T12 | Reviewed assignment, merge/split and reversal preserve original observations, audit and historical collage bytes. | NOT RUN | Pending implementation and actual verification |
| T13 | New identity gets one portrait; existing identity today/tomorrow reuses accepted bytes without another paid call. | NOT RUN | Pending implementation and actual verification |
| T14 | Default cloud request contains description/generated style art only. Crop opt-in isolates dog pixels and excludes handlers; full MP4 is never sent. | NOT RUN | Pending implementation and actual verification |
| T15 | Dollar/call/attempt/concurrency bounds reject work before overspend; a key with missing budget cannot submit. | NOT RUN | Pending implementation and actual verification |
| T16 | Timeout after possible submission, worker crash, SDK automatic retries and interrupted result saving do not blindly duplicate paid requests. | NOT RUN | Pending implementation and actual verification |
| T17 | Portrait PNG decode, alpha exterior/fur edges, full-body anatomy, style and major markings pass automated plus actual visual review. | NOT RUN | Pending implementation and actual verification |
| T18 | Zero dogs yields exact opaque cream 1920x1080 output; one/five/many dogs appear once at preserved proportions. | NOT RUN | Pending implementation and actual verification |
| T19 | Fixed recipe/assets/seed/placements reproduce the saved layout; margins and collisions are checked. | NOT RUN | Pending implementation and actual verification |
| T20 | Too many dogs or poor readable fit never silently truncates the day set; capacity state is actionable and last valid output survives. | NOT RUN | Pending implementation and actual verification |
| T21 | Midnight creates the new day and blank revision once; prior catalog/portrait/archive bytes survive. | NOT RUN | Pending implementation and actual verification |
| T22 | DST 23/25-hour days, timezone offsets, crossed-midnight observations and startup after a missed midnight follow the timestamp contract. | NOT RUN | Pending implementation and actual verification |
| T23 | Yesterday's slow portrait completion, deferred job and stale retry cannot overwrite today's output. | NOT RUN | Pending implementation and actual verification |
| T24 | Two publisher attempts and a reset race are serialized; an old generation is rejected immediately before final replacement. | NOT RUN | Pending implementation and actual verification |
| T25 | SMB interrupted upload/replace, occupied file, denied credentials and disconnect preserve the prior good image and defer safely. | NOT RUN | Pending implementation and actual verification |
| T26 | Remote readback has the desired bytes/hash/dimensions. A crash after replacement but before receipt does not replay stale output. | NOT RUN | Pending implementation and actual verification |
| T27 | Unrelated slideshow sentinel files and original input files remain unchanged through publish/reset/retry/rollback. | NOT RUN | Pending implementation and actual verification |
| T28 | The actual HA card displays successive revisions and the blank image through its normal slideshow/refresh behavior. | NOT RUN | Pending implementation and actual verification |
| T29 | Real CT112 native service start/restart and reset-timer scheduling work as the dedicated service user. | NOT RUN | Pending implementation and actual verification |
| T30 | Frigate/Ollama/OpenAI/SMB outages pause only dependent work; recovery resumes durable jobs without duplicates. | NOT RUN | Pending implementation and actual verification |
| T31 | Low disk and invalid/corrupt output do not publish broken data or delete retained history. | NOT RUN | Pending implementation and actual verification |
| T32 | Logs/config receipts/exceptions/archives/test evidence exclude seeded secret values and credential-bearing URLs. | NOT RUN | Pending implementation and actual verification |
| T33 | Release package installs in a fresh environment/directory; imports come from the installed artifact, not the development checkout. | NOT RUN | Pending implementation and actual verification |
| T34 | Rollback restores a compatible app version and documented state backup; migrations never silently downgrade live state. | NOT RUN | Pending implementation and actual verification |
| T35 | Operator commands, README examples, internal links and setup instructions work from the documented working directory. | NOT RUN | Pending implementation and actual verification |
| T36 | Final integrated checks and independent review resolve known findings and map every R01–R34 requirement to real evidence. | NOT RUN | Pending implementation and actual verification |
