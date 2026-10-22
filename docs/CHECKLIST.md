# Requirement and evidence matrix

Statuses refer to the full stated item. PASS entries below identify their actual evidence scope; offline tests do not establish required live gates. Evidence IDs refer to [validation](IMPLEMENTATION_VALIDATION.md). Numeric container examples112 are superseded by user-confirmed110.

| ID | Behavior / scenario | Status | Evidence |
|---|---|---|---|
| R01 | Runs directly as Python on Debian CT112, with no Docker runtime dependency. | IN PROGRESS | V01,V07; native installed service pending |
| R02 | Uses direct CT112 SSH when available; otherwise reaches the same running CT112 through `proxmox-host` and `pct exec 112`. | PASS | V01; actual route direct ct112, numeric110 |
| R03 | Selects Backyard East and Driveway PTZ using verified machine camera IDs. | IN PROGRESS | V03; events now observed from both selected IDs |
| R04 | Accepts dog events only, deduplicates repeated notifications, and handles completed-event media availability. | PASS | V02,V03; tests/test_ingest_pipeline.py |
| R05 | Downloads available clip/snapshot data using verified authorized Frigate access and its explicitly configured authentication mode. | IN PROGRESS | V03,V05; private source decode; live clip quality incomplete |
| R06 | Finds each dog independently and extracts clear, full-body real-image references. | BLOCKED | V05; nativePTZ lens gate preserved; full-body/multi-dog quality evidence incomplete |
| R07 | Obtains a detailed local description from a verified vision-capable configured Ollama model at the supplied host. | PASS | V04; pinned8b actual real-crop response |
| R08 | Keeps uncertain appearance facts explicit; does not turn unknown breed/markings into asserted identity facts. | BLOCKED | V02,V04,V05; actual adverse-condition evaluation incomplete |
| R09 | Maintains permanent identities and matches recognized returning dogs across visits/days and both cameras. | BLOCKED | V13; real independent returns/calibration missing |
| R10 | Abstains on ambiguous lookalikes or inadequate evidence and supports reviewed corrections. | BLOCKED | V02,V13; corrections pass offline; real ambiguity labels missing |
| R11 | Creates no duplicate identity/portrait when simultaneous events represent the same recognized dog. | BLOCKED | V02,V13; serialized uniqueness implemented; calibrated live cross-camera proof missing |
| R12 | Uses the OpenAI API for a newly established dog's watercolor portrait and reuses it on returns. | BLOCKED | V14; official SDK/fake path tested; paid new/return blocked |
| R13 | Matches the supplied pencil/watercolor style and produces a complete isolated dog with actual transparency. | BLOCKED | V14,V15; supplied assets inspected; new API likeness unperformed |
| R14 | Applies configured cost/call/concurrency limits and handles ambiguous billed request outcomes conservatively. | PASS | V02,V14; tests/test_foundation.py,test_portraits.py |
| R15 | Keeps full videos and recognition/description processing local; camera-crop upload is opt-in. | PASS | V02,V09,V14; cloud artwork-only assertions, opt-in currently refused |
| R16 | Shows each accepted distinct dog seen today exactly once, including previously cataloged dogs returning today. | IN PROGRESS | V02,V15; local daily membership tested; live accepted identities absent |
| R17 | Creates an opaque cream `1920x1080` collage with scattered placement, preserved proportions and complete silhouettes. | IN PROGRESS | V15; local exact render pass; live delivery pending |
| R18 | Saves reproducible layout metadata and portrait content hashes for each collage revision. | PASS | V02,V15; tests/test_composition.py reproducibility |
| R19 | Publishes the current image through Samba into the verified equivalent of `media/kitchen-tv`. | IN PROGRESS | V06; non-image staging pass; currentPNG not yet written |
| R20 | Shows the updated image in the actual existing Home Assistant dashboard slideshow. | IN PROGRESS | V10; exact picture card confirmed; actual rendering pending |
| R21 | Resets the owned display to an empty cream image at local midnight in America/New_York. | IN PROGRESS | V02,V12; clock/race tests and installed-tool syntax pass; installed/live blank pending |
| R22 | Prevents old-day jobs, retries and publisher races from restoring yesterday's collage after reset. | IN PROGRESS | V02; stale-generation/rollover/deadline tests; live exercise pending |
| R23 | Retains portrait assets, identity references and historical collages on CT112 across daily resets. | IN PROGRESS | V02; local persistence/immutable archive tests; installed-state reset pending |
| R24 | Recovers from process/container restart and Frigate/Ollama/OpenAI/SMB outage with bounded retries and durable work. | IN PROGRESS | V02,V06,V07; durable/fault/crash tests; real hardened service restart pending |
| R25 | Changes only application-owned CT112 paths/services and the single owned HA publication file. | IN PROGRESS | V06,V09; scoped staging preserves other media; installation/publication inventory pending |
| R26 | Provides useful redacted health, queue, recognition, model, publication, reset and error diagnostics. | IN PROGRESS | V02,V04; redacted doctor/status implemented; installed output pending |
| R27 | Uses project-local Git history, coherent checkpoints and tested/deployed artifact provenance. | IN PROGRESS | foundation eee09c6; branch codex/dog-art-pipeline; final provenance pending |
| R28 | Ships modular documentation and a reproducible, installable release with an executable operator guide. | IN PROGRESS | V07,V08; docs/package built; full delivery/native install pending |
| R29 | Continues autonomously through routine failures and records material decisions; escalates critical blockers. | PASS | IMPLEMENTATION_PLAN.md,IMPLEMENTATION_DECISIONS.md,BLOCKERS.md; actual recoveries recorded |
| R30 | Uses properly sequenced internal delegation where available, with integrated independent review. | PASS | V02; docs05 wave ownership followed; independent repair review observed |
| R31 | Handles growth without silently omitting today's dogs or deleting retained data. | PASS | V02,V15; layout-capacity/low-disk rejects without omission/deletion |
| R32 | Handles event-time/day membership, DST, midnight catch-up and crossed-midnight tracks consistently. | PASS | V02; DST/cross-midnight/startup timestamp-contract tests |
| R33 | Preserves secrets, private fixtures and existing user work; separates build settings, app settings and the single ignored secrets `.env`. | IN PROGRESS | V09,V08; final Git/release exclusion scan pending |
| R34 | Separates offline, on-target, live API, identity-quality and dashboard evidence. | IN PROGRESS | IMPLEMENTATION_VALIDATION.md; all70rows mapped, final reconciliation pending |
| T01 | Separate build/app TOML and allowlisted `.env` parse with correct types; unknown/duplicate/wrong-file keys fail, blank placeholders cannot enable live actions, runtime works without build config, and real `.env` stays out of Git/releases. | IN PROGRESS | V02; offline scenario covered; required live/package/operational part pending |
| T02 | Path traversal, broad target roots, symlink surprises and unsafe source/SMB paths are rejected. | PASS | V02; offline scenario covered; required live/package/operational part pending |
| T03 | SQLite migration and backup/restore preserve identity, recipe, queue and day invariants; incompatible schema fails visibly. | PASS | V02; offline scenario covered; required live/package/operational part pending |
| T04 | Duplicate new/update/end notifications, reconnect replay and overlapping backfill create one event/observation/job set. | PASS | V02; offline scenario covered; required live/package/operational part pending |
| T05 | Non-dog, false-positive and unselected-camera inputs are excluded; each selected machine ID is accepted. | PASS | V02; offline scenario covered; required live/package/operational part pending |
| T06 | Delayed clip, expired recordings, auth expiry, malformed media, byte/duration limits and decoder failures are explicit and retry boundedly. | PASS | V02; offline scenario covered; required live/package/operational part pending |
| T07 | Real crop selection respects native resolution, changing PTZ boxes, multiple dogs, occlusion and blur. | BLOCKED | V13; tests/test_local_ai.py,test_quality_evaluation.py; real label/quality gate incomplete |
| T08 | An actual configured Ollama vision request returns validated structured facts; malformed output/conflicting views/unknown fields are handled. | PASS | V04 plus tests/test_local_ai.py; real8b valid response and malformed/conflicting output handling |
| T09 | Match/new/uncertain decisions use compatible real-image features, calibrated thresholds and alternative-candidate margins. | BLOCKED | V13; tests/test_local_ai.py,test_quality_evaluation.py; real label/quality gate incomplete |
| T10 | Independent same-dog return visits across dates and cameras reuse canonical identity; same-color lookalikes do not merge. | BLOCKED | V13; tests/test_local_ai.py,test_quality_evaluation.py; real label/quality gate incomplete |
| T11 | Simultaneous cross-camera observations cannot create duplicate accepted enrollments or duplicate portrait submissions. | BLOCKED | V13; tests/test_local_ai.py,test_quality_evaluation.py; real label/quality gate incomplete |
| T12 | Reviewed assignment, merge/split and reversal preserve original observations, audit and historical collage bytes. | PASS | V02; offline scenario covered; required live/package/operational part pending |
| T13 | New identity gets one portrait; existing identity today/tomorrow reuses accepted bytes without another paid call. | BLOCKED | V02; offline scenario covered; required live/package/operational part pending |
| T14 | Default cloud request contains description/generated style art only. Crop opt-in isolates dog pixels and excludes handlers; full MP4 is never sent. | IN PROGRESS | V02; offline scenario covered; required live/package/operational part pending |
| T15 | Dollar/call/attempt/concurrency bounds reject work before overspend; a key with missing budget cannot submit. | PASS | V02; offline scenario covered; required live/package/operational part pending |
| T16 | Timeout after possible submission, worker crash, SDK automatic retries and interrupted result saving do not blindly duplicate paid requests. | PASS | V02; offline scenario covered; required live/package/operational part pending |
| T17 | Portrait PNG decode, alpha exterior/fur edges, full-body anatomy, style and major markings pass automated plus actual visual review. | BLOCKED | V02; offline scenario covered; required live/package/operational part pending |
| T18 | Zero dogs yields exact opaque cream 1920x1080 output; one/five/many dogs appear once at preserved proportions. | PASS | V02; offline scenario covered; required live/package/operational part pending |
| T19 | Fixed recipe/assets/seed/placements reproduce the saved layout; margins and collisions are checked. | PASS | V02; offline scenario covered; required live/package/operational part pending |
| T20 | Too many dogs or poor readable fit never silently truncates the day set; capacity state is actionable and last valid output survives. | PASS | V02; offline scenario covered; required live/package/operational part pending |
| T21 | Midnight creates the new day and blank revision once; prior catalog/portrait/archive bytes survive. | IN PROGRESS | V02; offline scenario covered; required live/package/operational part pending |
| T22 | DST 23/25-hour days, timezone offsets, crossed-midnight observations and startup after a missed midnight follow the timestamp contract. | PASS | V02; offline scenario covered; required live/package/operational part pending |
| T23 | Yesterday's slow portrait completion, deferred job and stale retry cannot overwrite today's output. | PASS | V02; offline scenario covered; required live/package/operational part pending |
| T24 | Two publisher attempts and a reset race are serialized; an old generation is rejected immediately before final replacement. | PASS | V02; offline scenario covered; required live/package/operational part pending |
| T25 | SMB interrupted upload/replace, occupied file, denied credentials and disconnect preserve the prior good image and defer safely. | PASS | V02; offline scenario covered; required live/package/operational part pending |
| T26 | Remote readback has the desired bytes/hash/dimensions. A crash after replacement but before receipt does not replay stale output. | IN PROGRESS | V02; offline scenario covered; required live/package/operational part pending |
| T27 | Unrelated slideshow sentinel files and original input files remain unchanged through publish/reset/retry/rollback. | IN PROGRESS | V02; offline scenario covered; required live/package/operational part pending |
| T28 | The actual HA card displays successive revisions and the blank image through its normal slideshow/refresh behavior. | IN PROGRESS | V02; offline scenario covered; required live/package/operational part pending |
| T29 | Real CT112 native service start/restart and reset-timer scheduling work as the dedicated service user. | IN PROGRESS | V02; offline scenario covered; required live/package/operational part pending |
| T30 | Frigate/Ollama/OpenAI/SMB outages pause only dependent work; recovery resumes durable jobs without duplicates. | IN PROGRESS | V02; offline scenario covered; required live/package/operational part pending |
| T31 | Low disk and invalid/corrupt output do not publish broken data or delete retained history. | PASS | V02; offline scenario covered; required live/package/operational part pending |
| T32 | Logs/config receipts/exceptions/archives/test evidence exclude seeded secret values and credential-bearing URLs. | PASS | V02; offline scenario covered; required live/package/operational part pending |
| T33 | Release package installs in a fresh environment/directory; imports come from the installed artifact, not the development checkout. | PASS | V08; fresh CT112 native venv, /tmp cwd, PYTHONPATHunset, site-packages import and bundled asset verified |
| T34 | Rollback restores a compatible app version and documented state backup; migrations never silently downgrade live state. | IN PROGRESS | V02; offline scenario covered; required live/package/operational part pending |
| T35 | Operator commands, README examples, internal links and setup instructions work from the documented working directory. | IN PROGRESS | V02; offline scenario covered; required live/package/operational part pending |
| T36 | Final integrated checks and independent review resolve known findings and map every R01–R34 requirement to real evidence. | IN PROGRESS | V02; offline scenario covered; required live/package/operational part pending |

Current scope override: [SCOPE_CHANGES.md](SCOPE_CHANGES.md). R09/R11/T09–T11 and return-only portions of R12/T13 are DEFERRED by explicit user decision. R16 counts accepted appearance entries, permitting repeated physical dogs. Original wording is preserved above for traceability, not silently weakened or marked passed.
