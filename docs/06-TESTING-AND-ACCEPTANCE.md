# Testing, visual review and acceptance evidence

## Test principles

Test observable behavior and failure recovery, not just internal method calls or agreement with the implementation. Use synthetic inputs/fake transports for deterministic failures, real independent-event labels for identity quality, actual local model calls for model compatibility, and controlled live access for deployment proof.

Never change assertions to make a required failure disappear. Fix the implementation or environment, retain a concise failure/correction record and re-run affected checks. Do not impose an arbitrary test-count target or claim configured CI has run.

The paths and CLI below are proposed interfaces to implement. They are not files/commands already installed by this document task.

## Required scenario matrix

| Test | Scenario and expected behavior | Requirements |
|---|---|---|
| T01 | Separate build/app TOML and allowlisted `.env` parse with correct types; unknown/duplicate/wrong-file keys fail, blank placeholders cannot enable live actions, runtime works without build config, and real `.env` stays out of Git/releases. | R01,R03,R14,R15,R33 |
| T02 | Path traversal, broad target roots, symlink surprises and unsafe source/SMB paths are rejected. | R19,R25,R33 |
| T03 | SQLite migration and backup/restore preserve identity, recipe, queue and day invariants; incompatible schema fails visibly. | R09,R23,R24 |
| T04 | Duplicate new/update/end notifications, reconnect replay and overlapping backfill create one event/observation/job set. | R04,R11,R24 |
| T05 | Non-dog, false-positive and unselected-camera inputs are excluded; each selected machine ID is accepted. | R03,R04 |
| T06 | Delayed clip, expired recordings, auth expiry, malformed media, byte/duration limits and decoder failures are explicit and retry boundedly. | R05,R24,R26 |
| T07 | Real crop selection respects native resolution, changing PTZ boxes, multiple dogs, occlusion and blur. | R06,R08 |
| T08 | An actual configured Ollama vision request returns validated structured facts; malformed output/conflicting views/unknown fields are handled. | R07,R08 |
| T09 | Match/new/uncertain decisions use compatible real-image features, calibrated thresholds and alternative-candidate margins. | R09,R10 |
| T10 | Independent same-dog return visits across dates and cameras reuse canonical identity; same-color lookalikes do not merge. | R09,R10,R11 |
| T11 | Simultaneous cross-camera observations cannot create duplicate accepted enrollments or duplicate portrait submissions. | R11,R12 |
| T12 | Reviewed assignment, merge/split and reversal preserve original observations, audit and historical collage bytes. | R10,R23 |
| T13 | New identity gets one portrait; existing identity today/tomorrow reuses accepted bytes without another paid call. | R12,R16 |
| T14 | Default cloud request contains description/generated style art only. Crop opt-in isolates dog pixels and excludes handlers; full MP4 is never sent. | R15,R33 |
| T15 | Dollar/call/attempt/concurrency bounds reject work before overspend; a key with missing budget cannot submit. | R14 |
| T16 | Timeout after possible submission, worker crash, SDK automatic retries and interrupted result saving do not blindly duplicate paid requests. | R11,R14,R24 |
| T17 | Portrait PNG decode, alpha exterior/fur edges, full-body anatomy, style and major markings pass automated plus actual visual review. | R13 |
| T18 | Zero dogs yields exact opaque cream 1920x1080 output; one/five/many dogs appear once at preserved proportions. | R16,R17 |
| T19 | Fixed recipe/assets/seed/placements reproduce the saved layout; margins and collisions are checked. | R17,R18 |
| T20 | Too many dogs or poor readable fit never silently truncates the day set; capacity state is actionable and last valid output survives. | R31 |
| T21 | Midnight creates the new day and blank revision once; prior catalog/portrait/archive bytes survive. | R21,R23 |
| T22 | DST 23/25-hour days, timezone offsets, crossed-midnight observations and startup after a missed midnight follow the timestamp contract. | R21,R32 |
| T23 | Yesterday's slow portrait completion, deferred job and stale retry cannot overwrite today's output. | R22,R32 |
| T24 | Two publisher attempts and a reset race are serialized; an old generation is rejected immediately before final replacement. | R19,R22 |
| T25 | SMB interrupted upload/replace, occupied file, denied credentials and disconnect preserve the prior good image and defer safely. | R19,R24 |
| T26 | Remote readback has the desired bytes/hash/dimensions. A crash after replacement but before receipt does not replay stale output. | R19,R22,R24 |
| T27 | Unrelated slideshow sentinel files and original input files remain unchanged through publish/reset/retry/rollback. | R25,R33 |
| T28 | The actual HA card displays successive revisions and the blank image through its normal slideshow/refresh behavior. | R20,R21 |
| T29 | Real CT112 native service start/restart and reset-timer scheduling work as the dedicated service user. | R01,R02,R21,R24 |
| T30 | Frigate/Ollama/OpenAI/SMB outages pause only dependent work; recovery resumes durable jobs without duplicates. | R24,R26 |
| T31 | Low disk and invalid/corrupt output do not publish broken data or delete retained history. | R23,R24,R31 |
| T32 | Logs/config receipts/exceptions/archives/test evidence exclude seeded secret values and credential-bearing URLs. | R26,R33 |
| T33 | Release package installs in a fresh environment/directory; imports come from the installed artifact, not the development checkout. | R27,R28 |
| T34 | Rollback restores a compatible app version and documented state backup; migrations never silently downgrade live state. | R23,R24,R28 |
| T35 | Operator commands, README examples, internal links and setup instructions work from the documented working directory. | R28 |
| T36 | Final integrated checks and independent review resolve known findings and map every R01–R34 requirement to real evidence. | R27,R29,R30,R34 |

