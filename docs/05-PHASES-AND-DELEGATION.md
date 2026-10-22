# Iterative phases and subagent sequencing

## Execution rule

This is one continuous future build after explicit activation. Phase boundaries are automatic engineering checkpoints, not requests for user sign-off. Read findings, fix failures, update evidence and proceed. Independent work may continue while a genuine blocker waits for user input.

The primary agent must maintain `docs/IMPLEMENTATION_PLAN.md` with phase state, dependencies, changed files, actual commands/results, decisions, surprises and next actions. No phase begins marked passed.

## Phase plan

| Phase | Goal and required work | Entry dependency | Exit evidence / checkpoint |
|---|---|---|---|
| A — Verify scope, access and baseline | Read brief/modules/instructions, inspect target repo, source assets, CT112/fallback route, resources, services, camera mappings, credentials readiness and permission boundaries. Initialize logs and requirement map. | Explicit build activation. | Redacted preflight with known/default/unknown values, scoped target identity, Git baseline and concrete blockers. Continue offline work for missing external inputs. |
| B — Establish contracts and durable foundation | Implement separate build/app TOML and allowlisted `.env` validation, records, SQLite migrations, queue/leases, uniqueness, clock abstraction, scoped budget/request ledger, path policy, redaction and CLI skeleton with no implicit live actions. | A; viable local repo and toolchain. | Offline foundation tests, config separation/exclusion, runtime without build config, migration/rollback/backup behavior and reviewed shared interfaces. Primary commits baseline contracts before parallel module work. |
| C — Ingest and extract observations | Frigate/MQTT or equivalent polling, dedup/reconciliation, authenticated media retrieval, native-resolution samples, PTZ/multi-dog crops, quality/provenance and private fixtures. | B; source contract. Live fetch additionally needs Frigate access. | Replay suite and contact-sheet review. Real read-only source fetch when available; missing media/access explicitly tracked. |
| D — Describe and recognize | Ollama adapter/JSON descriptions, verified local visual encoder, reference galleries, calibration, known/new/uncertain decisions, review/correction and cross-camera race handling. | B; synthetic observations initially; C for real calibration. | Local-model smoke, independent-event identity evaluation, abstention and correction tests. No uncalibrated auto-merge promotion. |
| E — Generate and validate portraits | Prompt/style recipe, official OpenAI API, input policy, paid-request ledger, finite limits, saving/alpha/likeness QA and portrait reuse. | B; D identity contract. Paid smoke also needs credential/model/numeric limits. | Fake-transport fault tests plus bounded actual API output and quality review. Zero extra calls on a recognized return. |
| F — Compose, reset and publish | Pillow random layout, daily membership/generation, archival, reset/startup catch-up, SMB adapter, latest-only outbox and readback. | B; existing art can stand in for E during development. Production publishing needs verified SMB readiness. | Zero/one/five/many renders, time/race/fault tests and isolated SMB staging. No production enablement by a subagent. |
| G — Integrate and independently review | Connect modules; test full replay, concurrency, crash/outage, budget/privacy, identity quality, packaging and docs against one integrated tree. Fix review findings. | C–F integrated; required offline contract checks pass. | Final offline suite, labeled visual/identity report, independent review findings/resolutions and tested-tree fingerprint. |
| H — Install and exercise on CT112 | Build/install the exact release in a native venv, configure scoped services/secrets, migrate local state, stage SMB, controlled live API/event path, both cameras and dashboard refresh. | G plus verified essential live inputs and authorization. | On-target receipt, real source/API/publish/dashboard evidence, installed/deployed source hash. Required live blockers remain open. |
| I — Verify operation and recovery | Real service restart, outage recovery, timer schedule, controlled on-target blank/restore or natural midnight, race/backlog/disk-space behavior and a bounded observation window. | H; working app-owned publication. | Operational scenario evidence and restoration of valid current-day output; no unintended production changes. |
| J — Finalize release, docs and handoff | Reconcile requirement checklist, decisions, blocker state, operator docs, reproducible artifact, checksums, Git checkpoints and final delivery receipt. Rerun affected tests after fixes. | All required prior exits; no hidden required failures. | All mandatory requirements mapped to fresh evidence, tested/deployed/final revisions distinguished, clean owned scope and complete report. |

A phase can be partially complete while an external gate is blocked. Record that state explicitly. “Offline module implemented” is not a pass for its required live behavior.

## Delegation policy

