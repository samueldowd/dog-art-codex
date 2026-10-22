# Dog Art Pipeline: autonomous Codex build package

**Document version:** 1.1.0  
**Prepared:** 2026-10-22, America/New_York  
**Current delivery:** documentation and reference assets only. No pipeline has been installed, connected, or deployed.

This package is an execution specification for a future Codex build. It is designed to work from a fresh chat without requiring the earlier conversation.

## Start here

1. Read [CODEX_BUILD_BRIEF.md](CODEX_BUILD_BRIEF.md), the authoritative scope and execution contract.
2. Complete or discover non-secret startup/deployment values in [config/build.toml](config/build.toml), and runtime values in [config/app.toml](config/app.toml), using [configuration guidance](docs/03-CONFIGURATION.md). Copy [config/.env.example](config/.env.example) to `config/.env` only if it does not already exist, then supply secrets securely. The real `.env` is ignored by Git and excluded from the ZIP.
3. Give Codex the entire extracted package, not just this README. Make the intended implementation repository and SSH/network tools available.
4. Paste the launch prompt below only when you actually want implementation to begin.

The package is ready for requirements-driven implementation. Live work remains subject to verified access, configured credentials, spending limits, and the critical-decision policy.

## Launch prompt

~~~text
Implement the Dog Art Pipeline described in CODEX_BUILD_BRIEF.md and its linked
modules. This message authorizes the future build within that specification's
scope and permission boundaries; it is not a request for another plan.

Read the brief and mandatory modules before editing. Discover and validate
build/app settings and the separate secrets file without exposing credentials.
Keep build-only keys out of app startup and keep real .env files out of Git and
release artifacts. Use SSH to CT112 when available;
otherwise use the existing SSH connection to proxmox-host and pct exec 112 for
container-local work after verifying the container is running and is the target.

Create and maintain a living implementation plan, a requirement/evidence matrix,
a decision log, a blocker log, and Git checkpoints. Explicitly use internal
subagents with the sequencing and file ownership described in
docs/05-PHASES-AND-DELEGATION.md. If subagent tools are unavailable, perform the
same work sequentially and document the limitation; do not create other chats.

Proceed autonomously through routine engineering decisions and passing stage
gates. Repair recoverable failures and continue. Interrupt me for critical
decisions, missing essential access or secrets, exceeded spending authority,
irreducible identity/quality ambiguity, or an enforced approval rejection that
has no safe authorized alternative. Continue independent work while waiting.
Do not fabricate values, weaken tests, bypass access controls, or declare an
unperformed live check passed.

Implement and verify the entire scoped result: native Python on Debian CT112,
Frigate dog events from Backyard East and Driveway PTZ, local Ollama descriptions
and returning-dog matching, OpenAI watercolor portraits, local 1920x1080 cream
collages of today's distinct dogs, Samba publication into media/kitchen-tv,
midnight clearing, persistent identity/artwork/archive storage, operational
documentation, reproducible versioned delivery, and the real dashboard check.

Do not stop at an offline prototype if required live gates remain. If a critical
blocker prevents completion, preserve a resumable checkpoint and report exactly
what is complete, what is blocked, the evidence, recovery attempts, and the input
needed. Respect any later instruction from me to stop or change scope.
~~~  

## Read order

| Order | File | Purpose |
|---|---|---|
| 1 | [CODEX_BUILD_BRIEF.md](CODEX_BUILD_BRIEF.md) | Scope, authority, mandatory behavior, completion contract |
| 2 | [01-REQUIREMENTS.md](docs/01-REQUIREMENTS.md) | Accepted requirements and measurable evidence |
| 3 | [02-PREFLIGHT-AND-ACCESS.md](docs/02-PREFLIGHT-AND-ACCESS.md) | SSH, Proxmox fallback, Git, permissions, network, Computer Use |
| 4 | [03-CONFIGURATION.md](docs/03-CONFIGURATION.md) | Variable catalog, provenance, blanks, startup validation |
| 5 | [04-ARCHITECTURE-AND-CONTRACTS.md](docs/04-ARCHITECTURE-AND-CONTRACTS.md) | Modules, state, matching, concurrency, output contracts |
| 6 | [05-PHASES-AND-DELEGATION.md](docs/05-PHASES-AND-DELEGATION.md) | Dependency-ordered phases and agent assignments |
| 7 | [06-TESTING-AND-ACCEPTANCE.md](docs/06-TESTING-AND-ACCEPTANCE.md) | Required tests, live evidence, quality and recognition evaluation |
| 8 | [07-DEPLOYMENT-AND-OPERATIONS.md](docs/07-DEPLOYMENT-AND-OPERATIONS.md) | Native services, publishing, recovery, reset, rollback |
| 9 | [08-GIT-DOCUMENTATION-AND-HANDOFF.md](docs/08-GIT-DOCUMENTATION-AND-HANDOFF.md) | Versioning, modular finished docs, reproducible artifact and receipt |
| 10 | [09-DECISIONS-AND-BLOCKERS.md](docs/09-DECISIONS-AND-BLOCKERS.md) | Autonomous decisions, escalation, resumability |
| Reference | [10-PRIOR-BUILD-REVIEW.md](docs/10-PRIOR-BUILD-REVIEW.md) | Review of the actual Formula Pro kickoff spec and lessons applied |
| Reference | [11-SOURCES.md](docs/11-SOURCES.md) | Official documentation and source provenance |
| Reference | [12-INPUT-ASSETS.md](docs/12-INPUT-ASSETS.md) | Existing scripts, five videos, generated artwork, staging rules |

## Templates and portability

- [config/build.toml](config/build.toml): non-secret build, SSH/Git, deployment and acceptance settings.
- [config/app.toml](config/app.toml): non-secret runtime cameras, models, budgets, collage, reset and publication settings.
- [config/.env.example](config/.env.example): blank secrets template for the single ignored `config/.env`; never overwrite an existing secrets file.
- [.gitignore](.gitignore): excludes real `.env` files and backups while retaining the blank example.
- [templates/AGENTS.md.template](templates/AGENTS.md.template): short instruction router for the future implementation repository.
- [templates/IMPLEMENTATION_PLAN.md](templates/IMPLEMENTATION_PLAN.md): implementation-only progress template, initially unchecked.
- [templates/REPORT_TEMPLATES.md](templates/REPORT_TEMPLATES.md): decisions, blockers, validation and delivery records.
- [authoring/CONTENT_PLAN.md](authoring/CONTENT_PLAN.md): how this document was planned and reviewed.
- [authoring/DOCUMENT_QA.md](authoring/DOCUMENT_QA.md): actual documentation checks and their limits.
- `assets/`: existing generated artwork for style and visual comparison, not identity-training truth.
- `ASSET_MANIFEST.json` and `SHA256SUMS`: portable inventory and integrity checks, generated after document QA.

The source videos contain private camera footage and are not bundled. Their known source locations are documented for optional, explicitly scoped staging into ignored private fixtures during the future build. A missing attachment path must be reported, not assumed accessible from CT112.

## Verify the package

The sibling delivery receipt records the ZIP hash. After extracting the ZIP, run the following from the extracted `dog-art-codex-build` directory on Linux to verify its files:

~~~sh
sha256sum -c SHA256SUMS
~~~

On Windows, `Get-FileHash -Algorithm SHA256` can check the ZIP against the receipt. Integrity checks validate delivered bytes; they do not activate or test the future pipeline.

This is not a HACS integration, Frigate modification, Home Assistant integration, or replacement slideshow. It is a separate Python service that publishes one owned image into the existing slideshow folder.

