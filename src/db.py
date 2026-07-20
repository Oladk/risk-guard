"""Connexion SQLite + schéma versionné + migrations.

Le schéma est versionné via `PRAGMA user_version`. `init_db` :
- installe le schéma le plus récent sur une base vierge,
- migre une base existante par paliers (v0→v1→v2…),
- est idempotent (peut être appelé à chaque démarrage).
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from . import constants as C

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "risk.db"

CURRENT_VERSION = 6

# --- DDL des tables (schéma courant) ----------------------------------------
DDL_USERS = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""

DDL_ACCOUNTS = """
CREATE TABLE IF NOT EXISTS accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL DEFAULT 1,
    name TEXT NOT NULL,
    kind TEXT NOT NULL DEFAULT 'MANUAL',        -- MANUAL | MT5
    base_currency TEXT NOT NULL,
    initial_balance REAL NOT NULL,
    timezone TEXT NOT NULL,
    reset_hour INTEGER NOT NULL,
    week_start TEXT NOT NULL,
    warning_threshold_pct REAL NOT NULL,
    preferred_unit TEXT NOT NULL,
    one_R_pct REAL NOT NULL,
    sound_enabled INTEGER NOT NULL DEFAULT 1,
    notify_enabled INTEGER NOT NULL DEFAULT 0,
    mt5_login INTEGER,
    mt5_server TEXT,
    mt5_path TEXT,
    enforce_enabled INTEGER NOT NULL DEFAULT 0,
    onboarded INTEGER NOT NULL DEFAULT 0
);
"""

DDL_RISK_RULES = """
CREATE TABLE IF NOT EXISTS risk_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id INTEGER NOT NULL DEFAULT 1,
    rule_type TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1,
    threshold_value REAL NOT NULL,
    threshold_unit TEXT NOT NULL,
    action TEXT NOT NULL DEFAULT 'BLOCK',
    UNIQUE(account_id, rule_type)
);
"""

DDL_TRADES = """
CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id INTEGER NOT NULL DEFAULT 1,
    external_id TEXT,                            -- id broker (sync MT5)
    instrument TEXT NOT NULL,
    market TEXT NOT NULL,
    direction TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'OPEN',
    opened_at TEXT NOT NULL,
    closed_at TEXT,
    trading_day TEXT NOT NULL,
    planned_risk_pct REAL NOT NULL,
    planned_risk_amount REAL NOT NULL,
    planned_risk_R REAL NOT NULL,
    entry_price REAL,
    stop_price REAL,
    take_profit REAL,
    size REAL,
    realized_pnl_amount REAL,
    realized_R REAL,
    outcome TEXT,
    emotion_tag TEXT,
    note TEXT,
    setup TEXT,
    thesis TEXT
);
"""

DDL_ADJUSTMENTS = """
CREATE TABLE IF NOT EXISTS balance_adjustments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id INTEGER NOT NULL DEFAULT 1,
    date TEXT NOT NULL,
    amount REAL NOT NULL,
    type TEXT NOT NULL,
    note TEXT
);
"""

DDL_ALERTS = """
CREATE TABLE IF NOT EXISTS alerts_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id INTEGER NOT NULL DEFAULT 1,
    timestamp TEXT NOT NULL,
    rule_type TEXT NOT NULL,
    level TEXT NOT NULL,
    context TEXT
);
"""

# A5 — journal d'événements append-only (log inviolable / audit).
DDL_TRADE_EVENTS = """
CREATE TABLE IF NOT EXISTS trade_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id INTEGER NOT NULL DEFAULT 1,
    trade_id INTEGER,
    event_type TEXT NOT NULL,                    -- OPEN | CLOSE | CANCEL | EDIT | SYNC
    timestamp TEXT NOT NULL,
    payload TEXT
);
"""

# A2 — taux de change.
DDL_FX_RATES = """
CREATE TABLE IF NOT EXISTS fx_rates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    from_ccy TEXT NOT NULL,
    to_ccy TEXT NOT NULL,
    rate REAL NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(from_ccy, to_ccy)
);
"""

# A3 — corrélations entre instruments (niveau marché, partagé).
DDL_CORRELATIONS = """
CREATE TABLE IF NOT EXISTS correlations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    instrument_a TEXT NOT NULL,
    instrument_b TEXT NOT NULL,
    corr REAL NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(instrument_a, instrument_b)
);
"""

# A4 — items de checklist pré-trade (par compte).
DDL_CHECKLIST = """
CREATE TABLE IF NOT EXISTS checklist_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id INTEGER NOT NULL DEFAULT 1,
    label TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1,
    position INTEGER NOT NULL DEFAULT 0
);
"""

# C1 — seuils de détection de tilt (par compte).
DDL_TILT_CONFIG = """
CREATE TABLE IF NOT EXISTS tilt_config (
    account_id INTEGER PRIMARY KEY,
    min_gap_minutes REAL NOT NULL,
    reentry_window_minutes REAL NOT NULL,
    escalation_ratio REAL NOT NULL,
    emotion_threshold INTEGER NOT NULL,
    overtrade_count INTEGER NOT NULL,
    vigilance_threshold INTEGER NOT NULL,
    tilt_threshold INTEGER NOT NULL
);
"""

DDL_INDEXES = """
CREATE INDEX IF NOT EXISTS idx_trades_account ON trades(account_id);
CREATE INDEX IF NOT EXISTS idx_trades_status ON trades(status);
CREATE INDEX IF NOT EXISTS idx_trades_closed ON trades(closed_at);
CREATE UNIQUE INDEX IF NOT EXISTS uidx_trades_external ON trades(account_id, external_id) WHERE external_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_events_account ON trade_events(account_id);
CREATE INDEX IF NOT EXISTS idx_rules_account ON risk_rules(account_id);
CREATE INDEX IF NOT EXISTS idx_checklist_account ON checklist_items(account_id);
"""

_ALL_DDL = [DDL_USERS, DDL_ACCOUNTS, DDL_RISK_RULES, DDL_TRADES, DDL_ADJUSTMENTS,
            DDL_ALERTS, DDL_TRADE_EVENTS, DDL_FX_RATES, DDL_CORRELATIONS,
            DDL_CHECKLIST, DDL_TILT_CONFIG]


# ---------------------------------------------------------------------------
# Sélection de backend : SQLite (défaut) ou Postgres (si DATABASE_URL défini)
# ---------------------------------------------------------------------------
def _database_url() -> str:
    """URL Postgres depuis l'env (priorité) ou `st.secrets` (Streamlit Cloud)."""
    url = os.environ.get("DATABASE_URL", "")
    if url:
        return url
    try:
        import streamlit as st
        return st.secrets.get("DATABASE_URL", "") or ""
    except Exception:
        return ""


