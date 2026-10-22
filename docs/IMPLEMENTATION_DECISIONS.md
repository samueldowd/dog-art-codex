# Implementation decisions

- D001 (2026-10-22, A, primary): User explicitly clarified CT112 is hostname and ID is 110. Use direct configured ct112 SSH; fallback must use pct exec **110**. Earlier brief examples of 112 are superseded only for numeric container ID. Evidence: human message and live hostname/root volume.
- D002 (A): Preserve user non-secret settings, normalize numeric/boolean TOML types without changing values. Missing/unsupported features block their stage, not offline commands. No credential values enter reports.
- D003 (A): Archive retention 180 is recorded but no destructive automatic retention implemented; permanent storage preservation governs until separately authorized deletion.
- D004 (B): Native Python >=3.11, standard-library SQLite, explicit transport injection and offline network denial; package selected assets with runtime, omit build config and secrets.

- D005 (A): Read-only Frigate 0.18 API on configured port 5000 accepted requests without credentials (internal unauthenticated route); explicitly select none for that verified route, while server auth itself remains enabled. Verified selected IDs backyard_east/driveway_ptz. Backyard East tracks only deer/bird: requested narrow human authorization before adding dog.
- D006 (A): Configured llama3.2-vision absent from live tags. No model substitution/download; human choice requested. CT112 has no CUDA device, so encoder backend must be verified before activation.
