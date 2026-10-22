"""Paid requests are reserved transactionally, never implicitly retried."""

import json
import math
import uuid


class BudgetError(ValueError):
    pass


class Ledger:
    def __init__(self, store):
        self.store = store

    def set_build_scope(self, scope, cap):
        if not scope or not math.isfinite(cap) or cap < 0:
            raise BudgetError("finite build cap required")
        with self.store.transaction() as db:
            existing = db.execute(
                "SELECT cap_usd FROM budget_scopes WHERE scope=?", (scope,)
            ).fetchone()
            if existing and existing[0] != cap:
                raise BudgetError("existing build scope cap is immutable")
            db.execute("INSERT OR IGNORE INTO budget_scopes VALUES(?,?)", (scope, cap))

    def reserve(
        self,
        recipe_key,
        dog_id,
        recipe,
        day,
        now,
        *,
        reserve_usd,
        daily_usd,
        daily_calls,
        concurrency=1,
        build_scope=None,
    ):
        numbers = (reserve_usd, daily_usd, daily_calls, concurrency)
        if any(type(x) not in (int, float) or not math.isfinite(x) or x <= 0 for x in numbers):
            raise BudgetError("finite positive numeric caps and reservation required")
        with self.store.transaction() as db:
            existing = db.execute(
                "SELECT * FROM requests WHERE recipe_key=?", (recipe_key,)
            ).fetchone()
            if existing:
                return dict(existing), False
            total, count = db.execute(
                "SELECT coalesce(sum(reserved_usd),0),count(*) FROM requests WHERE day=?", (day,)
            ).fetchone()
            if total + reserve_usd > daily_usd or count >= daily_calls:
                raise BudgetError("daily limit reached")
            active = db.execute(
                "SELECT count(*) FROM requests WHERE state IN ('reserved','submitting','indeterminate')"
            ).fetchone()[0]
            if active >= concurrency:
                raise BudgetError("request concurrency/indeterminate gate")
            if build_scope is not None:
                limit = db.execute(
                    "SELECT cap_usd FROM budget_scopes WHERE scope=?", (build_scope,)
                ).fetchone()
                used = db.execute(
                    "SELECT coalesce(sum(reserved_usd),0) FROM requests WHERE scope=?",
                    (build_scope,),
                ).fetchone()[0]
                if not limit or used + reserve_usd > limit[0]:
                    raise BudgetError("build scope limit reached or missing")
            rid = uuid.uuid4().hex
            db.execute(
                "INSERT INTO portraits(recipe_key,dog_id,recipe,state) VALUES(?,?,?,?)",
                (recipe_key, dog_id, json.dumps(recipe, sort_keys=True), "budget_reserved"),
            )
            db.execute(
                "INSERT INTO requests(request_id,recipe_key,day,scope,reserved_usd,state,created_at) VALUES(?,?,?,?,?,?,?)",
                (rid, recipe_key, day, build_scope, reserve_usd, "reserved", now),
            )
            return dict(
                db.execute("SELECT * FROM requests WHERE request_id=?", (rid,)).fetchone()
            ), True

    def transition(self, request_id, expected, state, *, remote_id=None, usage=None):
        allowed = {
            "reserved": {"submitting", "failed_before_submission"},
            "submitting": {"succeeded", "indeterminate", "rejected"},
            "succeeded": {"validated", "needs_review"},
            "indeterminate": set(),
            "validated": set(),
            "needs_review": {"validated"},
            "rejected": set(),
            "failed_before_submission": set(),
        }
        if state not in allowed.get(expected, set()):
            raise BudgetError("invalid request transition")
        with self.store.transaction() as db:
            changed = db.execute(
                "UPDATE requests SET state=?,remote_id=coalesce(?,remote_id),usage=coalesce(?,usage) WHERE request_id=? AND state=?",
                (
                    state,
                    remote_id,
                    json.dumps(usage) if usage is not None else None,
                    request_id,
                    expected,
                ),
            ).rowcount
            if changed != 1:
                raise BudgetError("request already transitioned")
            db.execute(
                "UPDATE portraits SET state=? WHERE recipe_key=(SELECT recipe_key FROM requests WHERE request_id=?)",
                (state, request_id),
            )

    def recover(self):
        with self.store.transaction() as db:
            db.execute(
                "UPDATE portraits SET state='indeterminate' WHERE recipe_key IN (SELECT recipe_key FROM requests WHERE state='submitting')"
            )
            db.execute("UPDATE requests SET state='indeterminate' WHERE state='submitting'")
