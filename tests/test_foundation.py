import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from dog_art.budget import BudgetError, Ledger
from dog_art.clock import FrozenClock
from dog_art.safety import SafetyError, owned_path, redact
from dog_art.settings import ConfigError, load_secrets, load_settings, load_toml
from dog_art.storage import Store

ROOT = Path(__file__).resolve().parents[1]


def test_config_separation(tmp_path):
    app = tmp_path / "app.toml"
    app.write_text((ROOT / "config/app.toml").read_text())
    settings = load_settings(app, tmp_path / ".env", environ={})
    assert settings.get("COLLAGE_WIDTH") == 1920
    assert not settings.secrets["OPENAI_API_KEY"]
    app.write_text(app.read_text() + "\nDEPLOY_TARGET_CTID = 110\n")
    with pytest.raises(ConfigError, match="misplaced"):
        load_toml(app, "app")
    app.write_text('MQTT_PORT = "1883"')
    with pytest.raises(ConfigError, match="integer"):
        load_toml(app, "app")
    app.write_text("MQTT_PORT = 1883\nMQTT_PORT = 1883")
    with pytest.raises(ConfigError):
        load_toml(app, "app")


def test_secret_precedence_and_no_interpolation(tmp_path):
    env = tmp_path / ".env"
    env.write_text("OPENAI_API_KEY=sentinel-${HOME}\n")
    assert load_secrets(env, {})["OPENAI_API_KEY"] == "sentinel-${HOME}"
    assert load_secrets(env, {"OPENAI_API_KEY": ""})["OPENAI_API_KEY"] == ""
    env.write_text("OPENAI_API_KEY=one\nOPENAI_API_KEY=two")
    with pytest.raises(ConfigError, match="duplicate"):
        load_secrets(env, {})
    env.write_text("MQTT_PORT=1883")
    with pytest.raises(ConfigError, match="misplaced"):
        load_secrets(env, {})
    assert "sentinel" not in redact("token=sentinel", ("sentinel",))


def test_path_policy(tmp_path):
    root = tmp_path / "state"
    root.mkdir()
    with pytest.raises(SafetyError):
        owned_path(root, "../escape")
    (root / "link").symlink_to(tmp_path)
    with pytest.raises(SafetyError):
        owned_path(root, "link/x")
    with pytest.raises(SafetyError):
        owned_path(Path("/"), "tmp/x")


def test_queue_dedup_leases_and_backup(tmp_path):
    store = Store(tmp_path / "state" / "catalog.sqlite")
    store.enqueue("ingest", "same", {"x": 1}, 0, max_attempts=2)
    store.enqueue("ingest", "same", {"x": 1}, 0, max_attempts=2)
    first = store.claim(0, 10)
    assert first["attempts"] == 1
    assert store.claim(9, 10) is None
    second = store.claim(10, 10)
    assert second["attempts"] == 2
    with pytest.raises(ValueError, match="stale"):
        store.finish(first["job_id"], first["lease_token"])
    store.finish(second["job_id"], second["lease_token"])
    backup = store.backup(tmp_path / "backup.sqlite")
    restored = Store(backup)
    assert restored.status()["jobs"] == {"done": 1}
    restored.close()
    store.close()
    db = sqlite3.connect(backup)
    db.execute("PRAGMA user_version=99")
    db.close()
    with pytest.raises(ValueError, match="incompatible"):
        Store(backup)


def test_paid_ledger_conservative(tmp_path):
    store = Store(tmp_path / "catalog.sqlite")
    store.db.execute("INSERT INTO dogs VALUES('d',0,'accepted',NULL)")
    ledger = Ledger(store)
    ledger.set_build_scope("build", 2)
    kwargs = {
        "reserve_usd": 1,
        "daily_usd": 5,
        "daily_calls": 12,
        "concurrency": 1,
        "build_scope": "build",
    }
    first, created = ledger.reserve("recipe", "d", {}, "2026-10-22", 0, **kwargs)
    assert created
    _, created = ledger.reserve("recipe", "d", {}, "2026-10-22", 0, **kwargs)
    assert not created
    with pytest.raises(BudgetError, match="concurrency"):
        ledger.reserve("recipe2", "d", {}, "2026-10-22", 0, **kwargs)
    ledger.transition(first["request_id"], "reserved", "submitting")
    ledger.recover()
    assert store.status()["requests"] == {"indeterminate": 1}
    with pytest.raises(BudgetError):
        ledger.transition(first["request_id"], "indeterminate", "submitting")
    store.close()


