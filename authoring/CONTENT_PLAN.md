# Content plan and authoring record

## Purpose

Produce a portable Markdown execution specification, not application code. The future builder must be able to start with this package, establish verified access, implement in dependency order, and demonstrate the requested live result without inventing requirements or relying on earlier chat memory.

## Inputs reviewed

- Current user requests and five clarification answers.
- Follow-up request to separate a single ignored secrets `.env`, build configuration and runtime application configuration.
- The actual Formula Pro kickoff specification at `samueldowd/fpa`, pinned revision `f418e53cc700e65f2c5351f8f5c11a935ad46de0`, `docs/BUILD_SPEC.md`, blob `9f900fa13f5e5f5b3a7eccbd659c08c3ea22b3c9`.
- Its initial provenance: introduced in `e785976983c71e69f7aca470f2f46b1b9fd231db`, “Establish build contract and sanitized offline regression harness,” 2026-10-20 UTC.
- Its validation report as supporting outcome evidence, distinguished from the kickoff specification.
- Current official Codex, OpenAI image, Ollama, Frigate, systemd and Python SMB documentation listed in docs/11.
- Existing artwork, source-video locations and extraction scripts from this workspace.

The earlier “Set up fpa” app thread was a separate setup task. It was not used as a substitute for the original build spec. Its historical empty-repository observation was superseded by live repository reads; it must not be represented as the current repository state.

## Design choices for the new document

1. Separate accepted facts, proposed defaults and unresolved values.
2. Keep a short brief plus explicit mandatory modules and a concise AGENTS template.
3. Make phase entry/exit criteria operational and evidence-based.
4. Establish schemas/config/queue contracts before parallel workers.
5. Separate routine agent decisions from critical blockers and preserve independent progress.
6. Require real CT112/SMB/dashboard evidence, unlike the older offline-only delivery boundary.
7. Preserve long-term identities while resetting only today's display.
8. Treat ambiguous matching, after-midnight jobs, duplicate API calls and SMB stale writes as first-class requirements.
9. Default sensitive unknowns to blank and cloud camera-image uploads to disabled.
10. Use native Python/systemd and application-level SMB to avoid unnecessary container-security changes.
11. Deliver a portable reference-asset inventory without bundling private camera recordings.
12. Validate the document package itself: links, variable definitions, blank secrets, required topics, artifact hashes and a specification consistency review.

## Planned document responsibilities

- README: how to use the kit and exact future launch prompt.
- Brief: project authority, hard requirements, boundaries and completion.
- Requirements: numbered behaviors mapped to phases/evidence.
- Preflight: SSH, Git, permissions, network, Computer Use and fallback routes.
- Configuration: separate build/app TOML, one ignored secrets `.env`, a blank tracked secret template and per-key provenance.
- Architecture: modules, state machines and concurrency/time contracts.
- Phases: ordered build waves and delegation ownership.
- Tests: deterministic, replay, live and visual acceptance.
- Operations: native deployment, daily rollover, retry, archival and rollback.
- Git/docs: checkpointing, release provenance, operator/developer handoff.
- Blockers: scoped autonomy, escalation and resumability.
- Source review: what was learned from the actual initiating build doc.
- Sources/assets: exact provenance and portable/nonportable inputs.

## Authoring boundary

No SSH connections to production, live service changes, repository pushes, API image-generation calls, Frigate/HA changes, or pipeline installation are authorized by this authoring task. Local file reads, source/documentation retrieval, document creation, asset copying and document QA are in scope.

This authoring record describes documentation work. Implementation-phase checklists must remain unchecked until a future implementation actually produces evidence.