def is_postgres() -> bool:
    return _database_url().startswith(("postgres://", "postgresql://"))


def _adapt_ddl(sql: str) -> str:
    """Adapte le DDL SQLite au dialecte Postgres."""
    if is_postgres():
        return sql.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "SERIAL PRIMARY KEY")
    return sql


class _PgConn:
    """Adaptateur fin psycopg : traduit `?`→`%s` et gère `executescript`.

    Le code du repository reste identique (placeholders `?`, accès `row["col"]`)."""

    def __init__(self, raw):
        self._raw = raw

    def execute(self, sql, params=()):
        return self._raw.execute(sql.replace("?", "%s"), params)

    def executescript(self, script):
        for stmt in script.split(";"):
            if stmt.strip():
                self._raw.execute(stmt)

    def commit(self):
        self._raw.commit()

    def close(self):
        self._raw.close()


def get_conn(db_path: Path | str | None = None):
    """Ouvre une connexion. SQLite par défaut ; Postgres si `DATABASE_URL` est défini.

    Le chemin SQLite peut être surchargé via `RISK_DB_PATH` (isolation des tests)."""
    if is_postgres():
        import psycopg
        from psycopg.rows import dict_row
        return _PgConn(psycopg.connect(_database_url(), row_factory=dict_row))
    if db_path is None:
        env_path = os.environ.get("RISK_DB_PATH")
        if env_path:
            db_path = env_path
        else:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            db_path = DB_PATH
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def last_insert_id(conn, cursor) -> int:
    """Dernier id auto-généré, portable SQLite (lastrowid) / Postgres (lastval())."""
    if is_postgres():
        return conn.execute("SELECT lastval() AS id").fetchone()["id"]
    return cursor.lastrowid


def _table_exists(conn, name: str) -> bool:
    if is_postgres():
        return conn.execute(
            "SELECT 1 FROM information_schema.tables WHERE table_name=?", (name,)
        ).fetchone() is not None
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


def _columns(conn, table: str) -> set[str]:
    # Utilisé uniquement dans les migrations SQLite (un Postgres neuf part de zéro).
    return {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}


