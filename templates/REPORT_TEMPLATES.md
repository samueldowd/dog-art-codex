# Implementation report templates

These records belong to the **future implementation**, not the documentation-authoring result. Initial statuses are NOT STARTED / NOT RUN. Do not fill them with predicted success, fabricated commands or secrets.

## docs/PREFLIGHT.md

- Timestamp, executing host and available tools:
- Applicable instruction/skill paths actually read:
- Target identity, CT112 state and verified SSH/Proxmox route:
- OS/Python/resources/paths/service-user observations:
- Git repository/branch/baseline/user-change inventory:
- Frigate camera-ID mapping and read-only auth:
- Ollama URL/exact model/capability:
- OpenAI model capability, credential presence and budget readiness:
- SMB mapping/owned filename/permission readiness:
- Browser/dashboard access and refresh unknowns:
- Private fixture availability:
- Selected build/app TOML paths; secrets presence only; `.env` Git/package exclusions:
- Missing inputs, restrictions and next safe action:

## docs/IMPLEMENTATION_DECISIONS.md

### D-0001 — TITLE

- Date / phase / source revision:
- Requirement(s):
- Classification: routine reversible / material / critical awaiting authorization
- Evidence and constraint:
- Alternatives considered:
- Chosen action and reason:
- Effect on behavior, privacy, cost, compatibility and operations:
- Validation / rollback:
- Authorization reference when required:
- Follow-up:

## docs/BLOCKERS.md

### B-0001 — TITLE

- Status: OPEN / WAITING FOR INPUT / RESOLVED
- First seen / last updated / phase:
- Blocked requirement(s) and action:
- Observed evidence, with sensitive fields removed:
- Reasonable recovery attempts and outcomes:
- Independent work continuing:
- Concrete prepared alternative or smallest decision:
- Exact input/access/approval required and why:
- Enforced approval rejection, if any: rejected action and stated reason
- Safe checkpoint / resumption command or action:
- Resolution evidence:

Do not repeatedly ask for the same resolved permission. If a skill or repository instruction explicitly requires approval, quote and link the exact instruction; distinguish that requirement from an engineering preference.

## docs/IMPLEMENTATION_VALIDATION.md

| Check | Requirement(s) | Layer | Source revision | Environment / versions | Command or visible action | Actual result | Evidence / timestamp |
|---|---|---|---|---|---|---|---|
| T01 | R01,R28 | OFFLINE | PENDING | PENDING | NOT RUN | NOT RUN | NONE |

Layers: OFFLINE, LOCAL_MODEL, LIVE_API, ON_TARGET, SMB_READBACK, DASHBOARD_VISUAL, NATURAL_MIDNIGHT or CONTROLLED_RESET. Use only applicable layers; do not mislabel mocks or still images as live evidence.

Valid result labels: PASS, FAIL, NOT RUN, BLOCKED, or NOT APPLICABLE with a specific justified requirement mapping. A required behavior cannot be made optional by choosing NOT APPLICABLE.

## docs/CHECKLIST.md

Create one row for **every R01–R34**; retain the original required behavior or an unambiguous link.

| ID | Implementation paths | Test/check IDs | Status | Evidence | Remaining gap / owner |
|---|---|---|---|---|---|
| R01 | NONE | NOT RUN | NOT STARTED | NONE | PENDING |

## Identity evaluation record

- Dataset and label provenance; independent event/camera/day counts:
- Enrollment/calibration/held-out split and leakage checks:
- Encoder/model/preprocessing versions and gallery policy:
- Match/new/margin thresholds and calibration method:
- Hard-negative false merges, return reuse, false splits, abstention:
- Low-light/PTZ/lookalike failure examples:
- Limits of the sample and honest confidence statement:
- Automatic matching enabled? Evidence/decision:
- Unresolved observations and correction/merge/split audit:

## Image-quality and publication record

- Identity/portrait revision and real evidence used locally:
- Prompt version, cloud model/settings, generated style reference hash:
- Real camera crop uploaded? Explicit authorization reference if yes:
- Paid ledger request status, estimate and actual available usage:
- PNG dimensions/alpha/core silhouette and matte review:
- Coat/pose/anatomy/style observations:
- Collage day/generation/revision, memberships, seed, input/output hashes:
- SMB server/share/subdirectory mapping and remote readback:
- Dashboard URL/view/card, observed refresh interval and screenshot:
- Existing unrelated slideshow files preserved:

## Reset acceptance record

- Mode: controlled_on_target / natural_midnight
- Application timezone, installed timer next-fire and clock/DST tests:
- Isolated on-target state test:
- Owned-image blank publication hash and visible result:
- Production current-day state preserved:
- Current valid image restored / naturally updated:
- Stale-job/outbox race tests:
- Archive/catalog before-and-after evidence:
- Limitations, publication lag and follow-up:

## docs/DELIVERY_RECEIPT.md

- Overall result: COMPLETE / IN PROGRESS / OFFLINE COMPLETE; LIVE BLOCKED / BLOCKED
- Requirements satisfied and unsatisfied:
- Source repository, branch, baseline, final commit:
- Final integrated test revision and status:
- Application version, artifact name/SHA256 and dependency lock:
- Exact installed revision/release path and service user:
- Service/reset-timer status and next scheduled reset:
- Frigate version/camera mapping; Ollama/encoder model versions:
- OpenAI configured model; no secret values:
- Build/app config paths and non-secret fingerprints; secrets-file source/presence only:
- Paid build calls/spend and unresolved ledger entries:
- Calibration/evaluation result and automatic identity mode:
- Published filename/day/revision/SHA256 and remote readback:
- Actual dashboard and reset acceptance modes/evidence:
- Backup/rollback evidence and operator commands:
- Decision/deviation list and open blockers:
- Required operator action and safe resume instructions:

