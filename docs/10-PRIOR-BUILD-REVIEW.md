# Review of the actual Formula Pro kickoff document

## Exact source and why it is the correct reference

The reviewed source is [docs/BUILD_SPEC.md at a pinned repository revision](https://github.com/samueldowd/fpa/blob/f418e53cc700e65f2c5351f8f5c11a935ad46de0/docs/BUILD_SPEC.md), titled **Formula Pro Advanced WiFi: autonomous build instructions for Codex**.

- Reviewed repository revision: `f418e53cc700e65f2c5351f8f5c11a935ad46de0`.
- File blob: `9f900fa13f5e5f5b3a7eccbd659c08c3ea22b3c9`.
- Repository inventory reported 112,670 bytes; fetched text contained 770 lines.
- The file was introduced by commit [e785976983c71e69f7aca470f2f46b1b9fd231db](https://github.com/samueldowd/fpa/commit/e785976983c71e69f7aca470f2f46b1b9fd231db), “Establish build contract and sanitized offline regression harness,” timestamp 2026-10-20T03:09:19Z.
- Its opening and final execution directive instruct Codex to implement, validate and continue, rather than merely propose a plan.
- Its numbered S01–S15 requirements and A–F stages map to the later [implementation validation report](https://github.com/samueldowd/fpa/blob/f418e53cc700e65f2c5351f8f5c11a935ad46de0/docs/IMPLEMENTATION_VALIDATION.md).

This is different from the later user guide/README, the validation write-up, and the app's separate “Set up fpa” environment setup thread. The build specification is the primary reference; the validation report is supporting evidence about how that contract was executed.

## What worked and is retained

| Pattern in the original | Why it helps | Adaptation here |
|---|---|---|
| Explicit implementation directive at both entry and handoff | Prevents ending with another plan. | Future launch prompt plus activation boundary that does not trigger a build during document authoring. |
| User-accepted requirements labeled separately from engineering choices | Keeps the agent from changing the target while solving implementation details. | R01–R34 matrix, known/default/discover labels and blank unknown values. |
| Pinned source/input provenance | Gives a reproducible starting point. | Source SHA, source review, asset manifest, fixture provenance and model/config version receipts. |
| Detailed state/lifecycle/concurrency semantics | Makes race conditions part of the requirement rather than post-hoc bugs. | Queue leases, event/portrait uniqueness, cross-camera identity, day generations, publication ordering and midnight barriers. |
| Dependency-ordered stages with automatic exit checks | Supports autonomous progress without stage-by-stage approval. | A–J phases, explicit wave barriers, primary-owned integration checks. |
| Delegation contracts with file ownership and evidence returns | Reduces conflicting edits and unsupported completion claims. | Named role briefs, primary-only shared files/Git/deployment/spending, integrated independent review. |
| Material decision log and recovery policy | Allows routine judgment while preserving reasoning. | Reversible decisions, critical-action matrix, blockers with exact resumption input. |
| Versioned checkpoints and tested-tree evidence | Separates progress from correctness. | Base/tested/final/deployed revisions, artifact hash and evidence freshness. |
| Definition of done and full requirement mapping | Makes missing features and unrun tests visible. | Offline/local-model/live/visual evidence categories with required deployment gates. |
| Sanitized fixtures and privacy tests | Avoids committing private user inputs. | Private camera fixtures ignored, redacted evidence and opt-in real-camera crop uploads. |
| Fresh-install/artifact/docs checks | Tests the deliverable the next person will actually use. | Fresh CT112 install path, release/wheel provenance, operator commands, rollback and documentation QA. |

## Changes needed for this project's scope

1. **Deployment is part of the target.** The FPA specification deliberately defined success as an offline validated integration and excluded live appliance/production deployment. This project requires CT112 operation, real service access, Samba delivery and a visible existing dashboard. Offline success cannot replace those gates.
2. **Credentials and paid execution are central dependencies.** Define preflight, numeric budgets, protected inputs and safe continuation when a secret or network permission is missing.
3. **Identity matching needs a measured abstention policy.** Text descriptions or similar coat colors do not reliably identify a returning dog. Require independent-event labels, local visual features and hard negatives.
4. **Calendar state and artwork lifetime differ.** Clear today's display without deleting identities or archived collages; block stale prior-day jobs from publishing.
5. **Cross-host paths require explicit mapping.** User-friendly camera names, SMB shares, CT112 paths and Windows attachment paths are not interchangeable.
6. **Document length should not depend on automatic instruction loading.** Keep a short root AGENTS router and explicit module read order. A long build spec is useful when read deliberately; it should not be stuffed into automatically loaded instructions.
7. **Production Computer Use is an evidence dependency.** Prepare the browser and login flow, identify actual tools and distinguish UI proof from filesystem proof.
8. **Collage changes are deterministic Python operations.** Preserve the individual generated portraits and use local composition, avoiding repeated paid re-generation of a whole growing collage.

## What was not copied

No appliance commands, feeding/device assumptions, original account data, HACS scope, FPA repository destination, HA compatibility matrix or original completion exclusions are requirements for Dog Art. The prior document's execution policy is useful reference material, not authority to act on this project's systems.

## Research boundary

Official Codex guidance was used to check instruction discovery, delegation boundaries and durable planning practices. Those sources support general practices; the concrete Dog Art requirements, paths, phases and acceptance criteria in this package are derived from the current user's request and project-specific engineering decisions.

