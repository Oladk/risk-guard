"""Test de migration de schéma v0 (mono-compte) -> v1 (multi-comptes)."""

from datetime import datetime, timezone

from src import constants as C
from src import db as DB
from src import repository as R

# Schéma v0 (tel qu'à la première version : mono-compte, pas d'account_id).
V0_SCHEMA = """
CREATE TABLE account (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    base_currency TEXT, initial_balance REAL, timezone TEXT, reset_hour INTEGER,
    week_start TEXT, warning_threshold_pct REAL, preferred_unit TEXT, one_R_pct REAL,
    sound_enabled INTEGER, notify_enabled INTEGER
);
CREATE TABLE risk_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT, rule_type TEXT UNIQUE, enabled INTEGER,
    threshold_value REAL, threshold_unit TEXT, action TEXT
);
CREATE TABLE trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT, instrument TEXT, market TEXT, direction TEXT,
    status TEXT, opened_at TEXT, closed_at TEXT, trading_day TEXT, planned_risk_pct REAL,
    planned_risk_amount REAL, planned_risk_R REAL, entry_price REAL, stop_price REAL,
    take_profit REAL, size REAL, realized_pnl_amount REAL, realized_R REAL, outcome TEXT,
    emotion_tag TEXT, note TEXT
);
CREATE TABLE balance_adjustments (
    id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT, amount REAL, type TEXT, note TEXT
);
CREATE TABLE alerts_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT, rule_type TEXT, level TEXT, context TEXT
);
"""


def _build_v0(conn):
    conn.executescript(V0_SCHEMA)
    conn.execute("PRAGMA user_version = 0")
    conn.execute(
        """INSERT INTO account VALUES (1, 'EUR', 5000, 'Europe/Paris', 17, 'MONDAY',
           0.8, 'PCT', 0.01, 1, 0)""")
    conn.execute("""INSERT INTO risk_rules (rule_type, enabled, threshold_value,
                 threshold_unit, action) VALUES ('daily_loss', 1, 0.04, 'PCT', 'BLOCK')""")
    conn.execute(
        """INSERT INTO trades (instrument, market, direction, status, opened_at,
           trading_day, planned_risk_pct, planned_risk_amount, planned_risk_R)
           VALUES ('EURUSD', 'FOREX', 'LONG', 'OPEN', '2026-07-06T10:00:00+00:00',
           '2026-07-06', 0.01, 50, 1.0)""")
    conn.execute("""INSERT INTO balance_adjustments (date, amount, type)
                 VALUES ('2026-07-01T00:00:00+00:00', 1000, 'DEPOSIT')""")
    conn.commit()


def test_migration_v0_to_v1(tmp_path):
    db_path = tmp_path / "old.db"
    conn = DB.get_conn(db_path)
    _build_v0(conn)

    # Migration (chaîne v0 -> v1 -> ... -> v6)
    DB.init_db(conn)

    # Version passée à la version courante
    assert conn.execute("PRAGMA user_version").fetchone()[0] == DB.CURRENT_VERSION == 6

    # accounts existe, l'ancienne table account a disparu
    assert DB._table_exists(conn, "accounts")
    assert not DB._table_exists(conn, "account")

    # v2 : nouvelles tables + colonnes
    assert DB._table_exists(conn, "correlations")
    assert DB._table_exists(conn, "checklist_items")
    trade_cols = DB._columns(conn, "trades")
    assert "setup" in trade_cols and "thesis" in trade_cols
    assert len(R.load_checklist(conn, 1)) == len(C.DEFAULT_CHECKLIST)

    # v3 : colonnes de connexion MT5 sur accounts
    acc_cols = DB._columns(conn, "accounts")
    assert {"mt5_login", "mt5_server", "mt5_path", "enforce_enabled"} <= acc_cols

    # v4 : table tilt_config seedée pour le compte migré
    assert DB._table_exists(conn, "tilt_config")
    assert R.load_tilt_config(conn, 1).tilt_threshold == C.DEFAULT_TILT["tilt_threshold"]

    # v5 : table users + user_id sur accounts (compte migré rattaché à user 1)
    assert DB._table_exists(conn, "users")
    assert "user_id" in DB._columns(conn, "accounts")

    # v6 : flag onboarded ; le compte migré (avec données) est déjà configuré
    assert "onboarded" in DB._columns(conn, "accounts")
    assert R.is_onboarded(conn, 1) is True

    # Compte migré avec ses valeurs d'origine
    acc = R.load_account(conn, 1)
    assert acc.base_currency == "EUR"
    assert acc.reset_hour == 17
    assert acc.name == "Compte principal"

    # account_id backfillé à 1 sur les données existantes
    trades = R.load_trades(conn, account_id=1)
    assert len(trades) == 1
    assert trades[0].instrument == "EURUSD"
    adj = R.load_adjustments(conn, account_id=1)
    assert len(adj) == 1

    # Règle préservée + nouvelles tables présentes
    rules = R.load_rules(conn, 1)
    assert any(r.rule_type == "daily_loss" and r.threshold_value == 0.04 for r in rules)
    assert DB._table_exists(conn, "trade_events")
    assert DB._table_exists(conn, "fx_rates")

    # init_db ré-appelé = idempotent (pas d'erreur, version stable)
    DB.init_db(conn)
    assert conn.execute("PRAGMA user_version").fetchone()[0] == DB.CURRENT_VERSION
