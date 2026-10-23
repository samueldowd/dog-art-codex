# Operator guide

On CT112, run from the application-owned `/var/lib/dog-art` directory as `dog-art` through normal sudo. Python SMB worker spawning cannot inherit an SSH user home that the dedicated account cannot traverse. Keep home permissions unchanged. Use `/opt/dog-art/current/venv/bin/dog-art --config /etc/dog-art/app.toml --secrets-file /etc/dog-art/.env` as the command prefix after installation. Never pass passwords/API keys as arguments. These commands are implemented; production installation/live acceptance status is recorded separately in validation.

```text
status --redact
doctor --mode offline --redact
doctor --mode live --redact
run --mode shadow --once
run --mode shadow
run --mode live
rollover
rollover --publish
retry --dependencies
backup --output /var/lib/dog-art/backups/operator-unique-name.sqlite
review list
review show OBSERVATION_ID
review visibility OBSERVATION_ID --full-body --reviewer OPERATOR --evidence LOCAL_REVIEW_RECEIPT
review visibility OBSERVATION_ID --no-full-body --reviewer OPERATOR --evidence LOCAL_REVIEW_RECEIPT
review enroll OBSERVATION_ID --reason EXPLICIT_NEW_IDENTITY_EVIDENCE
review assign OBSERVATION_ID DOG_ID --reason RETURN_VISIT_EVIDENCE
review merge SOURCE_DOG_ID TARGET_DOG_ID --reason CORRECTION_EVIDENCE
review split DOG_ID --observations OBSERVATION_ID_LIST --reason CORRECTION_EVIDENCE
review undo CORRECTION_ID --reason REVERSAL_EVIDENCE
portrait generate DOG_ID --observation OBSERVATION_ID --reserve-usd NUMERIC_CAP --build-scope UNIQUE_BUILD_SCOPE --build-cap-usd AUTHORIZED_BUILD_CAP
portrait accept RECIPE_KEY --reviewer OPERATOR --evidence LOCAL_VISUAL_QA_RECEIPT
```

`--data-root` is an explicit global non-secret override for isolated work. Production reset always derives the actual local date. There is no production arbitrary-date reset option. `run shadow` does not spend or publish; `rollover --publish` requires the app publication flag/mapping/credentials. Do not enable paid generation before model/cost/identity policy readiness.

`review show` exposes private local crop paths; keep its output private. Inspect multiple real views, independent event provenance and lookalike candidates. A collar/coat description, neighboring frames, generated art or an event ID is not proof of identity. Visibility review records evidence without overwriting original observations. Current best_effort_partial policy permits usable confirmed facts from partial views while preserving their original limitations; it does not assert exact unseen markings or proven physical identity. Accepted assignments enqueue membership rebuild; original observations/correction history/historical collages are preserved. Do not merge an ambiguous dog just to finish a collage.

Portrait results enter `needs_review`. Inspect complete paws/ears/tail, major markings, anatomy, generated-style fidelity, and cream/dark mattes before acceptance. Alpha checks alone cannot prove likeness. Rejected/indeterminate paid submissions are never blindly retried. An unresolved billed outcome needs provider evidence and a separately authorized bounded decision.

State is local: `catalog.sqlite`, `references/`, `portraits/`, `archives/YYYY-MM-DD/`, `staging/`, `models/`, `backups/`, `locks/`. Layout PNG/JSON archives are immutable. In the current user-selected per_observation mode, each qualifying immutable observation has one appearance entry; replay reuses its portrait, while a later physical return may produce another entry/portrait within the existing limits. Calibrated identity mode remains deferred and must not be enabled without its independent acceptance evidence. Missing portraits hold membership and prior valid output. No retained archives are automatically deleted.

`collage render --day YYYY-MM-DD --output ABSOLUTE_PREVIEW --sandbox NEW_EMPTY_ABSOLUTE_DIR` makes a local preview from a database backup and copied portrait inputs, with no production publication. `replay --manifest PRIVATE_MANIFEST --sandbox NEW_EMPTY_ABSOLUTE_DIR` validates/stages offline events/observations with paid/network/production writes disabled; it reports exactly which steps ran.

After repairing an unavailable dependency, `retry --dependencies` wakes parked work without resetting finite attempt counts. Exhausted work remains visible for diagnosis. Portrait acceptance wakes relevant current/historical collage work. Restart only Dog Art after a release/config repair and verify actual queue recovery. Preserve unrelated HA images, the last valid collage and retained catalog/artwork throughout.

Saved generated portraits can be reviewed automatically with `PORTRAIT_REVIEW_MODE="local_vlm"` in live mode. The pinned local Ollama model receives only cream/dark composites of saved generated artwork and the bundled generated style; camera pixels are excluded. All six schema checks must be true with no reasons, and file/facts/style/model/policy provenance must agree. A completed negative or ambiguous verdict stays `needs_review`. Technical failures use finite read retries; exhaustion stays visible and never triggers a new paid request. `operator` remains the default when the setting is absent.

Startup recovers valid deterministic saved PNG or complete `.partial` bytes belonging to an existing successful request under the paid-request lock. It records `needs_review`, never approves or resubmits them. Missing, corrupt, mismatched or conflicting evidence receives an explicit `saved_portrait_*` manual hold. Preserve all such files and the ledger for diagnosis; do not clear them to obtain another paid attempt.

The approved `custom:dog-art-picture` configuration and module are shipped under `deploy/home-assistant/`. Its fixed authenticated media URI is refreshed every 30 seconds while the dashboard is visible; hidden pages pause and resume when shown. It accepts only same-origin PNG bytes at the owned path, checks 1920x1080, and preserves the previous decoded image during outages. A module installation/update needs one browser reload; successive image replacements do not. No Home Assistant restart or entity/service change is required. Rollback replaces only this card with its saved prior picture-card configuration through a fresh guarded dashboard API patch; leave other dashboard cards unchanged.

`rollover` reports `composition_pending=true` when accepted members are waiting for portraits. That is a retained dependency, not failed calendar reconciliation. A durable `reset_pending` empty revision has priority until its current-day/generation publication is verified, even if a sighting arrives before the midnight timer. Later full art waits for that reset receipt; an already published day is never blanked again by routine reconciliation. `build` still surfaces missing art. No accepted membership or retained archive is cleared to obtain a successful reset.

With COLLAGE_PORTRAIT_POLICY="approved_only", status.display reports accepted_appearances, approved_portraits, pending_portraits and pending_states. paid_today reports request count and reserved_usd, which is a conservative guard rather than the provider bill. The current collage contains every approved portrait; pending appearances stay in the catalog and receipt. Each later approval advances the desired revision automatically. rollover can report composition_pending=true alongside render_pending=false when approved art is publishable while other portraits wait. Do not clear QA holds or raise budgets just to remove that pending count.
