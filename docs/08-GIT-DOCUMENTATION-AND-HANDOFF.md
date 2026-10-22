# Git versioning, modular documentation and delivery

## Repository scope

Use a dedicated Dog Art implementation repository. The Formula Pro repository is reference material only. Inspect actual Git root, branch/HEAD, staged and unstaged changes, untracked files and remotes before editing. Redact credential-bearing remote URLs.

Preserve existing user changes and history. Do not initialize Git in a broad parent directory, replace `.git`, silently stash work, reset to a clean tree, or commit unrelated files. An intentionally empty new project is valid.

Use existing verified Git author/signing configuration; do not invent identity, alter global config or bypass hooks/signing to make a commit succeed. Missing remote hosting does not prevent meaningful local versioning.

## Branches and checkpoints

Proposed implementation branch: `codex/dog-art-pipeline`, subject to actual repository conventions. Reuse an appropriate existing task branch safely.

The primary owns shared-checkout index/branch/commit operations. Subagents return changes and actual evidence; isolated worktrees are optional and must follow the host/app's worktree rules.

Make coherent checkpoints at B, integrated module milestones, G, installed release validation and final documentation. Smaller meaningful commits are welcome. Use explicit owned paths/hunks rather than indiscriminate `git add .`.

Before each commit:
- Inspect diff and staged scope.
- Verify no credentials, production environment file, private recordings/crops, local model cache, database or raw logs are included.
- Run relevant checks and record what was actually tested.
- Include tests/docs for behavior changes.
- Preserve unresolved WIP accurately rather than labeling it a validated release.

No force-push, destructive history rewrite, automatic default-branch merge, release publication or repository-visibility change. Remote policy defaults to `local_only`. If the future user explicitly configures/authorizes a verified target and `push_branch`, push the scoped branch and record actual remote/PR status. Do not claim a push or CI run from an intended command alone.

## Proposed ignore policy

The future repository must ignore the real `config/.env` and its backup variants, venvs, caches, model weights, private fixtures, raw clips/crops, production databases/WAL files, runtime archives and generated release output unless deliberately versioned. Track the blank `.env.example` plus non-secret `config/build.toml` and `config/app.toml`. Preserve these exclusions in application packaging independently of Git ignore behavior.

Keep sanitized synthetic fixtures, prompt/style templates, tests, docs, lock files, service definitions and selected nonprivate style assets under source control. Record asset licenses/provenance. Production generated portraits and household galleries stay in application storage unless the user explicitly chooses otherwise.

## Source, artifact and deployed versions

Distinguish:
- **Base revision:** initial source state.
- **Tested revision/tree:** exact runtime source and dependency/config/model combination validated.
- **Final repository revision:** may include later documentation-only evidence updates.
- **Artifact hash:** actual wheel/release archive bytes installed.
- **Deployed revision:** what CT112 is actually running.
- **Published revision/hash:** what the HA SMB file actually contains.

A later code change invalidates affected earlier evidence. A docs-only report commit must identify the runtime revision tested. Do not make self-referential commit-hash claims; write a final delivery receipt after the final commit or keep the receipt outside the hashed artifact.

Use a deliberate application version such as an initial `0.1.0` release, with semantic versioning for supported behavior, migrations and operator compatibility. This document package's `1.1.0` version is independent of the future application version.

## Finished documentation modules

The implementation must deliver accurate documentation for what exists:

| Finished document | Required content |
|---|---|
| Root `README.md` | Purpose, examples, architecture overview, supported behavior, quick start, prerequisites and links to detailed guides. |
| `docs/INSTALLATION.md` | Actual Debian/Python dependency setup, native venv/release deployment, direct SSH and Proxmox fallback, service/timer verification. |
| `docs/CONFIGURATION.md` | Every key/default/type/required stage and owning file; build/app TOML separation, ignored secrets `.env`, provisioning, loading/precedence, camera IDs, models, budgets and validation. |
| `docs/OPERATOR_GUIDE.md` | Status/review/correction, today's dogs, archive locations, manual rebuild, reset behavior, common commands and recovery. |
| `docs/ARCHITECTURE.md` | Implemented module boundaries, records/state diagrams, transactions, queues, identity and concurrency/time contracts. |
| `docs/PRIVACY_AND_COST.md` | Actual local/cloud data flow, upload opt-in, retained data, redaction, request accounting, cap behavior and limitations. |
| `docs/TROUBLESHOOTING.md` | Symptoms, diagnostic commands, safe remedies, model/media/SMB/dashboard issues and exact escalation information. |
| `docs/RECOVERY_AND_ROLLBACK.md` | Supported backup/restore, schema compatibility, release rollback and reset/publication reconciliation. |
| `docs/DEVELOPMENT.md` | Toolchain, tests, replay fixtures, model calibration, interfaces, code ownership, release/CI and version policy. |
| `docs/IMPLEMENTATION_PLAN.md` | Live progress, discoveries, decisions, outcomes and exact continuation state. |
| `docs/IMPLEMENTATION_DECISIONS.md` | Stable decision records with alternatives/rationale/evidence/reversibility. |
| `docs/IMPLEMENTATION_VALIDATION.md` | Per-phase and per-requirement actual results, source/env/revision, failures/corrections and live evidence boundaries. |
| `docs/BLOCKERS.md` | Active/resolved critical items, attempts, impact, owner/input and resumption step. |
| `docs/CHECKLIST.md` | Every R01–R34 requirement and applicable T01–T36 test with current status and evidence. |
| `CHANGELOG.md` | User-visible changes, migrations, behavior/version/model compatibility and known limitations. |

Update documents with implementation decisions; this build specification is not a substitute for finished operator documentation. Validate internal links, commands, examples and a fresh-setup walkthrough. Do not leave invented badges, compatibility promises or unfinished template text in a claimed finished release.

## Reproducible release

Build an installable package/release with:
- Pinned dependency versions, build commands and runtime version receipt.
- Exact source revision and selected model/style/preprocessing versions.
- Runtime code, required nonprivate assets, service templates and example config.
- No production secret file, private media, database, model download cache or unrelated outputs.
- SHA-256 manifest and fresh-directory install test.
- A documented deployment/rollback procedure matching the actual artifact.

Do not generate fake successful CI badges or claim cloud CI was executed if only local checks ran.

## Final handoff

The final report must link the release artifact, README/operator guide, validation report, decision log, blocker log if needed and delivery receipt. It must state:
- Repository, branch, base/tested/final revisions, final Git status and preserved unrelated changes.
- Actual target access route, installed/deployed version and service/timer state.
- Actual Frigate/camera/model mappings and redacted configuration readiness.
- Identity evaluation scope/errors/abstentions and limits.
- Actual API-call count/usage evidence and input privacy mode.
- Archive location, current local day, latest remote output/hash and observed dashboard refresh.
- Reset/recovery/rollback tests, distinguishing controlled exercises from natural observations.
- Completed mandatory criteria and any blocked/failed/not-run criteria.

If a required item is blocked, present a resumable checkpoint with its exact input/action request. Do not end with an overall complete claim or an offer to continue work that remains authorized and feasible.

