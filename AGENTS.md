# Dog Art implementation router

Read CODEX_BUILD_BRIEF.md and docs/01–12 before changing scope. Follow docs/IMPLEMENTATION_PLAN.md for continuation, docs/CONTRACTS.md for interfaces, docs/CHECKLIST.md for actual evidence, and docs/BLOCKERS.md for live gates.

User correction: CT112 is the hostname; the actual Proxmox container ID is **110**. Do not target ID 112.

Primary owns shared contracts, settings, storage/migrations, locks, Git, integration, live operations and paid requests. Internal workers own only assigned module/test paths. No worker may stage/commit, deploy, publish, access secrets or spend. Never print secrets. Real config/.env, recordings, crops, databases and model weights stay outside Git/releases. Runtime loads app TOML plus explicit secrets file, never build TOML. Preserve existing user settings and artwork. No archive deletion is implemented.

Do not claim offline tests establish live identity quality or dashboard acceptance. Keep all R01–R34/T01–T36 statuses truthful.
