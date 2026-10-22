# Troubleshooting

Start with `dog-art ... status --redact`, `doctor --mode offline --redact`, then explicitly selected read-only live doctor and `journalctl -u dog-art.service --since today`. Keep logs private; do not enable HTTP/SDK/SMB debug payloads or paste credentials.

| Symptom | Check and safe remedy |
|---|---|
| SSH works but installer cannot write | Dedicated chatgpt login retains password-protected sudo. Use normal interactive authentication for the scoped reviewed installer; do not change sudoers. Numeric container ID is110, hostnameCT112. |
| No selected dog events | Check actual camera IDs/dog tracking/recordings. Backyard East dog was added through a separately authorized targeted update and read back. Another camera remains excluded. Empty results are not proof of historical coverage. |
| New events rejected | Installed Frigate0.18 uses null legacy false_positive; parser accepts only verified object-type/score/clean-snapshot metadata, never explicit true/unknown malformed events. Check auth/media availability and finite exhausted-job codes. |
| Tiny or clipped crops | Detection snapshots were640×360; use native3840×2160 timestamped recording frames plus fresh detector boxes. Verify aspect/FOV/anchor timing. Do not reuse one box as PTZ moves or invent sharpened details. |
| Ollama absent/malformed | Exact qwen3-vl:4b digest/capabilities must match. No implicit pull/fallback. JSON unknowns/conflicts are retained. Schema/capability failure blocks only dependent jobs. |
| Everything needs identity review | Expected without independent visibility/identity calibration. Inspect real references/labels/lookalikes; do not lower thresholds or turn artwork into ground truth. |
| Paid portrait indeterminate | Inspect durable ledger/provider request evidence. Never resend blindly or delete the old record. A new bounded spend decision may be necessary. |
| Portrait saved but collage pending | Complete real visual approval, then check queued collage work/membership. Missing portraits preserve membership and prior valid output. `retry --dependencies` resumes resolved parked work without resetting attempts. |
| SMB offline/hung/open handle | Signed/encrypted session, total-deadline worker and safe replace preserve prior target where no replacement completed. Reconnect/read desired hash; never delete final image to make rename succeed. |
| File correct, dashboard stale | SMB readback is only publication proof. Check actual Wallpanel enumeration/recursive folders and120s cycle/cache. Request scope before any necessary dashboard change. |
| Midnight not reflected remotely | Check local day/generation, next timer, outbox and SMB lag. During outage local rollover persists; reconnect publishes the latest current day, not every historical revision. Never change system time for testing. |
| Low disk | Pause downloads/generation and report capacity. Retain catalog/artwork/archive and last valid output. User retains2048MiB floor; wait for space rather than silently reducing it. |
| Schema/model mismatch | Refuse incompatible comparisons/downgrades. Use compatible release/state backup; rebuild features only through an audited plan. |

Report exact error code, source/artifact/deployed revision, runtime/model versions, stage, target identity, last good output hash and reproduction steps. Label blocked/not-run live checks honestly.
