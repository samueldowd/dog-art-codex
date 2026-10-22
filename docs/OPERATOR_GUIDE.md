# Operator guide

Use `/opt/dog-art/current/venv/bin/dog-art --config /etc/dog-art/app.toml --secrets-file /etc/dog-art/.env` as the command prefix after installation. Never pass passwords/API keys as arguments. These commands are implemented; production installation/live acceptance status is recorded separately in validation.

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

`review show` exposes private local crop paths; keep its output private. Inspect multiple real views, independent event provenance and lookalike candidates. A collar/coat description, neighboring frames, generated art or an event ID is not proof of identity. Visibility review records evidence without overwriting original observations. Accepted assignments enqueue membership rebuild; original observations/correction history/historical collages are preserved. Do not merge an ambiguous dog just to finish a collage.

Portrait results enter `needs_review`. Inspect complete paws/ears/tail, major markings, anatomy, generated-style fidelity, and cream/dark mattes before acceptance. Alpha checks alone cannot prove likeness. Rejected/indeterminate paid submissions are never blindly retried. An unresolved billed outcome needs provider evidence and a separately authorized bounded decision.

State is local: `catalog.sqlite`, `references/`, `portraits/`, `archives/YYYY-MM-DD/`, `staging/`, `models/`, `backups/`, `locks/`. Layout PNG/JSON archives are immutable. Today's canonical IDs are unique; a return reuses an accepted portrait even when its pose/description changes. Missing portraits hold membership and prior valid output. No retained archives are automatically deleted.

`collage render --day YYYY-MM-DD --output ABSOLUTE_PREVIEW --sandbox NEW_EMPTY_ABSOLUTE_DIR` makes a local preview from a database backup and copied portrait inputs, with no production publication. `replay --manifest PRIVATE_MANIFEST --sandbox NEW_EMPTY_ABSOLUTE_DIR` validates/stages offline events/observations with paid/network/production writes disabled; it reports exactly which steps ran.

After repairing an unavailable dependency, `retry --dependencies` wakes parked work without resetting finite attempt counts. Exhausted work remains visible for diagnosis. Portrait acceptance wakes relevant current/historical collage work. Restart only Dog Art after a release/config repair and verify actual queue recovery. Preserve unrelated HA images, the last valid collage and retained catalog/artwork throughout.
