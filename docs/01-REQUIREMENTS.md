# Requirements and success criteria

## Authority and labels

The user requested a build document, not a running system, on 2026-10-22. This module defines the future implementation's behavior.

**Confirmed** means stated by the user. **Default** means a proposed reversible engineering choice. **Discover** means verify in the target environment. **Blocker** means required work cannot be completed honestly until resolved.

All implementation criteria below begin **NOT STARTED**. The future builder must create a separate live checklist with actual status, evidence links, source revision, environment and observation time.

## Functional and operational requirements

| ID | Required observable behavior | Minimum acceptance evidence | Phases |
|---|---|---|---|
| R01 | Runs directly as Python on Debian CT112, with no Docker runtime dependency. | Installed OS/Python versions, package origin, service identity and running process on CT112. | A,H |
| R02 | Uses direct CT112 SSH when available; otherwise reaches the same running CT112 through `proxmox-host` and `pct exec 112`. | Redacted access report identifies target and demonstrated route; no host deployment. | A,H |
| R03 | Selects Backyard East and Driveway PTZ using verified machine camera IDs. | Config-to-display-name mapping and real events from both selected cameras; another camera is excluded. | A,C,H |
| R04 | Accepts dog events only, deduplicates repeated notifications, and handles completed-event media availability. | Replay tests for new/update/end, duplicates, false positives, delayed clip and non-dog events. | C,G |
| R05 | Downloads available clip/snapshot data using verified authorized Frigate access and its explicitly configured authentication mode. | Valid media decode, configured auth behavior, retry, missing-recording case and bounded download limits. | C,H |
| R06 | Finds each dog independently and extracts clear, full-body real-image references. | Frame/crop contact sheets, multiple-dog, moving PTZ, resolution-scaling, blur and occlusion cases. | C,G |
| R07 | Obtains a detailed local description from a verified vision-capable configured Ollama model at the supplied host. | Actual configured tag/capabilities, sanitized local request/result and schema validation. | D,H |
| R08 | Keeps uncertain appearance facts explicit; does not turn unknown breed/markings into asserted identity facts. | Poor-light, partial-dog and conflicting-frame evaluations; unknown fields retained. | D,G |
| R09 | Maintains permanent identities and matches recognized returning dogs across visits/days and both cameras. | Labeled independent-event evaluation, match evidence, persistent IDs before/after restart. | D,G,H,I |
| R10 | Abstains on ambiguous lookalikes or inadequate evidence and supports reviewed corrections. | Ambiguous case enters review; CLI correction/merge/split audit and safe regeneration rules tested. | D,G |
| R11 | Creates no duplicate identity/portrait when simultaneous events represent the same recognized dog. | Cross-camera concurrent replay and database/job uniqueness tests. | B,D,E,G |
| R12 | Uses the OpenAI API for a newly established dog's watercolor portrait and reuses it on returns. | Controlled real API request for a new identity; return replay/live test records zero additional paid calls. | E,H |
| R13 | Matches the supplied pencil/watercolor style and produces a complete isolated dog with actual transparency. | Decoded alpha/matte QA, full-body/style/marking inspection, checksums and saved prompt/model settings. | E,G,H |
| R14 | Applies configured cost/call/concurrency limits and handles ambiguous billed request outcomes conservatively. | Limit and timeout tests; recorded budget reservations, requests and results without duplicate automatic paid retries. | B,E,G |
| R15 | Keeps full videos and recognition/description processing local; camera-crop upload is opt-in. | Network-request assertions and privacy sentinels; default cloud payload uses description/generated style art only. | D,E,G |
| R16 | Shows each accepted distinct dog seen today exactly once, including previously cataloged dogs returning today. | Zero/one/five/many-dog membership tests; repeated same-day return changes last-seen only. | B,F,G,H |
| R17 | Creates an opaque cream `1920x1080` collage with scattered placement, preserved proportions and complete silhouettes. | Exact pixel dimensions, color/opacity test, visual review and collision/margin checks. | F,G,H |
| R18 | Saves reproducible layout metadata and portrait content hashes for each collage revision. | Re-render produces the expected layout with recorded seed/settings; archive receipt verifies inputs. | F,G |
| R19 | Publishes the current image through Samba into the verified equivalent of `media/kitchen-tv`. | Temporary upload, safe replacement, remote decoded-image/hash readback and ownership checks. | F,H |
| R20 | Shows the updated image in the actual existing Home Assistant dashboard slideshow. | Browser/Computer Use screenshot or directly observed equivalent, URL/card, revision and refresh behavior recorded. | H,I |
| R21 | Resets the owned display to an empty cream image at local midnight in America/New_York. | Clock/DST tests, installed timer schedule, controlled on-target blank/restore exercise or natural midnight evidence. | F,H,I |
| R22 | Prevents old-day jobs, retries and publisher races from restoring yesterday's collage after reset. | Delayed portrait completion, retry, two-publisher, rollover/restart and outbox-order tests. | B,F,G,I |
| R23 | Retains portrait assets, identity references and historical collages on CT112 across daily resets. | Before/after inventory and persistence tests; date/revision archives remain readable. | B,F,I |
| R24 | Recovers from process/container restart and Frigate/Ollama/OpenAI/SMB outage with bounded retries and durable work. | Fault injection, crash-restart, reclaimable job leases, recent-event reconciliation and actual service restart. | B,G,H,I |
| R25 | Changes only application-owned CT112 paths/services and the single owned HA publication file. | Scoped installation/publish inventory and preservation tests with unrelated slideshow sentinel files. | A,F,H |
| R26 | Provides useful redacted health, queue, recognition, model, publication, reset and error diagnostics. | Doctor/status output and sanitized structured logs covering success, uncertainty and faults. | B,G,H |
| R27 | Uses project-local Git history, coherent checkpoints and tested/deployed artifact provenance. | Base/final/tested revisions, clean owned scope, package hash, deployment receipt and rollback record. | A–J |
| R28 | Ships modular documentation and a reproducible, installable release with an executable operator guide. | Fresh-directory/package installation test, documented commands and checked links/examples. | G,J |
| R29 | Continues autonomously through routine failures and records material decisions; escalates critical blockers. | Phase/decision/blocker logs, recovery evidence and no misleading completion statuses. | A–J |
| R30 | Uses properly sequenced internal delegation where available, with integrated independent review. | Task ownership/dependencies, returned evidence, primary integration checks and reviewer findings resolved. | B–J |
| R31 | Handles growth without silently omitting today's dogs or deleting retained data. | Many-dog layout test; explicit capacity/disk-space behavior preserves last good output and raises an actionable blocker. | F,G,I |
| R32 | Handles event-time/day membership, DST, midnight catch-up and crossed-midnight tracks consistently. | Timestamp contract and deterministic tests; old observations archive without stale publication. | B,F,G,I |
| R33 | Preserves secrets, private fixtures and existing user work; separates build settings, app settings and the single ignored secrets `.env`. | Repository/artifact/log scans, wrong-file/key tests, runtime without build config and Git/archive exclusions; no real credentials or private recordings committed. | A–J |
| R34 | Separates offline, on-target, live API, identity-quality and dashboard evidence. | Final report has distinct statuses and no skipped required check labeled passed. | G–J |