def test_utc_and_dst():
    clock = FrozenClock(datetime(2026, 11, 1, 4, 30, tzinfo=UTC))
    assert clock.day() == "2026-11-01"
    clock.value = datetime(2026, 11, 2, 4, 30, tzinfo=UTC)
    assert clock.day() == "2026-11-01"
    with pytest.raises(ValueError):
        FrozenClock(datetime(2026, 10, 22))


def test_crash_before_submission_releases_concurrency_without_replaying(tmp_path):
    store = Store(tmp_path / "state/catalog.sqlite")
    store.db.execute("INSERT INTO dogs VALUES('d',0,'accepted',NULL)")
    ledger = Ledger(store)
    kwargs = {"reserve_usd": 1, "daily_usd": 5, "daily_calls": 5, "concurrency": 1}
    first, _ = ledger.reserve("first", "d", {}, "2026-10-22", 0, **kwargs)
    ledger.recover()
    assert (
        store.db.execute(
            "SELECT state FROM requests WHERE request_id=?", (first["request_id"],)
        ).fetchone()[0]
        == "failed_before_submission"
    )
    old, created = ledger.reserve("first", "d", {}, "2026-10-22", 1, **kwargs)
    assert not created and old["request_id"] == first["request_id"]
    _, created = ledger.reserve("second", "d", {}, "2026-10-22", 1, **kwargs)
    assert created
    store.close()


def test_partial_reference_policy_is_explicit_and_only_per_observation(tmp_path):
    app = tmp_path / "app.toml"
    text = (ROOT / "config/app.toml").read_text()
    app.write_text(text)
    assert (
        load_settings(app, tmp_path / ".env", environ={}).get("SOURCE_REFERENCE_POLICY")
        == "best_effort_partial"
    )
    app.write_text(
        text.replace(
            'SOURCE_REFERENCE_POLICY = "best_effort_partial"',
            'SOURCE_REFERENCE_POLICY = "anything"',
        )
    )
    with pytest.raises(ConfigError, match="SOURCE_REFERENCE_POLICY"):
        load_settings(app, tmp_path / ".env", environ={})
    app.write_text(
        text.replace('IDENTITY_MODE = "per_observation"', 'IDENTITY_MODE = "calibrated_auto"')
    )
    with pytest.raises(ConfigError, match="partial references require per_observation"):
        load_settings(app, tmp_path / ".env", environ={})
    app.write_text(text.replace('SOURCE_REFERENCE_POLICY = "best_effort_partial"', ""))
    assert (
        load_settings(app, tmp_path / ".env", environ={}).get(
            "SOURCE_REFERENCE_POLICY", "full_body"
        )
        == "full_body"
    )


@pytest.mark.parametrize(
    "replacement",
    [
        'PORTRAIT_REVIEW_MODE = "approve_everything"',
        "OPENAI_PORTRAIT_RESERVATION_USD = 0",
        "OPENAI_PORTRAIT_RESERVATION_USD = 6",
    ],
)
def test_output_review_and_reservation_configuration_fail_closed(tmp_path, replacement):
    text = (ROOT / "config/app.toml").read_text()
    key = replacement.split(" = ")[0]
    import re

    text = re.sub(r"^" + key + r" = .*$", replacement, text, flags=re.M)
    app = tmp_path / "app.toml"
    app.write_text(text)
    with pytest.raises(ConfigError):
        load_settings(app, tmp_path / ".env", environ={})


@pytest.mark.parametrize("key", ["OPENAI_PORTRAIT_RESERVATION_USD", "OPENAI_DAILY_BUDGET_USD"])
def test_unknown_spending_placeholder_allows_offline_load_but_blocks_portrait(tmp_path, key):
    import re

    text = (ROOT / "config/app.toml").read_text()
    app = tmp_path / "app.toml"
    app.write_text(re.sub(r"^" + key + r" = .*$", key + ' = ""', text, flags=re.M))
    settings = load_settings(app, tmp_path / ".env", environ={})
    assert key in settings.missing("portrait")
