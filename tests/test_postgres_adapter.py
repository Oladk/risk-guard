"""Tests des adaptateurs Postgres (parties pures — pas de vraie base PG requise)."""

from src import db as DB
from src import repository as R


def test_is_postgres_false_by_default(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert DB.is_postgres() is False


def test_is_postgres_true_for_pg_url(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@host/db")
    assert DB.is_postgres() is True


def test_adapt_ddl_sqlite_unchanged(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert "AUTOINCREMENT" in DB._adapt_ddl("id INTEGER PRIMARY KEY AUTOINCREMENT")


def test_adapt_ddl_postgres_serial(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://x")
    out = DB._adapt_ddl("id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT")
    assert "SERIAL PRIMARY KEY" in out
    assert "AUTOINCREMENT" not in out


def test_pgconn_translates_placeholders():
    calls = []

    class FakeRaw:
        def execute(self, sql, params=()):
            calls.append((sql, params))
            return "cursor"

    c = DB._PgConn(FakeRaw())
    c.execute("SELECT * FROM t WHERE a=? AND b=?", (1, 2))
    assert calls[0][0] == "SELECT * FROM t WHERE a=%s AND b=%s"
    assert calls[0][1] == (1, 2)


def test_row_to_account_accepts_lowercase_pg_keys():
    """Postgres renvoie les colonnes en minuscules (one_r_pct) — l'accès doit marcher."""
    row = {
        "id": 1, "name": "X", "kind": "MANUAL", "base_currency": "XOF",
        "initial_balance": 1000.0, "timezone": "UTC", "reset_hour": 0,
        "week_start": "MONDAY", "warning_threshold_pct": 0.8, "preferred_unit": "PCT",
        "one_r_pct": 0.01, "sound_enabled": 1, "notify_enabled": 0,
        "mt5_login": None, "mt5_server": "", "mt5_path": "", "enforce_enabled": 0,
    }
    acc = R._row_to_account(row)
    assert acc.one_R_pct == 0.01
    assert acc.base_currency == "XOF"


def test_row_to_trade_accepts_lowercase_pg_keys():
    row = {
        "id": 1, "instrument": "EURUSD", "market": "FOREX", "direction": "LONG",
        "status": "CLOSED", "opened_at": "2026-07-07T12:00:00+00:00",
        "closed_at": "2026-07-07T13:00:00+00:00", "trading_day": "2026-07-07",
        "planned_risk_pct": 0.01, "planned_risk_amount": 100.0, "planned_risk_r": 1.0,
        "entry_price": None, "stop_price": None, "take_profit": None, "size": None,
        "realized_pnl_amount": 200.0, "realized_r": 2.0, "outcome": "WIN",
        "emotion_tag": None, "note": None, "setup": None, "thesis": None,
        "external_id": None,
    }
    t = R._row_to_trade(row)
    assert t.planned_risk_R == 1.0
    assert t.realized_R == 2.0


def test_pgconn_executescript_splits_statements():
    calls = []

    class FakeRaw:
        def execute(self, sql, params=()):
            calls.append(sql.strip())

    c = DB._PgConn(FakeRaw())
    c.executescript("CREATE TABLE a (x INT);\nCREATE TABLE b (y INT);\n")
    assert len([s for s in calls if s]) == 2