## Test layers and suggested commands

Implement a reproducible toolchain and document its exact target-Python commands. Examples from the future implementation repository:

~~~sh
python -m pytest -q -m "not live and not local_model"
python -m pytest -q -m local_model
python -m pytest -q -m live
python -m ruff check .
python -m ruff format --check .
python -m compileall -q src
python -m build
~~~

- `local_model` checks must call only explicitly configured local services/models.
- `live` checks require separate explicit enablement, target readiness and budget/path guards. CI must not silently run paid API calls or write to the production slideshow.
- Offline test runs must have an explicit network-deny/fake-transport mechanism; an accidentally missing credential is not a dependable isolation strategy.
- Selecting only offline tests is valid evidence for offline behavior. Required live/model checks excluded from that run remain **NOT RUN/BLOCKED**, not passed or not applicable.
- Pin tool/dependency versions and record actual command, working directory, Python/runtime, source revision, time, exit code, result count and evidence path.
- Run the target CT112 Python/runtime. Claim additional version support only if actually tested or clearly labeled unverified.

## Fixture strategy

Use:
1. Synthetic event payloads and descriptions for deterministic malformed-data and ordering tests.
2. The supplied generated art for rendering/style comparisons.
3. Privately staged real video/crop fixtures, with provenance and authorization, for decoder, PTZ and visual evaluation.
4. Labeled independent visits and lookalike negatives for real returning-dog accuracy.

The five supplied clips help test five appearance examples. They do not by themselves demonstrate the same dog returning on different events or across cameras. Derived crops from one clip are useful within-event references, not independent test visits.

Keep real videos, real-crop galleries and any household/handler context in ignored protected storage. Sanitized payloads may be committed when IDs, names, locations and secrets are removed without changing important types/timing relationships.

## Portrait QA

For at least one controlled real API portrait and representative difficult cases:
- Compare against real dog references locally and the chosen style artwork.
- Inspect paws/limbs/ears/tail, harness/collar, major markings, pose and absence of extra animals/text.
- Composite onto cream and a dark test matte for inspection; save a bounded redacted/generated-art QA image.
- Verify that the saved deliverable's actual alpha channel isolates the dog. Corner samples alone are insufficient; check exterior regions and boundaries.
- Record input policy, recipe/style version, API model/settings, output hash and accept/review/fail decision.

A local VLM can help flag output problems but is not ground truth for identity or likeness. Bounded failed attempts must not become an unlimited paid retry loop.

## Live end-to-end sequence

After offline integration and access readiness:
1. Record installed release/model/config fingerprints and service identity on CT112.
2. Observe or replay a real authorized completed dog event into the actual installed service.
3. Verify a local description, identity decision and, for one new accepted dog, a bounded real API portrait.
4. Verify archived collage metadata and SMB readback.
5. Observe the current image in the real HA slideshow; record screenshot, card/view URL and refresh timing.
6. Exercise both configured cameras and an independently labeled returning-dog visit; prove the portrait-request ledger does not increment for the return.
7. Restart only the application service and verify persistence/recovery.
8. Run the controlled blank/restore acceptance exercise below or observe natural midnight, and verify normal current-day operation afterward.

If a needed real event or independent return sample is unavailable, a deterministic replay can prove plumbing but must not be labeled a natural return observation. Record the remaining identity/live evidence blocker.

## Reset acceptance without changing system time

Default `RESET_ACCEPTANCE_MODE=controlled_on_target` means:
- Unit/integration tests inject a clock and verify DST, startup catch-up and old-job races.
- An on-target isolated state directory runs the same reset code and timer/service entrypoint.
- A bounded controlled exercise publishes the valid blank to the single owned HA image, verifies SMB and dashboard display, then rebuilds/restores the valid **current** day from the production catalog.
- Verify the installed production timer's next scheduled local midnight and startup recovery.
- Do not set the Proxmox/CT112 host clock, erase the real day catalog, or execute a production reset with an arbitrary test date.
- Record which observations were controlled and whether a natural midnight was actually observed.

This controlled exercise is within the future launch's scoped owned-image publication authority. If existing platform/user policy requires an additional approval, obtain that specific approval. Natural midnight observation is useful supplementary evidence, not something to fabricate.

## Failure and release evidence

Use `PASS / FAIL / BLOCKED / NOT RUN / IN PROGRESS` accurately. Keep rejected/superseded evidence concise but traceable. A meaningful code/config/model change invalidates affected evidence; re-run appropriate checks before delivery.

Required output of phase J:
- Requirement R01–R34 and T01–T36 coverage.
- Actual offline/local/live/visual outcomes separated.
- Identity dataset size, independent split, errors/abstentions and known limits.
- API request/budget evidence and private-input policy.
- Final tested tree, artifact hash and deployed version.
- Dashboard and reset evidence, operational recovery and rollback.
- Explicit unresolved issues. Any required failure or blocker prevents an overall complete claim.