## Today's dogs and daily reset

- The identity catalog, portraits and reference galleries are permanent until a separately authorized retention decision.
- A daily membership set contains accepted `dog_id` values observed on that local calendar date.
- Resolve identity before changing membership. Ambiguous observations do not receive invented confident identities.
- Use actual qualifying observation timestamps. If a continuous event includes timestamped observations on both sides of midnight, it can contribute to both day sets. If only an event start timestamp is available, document that source limitation and use it consistently; never use processing-completion time as observation time.
- At rollover, atomically establish the new day/generation in persistent state and queue its blank image. No older publication may supersede it.
- No reset may clear the permanent catalog, previous dates, reference evidence, portraits or archives.
- An unreachable HA VM cannot be updated remotely. Keep reset state locally and publish the current valid image as soon as access returns; report publication lag honestly.

## Recognition acceptance

Dog re-identification is a probabilistic appearance match, not proof of an individual animal's identity. Shared coat/breed descriptions, the same handler, location or collar are insufficient alone. Accessories may change.

Before enabling automatic accepted matches:
1. Use labeled **independent events**, with both selected cameras where available and representative lighting.
2. Include distinct lookalike dogs as negative examples and uncertain/low-quality crops as abstention examples.
3. Hold out events from enrollment/calibration. Adjacent frames or augmented copies of one clip are not independent return visits.
4. Measure false merges, correct returns, false splits and review/abstention rate separately.
5. Proposed starting release targets: **zero observed false merges on the labeled hard-negative set** and **at least 90% correct reuse on recognizable held-out returns**. These are engineering targets, not statistical guarantees. Document sample counts and confidence limits.
6. Missing independent return/negative data blocks a claim that R09 is empirically proven. Build and shadow-mode testing may continue, but do not enable uncalibrated automatic merging or call the whole deployment complete.
7. Do not fabricate a numeric confidence threshold before choosing the image model and measuring its score distributions. Score scales differ across encoders.

## Visual acceptance

- Reuse the supplied artwork as style references and the five-dog collage as a visual target.
- No extra animals, missing limbs, clipped tails/paws, accidental captions or changed major coat markings.
- Request actual transparent PNGs and inspect compositing on both cream and a dark test matte; a checkerboard or painted background is not transparency.
- A tiny edge-antialias alpha value is not the same as an opaque background. Inspect large exterior areas and fur boundaries, not only corner samples.
- Collage layout uses seeded scattered placement. Reject collisions/crops; retain layout metadata and reasonable margins. Do not mirror asymmetrical markings just to vary orientation.
- If portrait generation fails likeness/style checks after bounded authorized attempts, hold that portrait for review. Save the prior working collage and record what is missing.
- Never silently substitute an illustrative generic dog when the camera evidence cannot support the requested likeness.

## Overall result states

- **COMPLETE:** all required scope, live acceptance, evidence, versioning and handoff pass.
- **OFFLINE IMPLEMENTATION COMPLETE; LIVE ACCEPTANCE BLOCKED:** useful intermediate checkpoint, not overall completion.
- **IN PROGRESS / INTERRUPTED:** implementation or user-requested stop, with accurate remaining work.
- **BLOCKED:** a specific essential dependency needs user/external action after viable alternatives were considered.
- **FAIL:** required behavior is incorrect; continue fixing while meaningful authorized work remains.

A future builder must not pre-check any acceptance item merely by copying this specification.

