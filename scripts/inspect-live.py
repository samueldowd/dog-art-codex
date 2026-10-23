"""Read-only aggregate installed-live report. No credentials or private source payloads."""

import collections
import json
import os
import re
import sqlite3
import subprocess
import tomllib
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

assert os.geteuid() == 0 and os.uname().nodename == "CT112"
s = tomllib.loads(Path("/etc/dog-art/app.toml").read_text())
root = Path(s["APP_DATA_ROOT"])
p = root / "catalog.sqlite"
assert root == Path("/var/lib/dog-art") and not p.is_symlink()
db = sqlite3.connect(p.as_uri() + "?mode=ro", uri=True)
db.row_factory = sqlite3.Row
db.execute("PRAGMA query_only=ON")
db.execute("BEGIN")
day = datetime.now(ZoneInfo(s["DAY_TIMEZONE"])).date().isoformat()


def rows(sql, args=()):
    return [dict(r) for r in db.execute(sql, args)]


def label(v):
    return (
        v
        if isinstance(v, str) and re.fullmatch(r"[A-Za-z0-9_.:-]{1,100}", v)
        else ("none" if v is None else "other")
    )


r = {
    "read_utc": datetime.now(UTC).isoformat(),
    "day": day,
    "policy": {
        k: s.get(k)
        for k in (
            "OPENAI_GENERATION_ENABLED",
            "PUBLISH_ENABLED",
            "OPENAI_DAILY_BUDGET_USD",
            "OPENAI_MAX_CALLS_PER_DAY",
            "OPENAI_PORTRAIT_RESERVATION_USD",
            "IDENTITY_MODE",
            "PORTRAIT_REVIEW_MODE",
        )
    },
    "jobs": rows(
        "SELECT kind,state,error_code,count(*) AS count,min(attempts) AS min_attempts,max(attempts) AS max_attempts FROM jobs GROUP BY kind,state,error_code"
    ),
    "portraits": rows(
        "SELECT state,error_code,count(*) AS count FROM portraits GROUP BY state,error_code"
    ),
    "requests_today": rows(
        "SELECT state,count(*) AS calls,sum(reserved_usd) AS reserved_usd FROM requests WHERE day=? GROUP BY state",
        (day,),
    ),
    "build_reservation_today": db.execute(
        "SELECT coalesce(sum(reserved_usd),0) FROM requests WHERE day=? AND scope IS NOT NULL",
        (day,),
    ).fetchone()[0],
    "members": db.execute("SELECT count(*) FROM membership WHERE day=?", (day,)).fetchone()[0],
    "members_with_validated_art": db.execute(
        "SELECT count(*) FROM membership m WHERE m.day=? AND EXISTS(SELECT 1 FROM portraits p WHERE p.dog_id=m.dog_id AND p.state='validated')",
        (day,),
    ).fetchone()[0],
    "outbox": rows("SELECT revision,state FROM outbox WHERE day=? ORDER BY revision", (day,)),
    "qa": [],
}
for group in ("jobs", "portraits"):
    for row in r[group]:
        for k in ("kind", "state", "error_code"):
            if k in row:
                row[k] = label(row[k])
for a in db.execute(
    "SELECT created_at,payload FROM audit WHERE code='portrait_local_review' ORDER BY created_at DESC LIMIT 12"
):
    v = json.loads(a["payload"])
    checks = v.get("evidence", {}).get("checks", {})
    r["qa"].append(
        {
            "utc": datetime.fromtimestamp(a["created_at"], UTC).isoformat(),
            "decision": label(v.get("decision")),
            "review_status": label(v.get("review_status")),
            "retryable": v.get("retryable") is True,
            "checks": {
                k: checks.get(k)
                for k in (
                    "one_dog",
                    "complete_anatomy",
                    "no_extras",
                    "style_matches",
                    "confirmed_facts_match",
                    "clean_exterior",
                )
            },
            "reason_count": len(v.get("evidence", {}).get("reasons", [])),
        }
    )
last = db.execute("SELECT payload FROM publications ORDER BY created_at DESC LIMIT 1").fetchone()
if last:
    v = json.loads(last[0])
    r["last_publication"] = {
        k: v.get(k) for k in ("day", "revision", "sha256", "state", "verified_at")
    }
db.close()
# Only aggregate application error codes, never raw journal text or HTTP/SDK output.
j = subprocess.run(
    [
        "journalctl",
        "-u",
        "dog-art.service",
        "--since",
        "15 minutes ago",
        "-n",
        "150",
        "--no-pager",
        "-o",
        "cat",
    ],
    capture_output=True,
    text=True,
    timeout=10,
)
c = collections.Counter()
for line in j.stdout.splitlines():
    try:
        v = json.loads(line)
    except (ValueError, TypeError):
        continue
    if isinstance(v, dict) and "code" in v:
        c[(label(v.get("stage")), label(v.get("kind")), label(v["code"]))] += 1
r["journal_error_counts"] = [
    {"stage": a, "kind": b, "code": c0, "count": n} for (a, b, c0), n in c.items()
]
print(json.dumps(r, indent=2))
