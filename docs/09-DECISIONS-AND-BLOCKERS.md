# Autonomous decisions, critical blockers and continuation

## Routine decisions: make them, record material ones, continue

The future builder is authorized to choose reversible implementation details that preserve requirements: module names, supported compatible dependencies, schema layout, Python toolchain, test organization, file naming within the owned scope, retry mechanics, local image encoder selection within verified resource/license bounds, layout algorithms and equivalent read-only Frigate ingest routes.

A material decision record must contain:
- Stable ID, timestamp, phase and author/agent.
- Question, known facts and assumptions.
- Decision, alternatives considered and rationale tied to requirements.
- Scope/privacy/cost/compatibility effects and reversibility.
- Changed files/config/version, validating evidence and any follow-up/supersession.

Not every formatting change needs a record. The log explains decisions already made; it is not a queue of routine approval requests.

## Critical decision and blocker matrix

| Situation | Continue independently | Required interruption / limit |
|---|---|---|
| Direct CT112 SSH fails | Verify `proxmox-host` and running `pct exec 112` route; continue offline modules. | Missing essential access after valid fallback needs narrow access/auth input. |
| CT112 is stopped or absent | Continue offline implementation and prepare target findings. | Ask before starting/recreating/moving it; do not act on a guessed target. |
| SSH host key changed/unknown | Prepare verification details and other work. | Obtain trusted identity verification; never bypass checks. |
| LXC cannot mount CIFS | Use supported application-level SMB or a verified existing mount. | Changes to privilege, AppArmor, nesting, host mounts or network are separate authority. |
| Missing service credential/MFA | Build/test fake adapters and nondependent modules. | Request secure provisioning/login; no secret extraction or guessed credentials. |
| Ollama tag missing/unsupported | Query permitted model metadata, build adapter/tests and report capability findings. | Exact model substitution/cloud vision/new major model infrastructure needs explicit scope. |
| No calibrated identity thresholds/data | Implement gallery/review/shadow mode and evaluate available independent data. | Do not enable unverified auto-merging or claim empirical returning-dog success; request labels/examples if essential. |
| Similar-looking dogs cannot be distinguished | Retain uncertainty and useful evidence. | Do not force identity; request correction or better evidence where required. |
| API key/model/budget absent | Finish offline/local work and paid-request guards. | No paid submission until numeric authority and access exist. |
| Paid response outcome indeterminate | Persist state, inspect verified retrieval/usage evidence and do other work. | Do not blindly resend; request explicit retry/spend decision if uncertainty cannot be resolved. |
| Requested setting exceeds budget/resource bound | Optimize within the approved envelope. | New spending, oversized downloads or infrastructure allocation needs a concrete decision. |
| Camera recording/dog detection absent | Prepare the smallest Frigate configuration proposal. | Ask before changing production recording/detection/model settings. |
| Dashboard cache prevents visible updates | Verify card behavior and prepare a minimal reviewable change. | Ask for any necessary HA configuration scope; no redesign/storage edits. |
| Required Computer Use/browser unavailable | Try supported permitted alternatives and complete other evidence. | Report visible acceptance blocked; do not fabricate screenshots or deploy remote-control workarounds. |
| New remote repo/visibility/owner unclear | Continue local Git checkpoints. | Ask before external creation/publication or a private/public choice. |
| Existing user changes overlap | Inspect/reconcile within scope and preserve staging state. | Ask only if intent cannot be reconciled responsibly; never discard work. |
| Low disk or collage density cannot meet requirements | Preserve data/output and document measured constraints. | Archive deletion, member omission or new pagination/retention scope needs a decision. |
| Required test fails with plausible repairs | Diagnose, repair, rerun affected tests and record it. | Not a reason to ask for stage sign-off or stop early. |
| Enforced sandbox/approval denial | Try an honestly safer authorized route; keep unaffected work moving. | Do not bypass the control. If still blocked, state the rejected action, actual reviewer reason and needed authorization. |
| User explicitly stops/pauses | Save state/evidence/checkpoint and stop new side effects. | Follow the stop; do not continue deployment or paid work. |

## Critical-blocker procedure

1. Identify the exact failed operation/requirement and practical impact.
2. Capture redacted evidence and the actual access/error context.
3. Try materially different plausible safe remedies. Do not repeat the same failure indefinitely or treat a fixed retry count as permission to abandon useful progress.
4. Complete independent work and preserve a resumable Git/state checkpoint.
5. Ask a concise question with concrete viable options, a recommendation, and the precise input/action needed.
6. Keep dependent work stopped until the required answer/authorization arrives. Elapsed time is not consent.
7. Resume from recorded state after the answer; do not replay paid actions or restart the whole project blindly.
8. If no safe meaningful progress remains, report blocked accurately with source/artifact locations and remaining checks.

When approval is required by a specific instruction, skill or automatic review, name the source and quote/summarize the actual restriction. Do not invent a policy-based approval gate for a reversible routine action.

## Evidence discipline

- A retry scheduled is not recovery observed.
- A Git commit is not a test pass.
- A successfully copied image is not a dashboard observation.
- A structured JSON description is not ground-truth identity.
- A generated portrait is not a real-image identity reference.
- Offline/fake-transport tests are not a natural live event.
- A configured timer is not proof of its reset action.
- A subagent report is not proof of the integrated tree.
- A planned command or example path is not an installed feature.

These distinctions govern reporting, not excuses to leave feasible work unfinished. Gather the missing evidence or explicitly preserve the blocker.

## Continuation and context loss

Maintain an immediately usable next-step section with:
- Current branch/tree, changed paths and last tested/deployed artifact.
- Active/completed agent tasks and ownership.
- Remaining phase/requirement items and exact commands/data needed.
- Paid-request ledger state, reserved budgets and indeterminate submissions.
- Current day/generation/outbox state and production feature-enable flags.
- Pending user questions and boundaries on dependent work.

After compaction, interruption or a fresh session, read that record and current Git/service state before taking side effects. The latest user steering modifies the existing objective unless it clearly cancels/replaces it. Never reinterpret context loss as permission to mark the work complete.