def _version(conn) -> int:
    if is_postgres():
        if not _table_exists(conn, "schema_meta"):
            return 0
        row = conn.execute("SELECT version FROM schema_meta LIMIT 1").fetchone()
        return row["version"] if row else 0
    return conn.execute("PRAGMA user_version").fetchone()[0]


def _set_version(conn, v: int) -> None:
    if is_postgres():
        conn.executescript("CREATE TABLE IF NOT EXISTS schema_meta (version INTEGER NOT NULL)")
        conn.execute("DELETE FROM schema_meta")
        conn.execute("INSERT INTO schema_meta (version) VALUES (?)", (int(v),))
        return
    conn.execute(f"PRAGMA user_version = {int(v)}")


def init_db(conn: sqlite3.Connection) -> None:
    if not _table_exists(conn, "accounts") and not _table_exists(conn, "account"):
        _create_latest(conn)
        _set_version(conn, CURRENT_VERSION)
    else:
        v = _version(conn)
        if v < 1:
            _migrate_v0_to_v1(conn)
            v = 1
        if v < 2:
            _migrate_v1_to_v2(conn)
            v = 2
        if v < 3:
            _migrate_v2_to_v3(conn)
            v = 3
        if v < 4:
            _migrate_v3_to_v4(conn)
            v = 4
        if v < 5:
            _migrate_v4_to_v5(conn)
            v = 5
        if v < 6:
            _migrate_v5_to_v6(conn)
            v = 6
        _set_version(conn, CURRENT_VERSION)
    _seed(conn)
    conn.commit()


def _create_latest(conn) -> None:
    for ddl in _ALL_DDL:
        conn.executescript(_adapt_ddl(ddl))
    conn.executescript(_adapt_ddl(DDL_INDEXES))


