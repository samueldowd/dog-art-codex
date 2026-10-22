# Documentation package changelog

## 1.1.0 — 2026-10-22

- Split configuration into non-secret `config/build.toml`, non-secret `config/app.toml` and the single ignored `config/.env`, with a blank tracked `.env.example`.
- Added Git ignore rules and required archive/checksum exclusions for the real secrets file.
- Defined typed TOML placeholders, file ownership, strict loading, build/runtime spending boundaries and runtime independence from build config.
- Updated deployment paths, phases, tests, documentation and package validation. Retired the combined environment example and alternate credential-file settings; camera lists now use native TOML arrays.

## 1.0.0 — 2026-10-22

- Created the future autonomous-build contract and launch prompt.
- Reviewed the actual initiating Formula Pro Advanced specification at a pinned revision.
- Added traceable requirements, access/configuration guidance, dependency-ordered phases, delegation, tests, live acceptance and critical-blocker policy.
- Included known environment values, blank unknown/secrets, reference artwork, reusable-script reference text and report templates.
- Kept the delivery limited to documentation and existing assets; no pipeline, production connection, installation or deployment was performed.

Documentation package versions and future application versions are separate.