Internal subagents are explicitly requested for the future implementation where available. Use the current client's supported delegation tools. Inherit the parent's model/settings unless the user or applicable instructions explicitly select others. Do not assume fixed tool names, maximum concurrency, custom agent configuration or a separate security sandbox.

Do not create new user-owned chats, recurring jobs, background agents or messages to other chats as a substitute for internal delegation. Subagents inherit actual permissions; role wording does not grant new access.

The primary agent owns:
- Shared schemas, migrations, root config, dependency locks and architecture decisions.
- Git index, branches, commits and integration in any shared checkout.
- Live deployments, paid calls, secrets provisioning and the single publisher.
- Exit-criterion decisions, final integrated tests and truthful completion.

## Wave 0: primary-led baseline

Perform A and B in sequence. A read-only discovery subagent may inspect documentation or existing code while the primary verifies environment access, but it must not modify sources or connect using new authority. Publish the agreed interface contract and file ownership before implementation workers start.

## Wave 1: independent module work after B

Use only available slots; queue roles or execute them sequentially when needed.

| Role | Owned implementation area | Inputs | Required return |
|---|---|---|---|
| Ingest worker | `frigate/`, `vision/` and owned tests | Event/Observation contracts, fixture/privacy rules | Paths, media/PTZ/multi-dog evidence, actual tests, remaining access gaps |
| Local-AI worker | `description/`, `identity/` and owned tests | Description/Identity contracts, fixed schema and fake crops | Model candidates/provenance, schema and matching tests, calibration limits; no model substitution |
| Composition worker | `daily/`, `collage/` and owned tests | Day/Collage contracts, bundled art, injected clock | Render samples, seed/layout metadata, midnight/DST/race tests |
| Publication worker, if a slot is available | `publishing/` and fake/staging tests | PublishReceipt/path policy; no live writes | SMB behavior, atomic-replace/readback tests and target requirements |

Workers must not independently install packages globally or alter the dependency lock. Request a dependency change through the primary, who resolves it once. Shared-interface changes require coordination before dependent edits.

## Wave 2: evidence-dependent work

- Finish real crop selection before final local description/identity calibration.
- Complete identity acceptance decisions before a new dog's paid portrait job.
- The portrait worker can implement fake-transport behavior while D is incomplete, but actual paid smoke is primary-owned and gated.
- The publication worker can test an isolated SMB fixture while other modules evolve; production output remains primary-owned.
- Integrate C–F and run cross-module tests before any promotion to H.

A module compiling against mocks does not prove the actual dependency works. Resolve schema drift centrally, then rerun both sides.

## Wave 3: independent review

After integration, assign a reviewer who did not implement the relevant module to inspect:
1. Identity false merges, mutable accessories and cross-camera duplicate enrollment.
2. Duplicate paid requests, SDK retries, reservations and indeterminate outcomes.
3. Midnight generations, old-job publication, cache/SMB replacement and restart recovery.
4. Secret/private-media leakage and path/Git scope.
5. Missing requirement tests and overstated live evidence.

Review is read-only. Return severity, exact file/behavior, requirement ID, evidence and a concrete repair recommendation. No finding is resolved solely because the implementer says so. The primary applies fixes and re-runs relevant integrated checks. If a separate reviewer is unavailable, perform a documented fresh self-review and disclose that limitation.

## Wave 4: serial deployment and finalization

Only the primary executes H/I publication and service changes. Reviewers may inspect redacted evidence. Finish J after all worker changes are integrated and the final runtime tree is known. Do not let a documentation worker record predicted passing counts or future deployment as already observed.

## Task brief template

~~~text
Task:
Allowed files:
Read-only inputs:
Dependency/entry conditions:
Interfaces that must remain unchanged:
Required behaviors and requirement IDs:
Tests you must actually run:
Forbidden actions: shared files/Git state, production writes, paid calls,
credential changes, unrelated edits.
Return: changed paths, command/environment/results, evidence links, unresolved
risks, decisions/deviations and whether dependent work is safe to begin.
~~~

## Integration and interruption

Never overwrite a teammate's changes to simplify a merge. Inspect ownership conflicts, reconcile interfaces and preserve uncommitted user work. A worker's completion is not a phase pass until the primary tests the integrated result.

On a user stop, halt new assignments, safely stop active work, capture worker status and preserve a resumable checkpoint. On resumption, re-read the plan, current tree and latest instructions; do not restart discovery or repeat paid operations blindly.