def _migrate_v0_to_v1(conn: sqlite3.Connection) -> None:
    """v0 (mono-compte `account`, tables sans account_id) → v1 (multi-comptes)."""
    conn.executescript(DDL_ACCOUNTS)
    row = conn.execute("SELECT * FROM account WHERE id = 1").fetchone()
    if row is not None:
        conn.execute(
            """INSERT INTO accounts (id, name, kind, base_currency, initial_balance,
               timezone, reset_hour, week_start, warning_threshold_pct, preferred_unit,
               one_R_pct, sound_enabled, notify_enabled)
               VALUES (1, 'Compte principal', 'MANUAL', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (row["base_currency"], row["initial_balance"], row["timezone"],
             row["reset_hour"], row["week_start"], row["warning_threshold_pct"],
             row["preferred_unit"], row["one_R_pct"], row["sound_enabled"],
             row["notify_enabled"]),
        )

    for table in ("trades", "balance_adjustments", "alerts_log"):
        if _table_exists(conn, table) and "account_id" not in _columns(conn, table):
            conn.execute(
                f"ALTER TABLE {table} ADD COLUMN account_id INTEGER NOT NULL DEFAULT 1")
    if "external_id" not in _columns(conn, "trades"):
        conn.execute("ALTER TABLE trades ADD COLUMN external_id TEXT")

    if _table_exists(conn, "risk_rules"):
        conn.execute("ALTER TABLE risk_rules RENAME TO risk_rules_old")
    conn.executescript(DDL_RISK_RULES)
    if _table_exists(conn, "risk_rules_old"):
        conn.execute(
            """INSERT INTO risk_rules (account_id, rule_type, enabled, threshold_value,
               threshold_unit, action)
               SELECT 1, rule_type, enabled, threshold_value, threshold_unit, action
               FROM risk_rules_old""")
        conn.execute("DROP TABLE risk_rules_old")

    conn.executescript(DDL_TRADE_EVENTS)
    conn.executescript(DDL_FX_RATES)
    conn.execute("DROP TABLE account")


def _migrate_v1_to_v2(conn: sqlite3.Connection) -> None:
    """v1 → v2 : colonnes setup/thesis sur trades, tables correlations & checklist."""
    for col in ("setup", "thesis"):
        if col not in _columns(conn, "trades"):
            conn.execute(f"ALTER TABLE trades ADD COLUMN {col} TEXT")
    conn.executescript(DDL_CORRELATIONS)
    conn.executescript(DDL_CHECKLIST)
    conn.executescript(DDL_INDEXES)


def _migrate_v2_to_v3(conn: sqlite3.Connection) -> None:
    """v2 → v3 : colonnes de connexion MT5 sur accounts + index unique external_id."""
    add_cols = [
        ("mt5_login", "INTEGER"),
        ("mt5_server", "TEXT"),
        ("mt5_path", "TEXT"),
        ("enforce_enabled", "INTEGER NOT NULL DEFAULT 0"),
    ]
    existing = _columns(conn, "accounts")
    for col, decl in add_cols:
        if col not in existing:
            conn.execute(f"ALTER TABLE accounts ADD COLUMN {col} {decl}")
    conn.executescript(DDL_INDEXES)


def _migrate_v3_to_v4(conn: sqlite3.Connection) -> None:
    """v3 → v4 : table `tilt_config` (seuils de détection de tilt par compte)."""
    conn.executescript(DDL_TILT_CONFIG)


def _migrate_v4_to_v5(conn: sqlite3.Connection) -> None:
    """v4 → v5 : table `users` + `user_id` sur accounts (auth multi-utilisateur).

    Les comptes existants restent rattachés à user_id=1 (propriétaire local par défaut)."""
    conn.executescript(DDL_USERS)
    if "user_id" not in _columns(conn, "accounts"):
        conn.execute("ALTER TABLE accounts ADD COLUMN user_id INTEGER NOT NULL DEFAULT 1")


def _migrate_v5_to_v6(conn: sqlite3.Connection) -> None:
    """v5 → v6 : flag `onboarded` sur accounts (assistant premier lancement).

    Les comptes existants sont considérés déjà configurés (onboarded=1)."""
    if "onboarded" not in _columns(conn, "accounts"):
        conn.execute("ALTER TABLE accounts ADD COLUMN onboarded INTEGER NOT NULL DEFAULT 0")
    # Comptes déjà présents = déjà configurés (le seed d'un compte neuf reste à 0).
    conn.execute("UPDATE accounts SET onboarded = 1")


def _seed(conn: sqlite3.Connection) -> None:
    if conn.execute("SELECT COUNT(*) AS n FROM accounts").fetchone()["n"] == 0:
        a = C.DEFAULT_ACCOUNT
        conn.execute(
            """INSERT INTO accounts (name, kind, base_currency, initial_balance,
               timezone, reset_hour, week_start, warning_threshold_pct, preferred_unit,
               one_R_pct, sound_enabled, notify_enabled)
               VALUES ('Compte principal', 'MANUAL', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (a["base_currency"], a["initial_balance"], a["timezone"], a["reset_hour"],
             a["week_start"], a["warning_threshold_pct"], a["preferred_unit"],
             a["one_R_pct"], a["sound_enabled"], a["notify_enabled"]),
        )
    for acc in conn.execute("SELECT id FROM accounts").fetchall():
        seed_rules_for_account(conn, acc["id"])
        seed_checklist_for_account(conn, acc["id"])
        seed_tilt_config_for_account(conn, acc["id"])


def seed_rules_for_account(conn: sqlite3.Connection, account_id: int) -> None:
    existing = {r["rule_type"] for r in conn.execute(
        "SELECT rule_type FROM risk_rules WHERE account_id = ?", (account_id,))}
    for rule_type, enabled, value, unit, action in C.DEFAULT_RULES:
        if rule_type not in existing:
            conn.execute(
                """INSERT INTO risk_rules (account_id, rule_type, enabled,
                   threshold_value, threshold_unit, action) VALUES (?, ?, ?, ?, ?, ?)""",
                (account_id, rule_type, enabled, value, unit, action),
            )


def seed_checklist_for_account(conn: sqlite3.Connection, account_id: int) -> None:
    n = conn.execute("SELECT COUNT(*) AS n FROM checklist_items WHERE account_id = ?",
                     (account_id,)).fetchone()["n"]
    if n == 0:
        for i, label in enumerate(C.DEFAULT_CHECKLIST):
            conn.execute(
                """INSERT INTO checklist_items (account_id, label, enabled, position)
                   VALUES (?, ?, 1, ?)""", (account_id, label, i))


def seed_tilt_config_for_account(conn: sqlite3.Connection, account_id: int) -> None:
    exists = conn.execute("SELECT 1 FROM tilt_config WHERE account_id = ?",
                          (account_id,)).fetchone()
    if not exists:
        t = C.DEFAULT_TILT
        conn.execute(
            """INSERT INTO tilt_config (account_id, min_gap_minutes, reentry_window_minutes,
               escalation_ratio, emotion_threshold, overtrade_count, vigilance_threshold,
               tilt_threshold) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (account_id, t["min_gap_minutes"], t["reentry_window_minutes"],
             t["escalation_ratio"], t["emotion_threshold"], t["overtrade_count"],
             t["vigilance_threshold"], t["tilt_threshold"]),
        )
