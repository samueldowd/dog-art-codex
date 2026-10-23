"""Ready-art status retains held appearances and conservative paid reservations."""

import json
from pathlib import Path

import pytest

from dog_art.settings import ConfigError, load_settings
from dog_art.storage import Store

ROOT = Path(__file__).resolve().parents[1]


def test_status_counts_ready_held_and_unrequested_without_private_payloads(tmp_path):
    store = Store(tmp_path / "catalog.sqlite")
    try:
        store.db.execute("INSERT INTO days VALUES('2026-10-22','generation',8,0)")
        store.db.execute("INSERT INTO meta VALUES('current_day','2026-10-22')")
        for i in range(8):
            dog = f"private-dog-{i}"
            store.db.execute("INSERT INTO dogs(dog_id,created_at) VALUES(?,0)", (dog,))
            store.db.execute("INSERT INTO membership VALUES('2026-10-22',?,0,0)", (dog,))
            if i == 7:
                continue
            state = "validated" if i < 5 else "needs_review"
            store.db.execute(
                "INSERT INTO portraits(recipe_key,dog_id,recipe,state) VALUES(?,?,?,?)",
                (f"recipe-{i}", dog, "private-source-description", state),
            )
            store.db.execute(
                "INSERT INTO requests(request_id,recipe_key,day,reserved_usd,state,created_at) VALUES(?,?,?,?,?,0)",
                (f"request-{i}", f"recipe-{i}", "2026-10-22", 2 if i == 0 else 0.5, state),
            )
        status = store.status()
        assert status["display"] == {
            "accepted_appearances": 8,
            "approved_portraits": 5,
            "pending_portraits": 3,
            "pending_states": {"needs_review": 2, "not_requested": 1},
        }
        assert status["paid_today"] == {"calls": 7, "reserved_usd": 5}
        assert "private-" not in json.dumps(status)
        store.db.execute("UPDATE portraits SET state='validated' WHERE recipe_key='recipe-5'")
        assert store.status()["display"]["approved_portraits"] == 6
        assert store.db.execute("SELECT count(*) FROM membership").fetchone()[0] == 8
        store.db.execute("INSERT INTO days VALUES('2026-10-23','newgeneration',0,0)")
        store.db.execute("UPDATE meta SET value='2026-10-23' WHERE key='current_day'")
        assert store.status()["display"]["accepted_appearances"] == 0
        assert store.status()["paid_today"] == {"calls": 0, "reserved_usd": 0}
        assert store.db.execute("SELECT count(*) FROM requests").fetchone()[0] == 7
    finally:
        store.close()


def test_collage_policy_is_explicit_and_legacy_default_is_strict(tmp_path):
    source = (ROOT / "config/app.toml").read_text()
    config = tmp_path / "app.toml"
    config.write_text(source)
    assert (
        load_settings(config, tmp_path / ".env", environ={})["COLLAGE_PORTRAIT_POLICY"]
        == "approved_only"
    )
    legacy = "\n".join(
        line for line in source.splitlines() if not line.startswith("COLLAGE_PORTRAIT_POLICY")
    )
    config.write_text(legacy)
    assert (
        load_settings(config, tmp_path / ".env", environ={}).get(
            "COLLAGE_PORTRAIT_POLICY", "all_accepted"
        )
        == "all_accepted"
    )
    config.write_text(legacy + '\nCOLLAGE_PORTRAIT_POLICY = "skip_qa"\n')
    with pytest.raises(ConfigError, match="COLLAGE_PORTRAIT_POLICY"):
        load_settings(config, tmp_path / ".env", environ={})


def test_cli_reports_pending_art_while_ready_subset_is_rendered(tmp_path, monkeypatch, capsys):
    from test_ready_collages import ready_setup

    import dog_art.cli as cli
    from dog_art.clock import FrozenClock

    store, settings, clock, daily, transport = ready_setup(tmp_path, count=3, ready=1)
    store.close()
    monkeypatch.setattr(cli, "load_settings", lambda *args, **kwargs: settings)
    # The production date is fixed only inside this offline CLI fixture.
    monkeypatch.setattr("dog_art.runtime.Clock", lambda: FrozenClock(clock.now()))
    assert cli.main(["rollover"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["composition_pending"] is True
    assert result["render_pending"] is False
    assert result["display"]["accepted_appearances"] == 3
    assert result["display"]["approved_portraits"] == 1
    assert result["display"]["pending_portraits"] == 2
    assert result["publication"] is None
    assert set(result["day"]["dog_ids"]) == {"dog-0", "dog-1", "dog-2"}
