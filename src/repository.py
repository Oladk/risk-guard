"""Couche d'accès aux données : conversion lignes SQLite <-> dataclasses.

Multi-comptes : la plupart des fonctions prennent un `account_id` (défaut 1 pour
rester rétro-compatible avec le mono-compte). Chaque mutation de trade écrit aussi
un événement append-only dans `trade_events` (log inviolable / audit).
"""

from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime
from typing import Optional

from . import behavior as B
from . import constants as C
from . import db as DB
from . import risk_engine as E
from .time_utils import UTC, _as_aware_utc, trading_day_of


# --- Sérialisation -----------------------------------------------------------
def _iso(dt: Optional[datetime]) -> Optional[str]:
    return None if dt is None else _as_aware_utc(dt).isoformat()


def _parse_dt(s: Optional[str]) -> Optional[datetime]:
    return None if not s else datetime.fromisoformat(s).astimezone(UTC)


def _parse_date(s: Optional[str]) -> Optional[date]:
    return None if not s else date.fromisoformat(s)


# --- Comptes -----------------------------------------------------------------
def _row_to_account(r: sqlite3.Row) -> E.Account:
    return E.Account(
        base_currency=r["base_currency"], initial_balance=r["initial_balance"],
        timezone=r["timezone"], reset_hour=r["reset_hour"], week_start=r["week_start"],
        warning_threshold_pct=r["warning_threshold_pct"], preferred_unit=r["preferred_unit"],
        one_R_pct=r["one_R_pct"], sound_enabled=bool(r["sound_enabled"]),
        notify_enabled=bool(r["notify_enabled"]), id=r["id"], name=r["name"], kind=r["kind"],
        mt5_login=r["mt5_login"], mt5_server=r["mt5_server"] or "",
        mt5_path=r["mt5_path"] or "", enforce_enabled=bool(r["enforce_enabled"]),
    )


def list_accounts(conn: sqlite3.Connection,
                  user_id: Optional[int] = None) -> list[E.Account]:
    if user_id is None:
        rows = conn.execute("SELECT * FROM accounts ORDER BY id").fetchall()
    else:
        rows = conn.execute("SELECT * FROM accounts WHERE user_id = ? ORDER BY id",
                            (user_id,)).fetchall()
    return [_row_to_account(r) for r in rows]


def load_account(conn: sqlite3.Connection, account_id: int = 1) -> E.Account:
    r = conn.execute("SELECT * FROM accounts WHERE id = ?", (account_id,)).fetchone()
    if r is None:  # repli : premier compte disponible
        r = conn.execute("SELECT * FROM accounts ORDER BY id LIMIT 1").fetchone()
    return _row_to_account(r)


def create_account(conn: sqlite3.Connection, name: str, base_currency: str,
                   initial_balance: float, timezone: str, reset_hour: int = 0,
                   week_start: str = "MONDAY", kind: str = "MANUAL",
                   user_id: int = 1) -> int:
    d = C.DEFAULT_ACCOUNT
    cur = conn.execute(
        """INSERT INTO accounts (user_id, name, kind, base_currency, initial_balance,
           timezone, reset_hour, week_start, warning_threshold_pct, preferred_unit,
           one_R_pct, sound_enabled, notify_enabled)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (user_id, name, kind, base_currency, initial_balance, timezone, reset_hour,
         week_start, d["warning_threshold_pct"], d["preferred_unit"], d["one_R_pct"],
         d["sound_enabled"], d["notify_enabled"]),
    )
    account_id = DB.last_insert_id(conn, cur)
    DB.seed_rules_for_account(conn, account_id)
    DB.seed_checklist_for_account(conn, account_id)
    DB.seed_tilt_config_for_account(conn, account_id)
    conn.commit()
    return account_id


def is_onboarded(conn: sqlite3.Connection, account_id: int) -> bool:
    r = conn.execute("SELECT onboarded FROM accounts WHERE id = ?", (account_id,)).fetchone()
    return bool(r["onboarded"]) if r else True


def mark_onboarded(conn: sqlite3.Connection, account_id: int) -> None:
    conn.execute("UPDATE accounts SET onboarded = 1 WHERE id = ?", (account_id,))
    conn.commit()


def apply_risk_profile(conn: sqlite3.Connection, account_id: int, profile: str) -> None:
    """Applique un profil de risque prédéfini aux règles du compte."""
    preset = C.RISK_PROFILES.get(profile)
    if not preset:
        return
    for rule in load_rules(conn, account_id):
        if rule.rule_type in preset:
            rule.enabled = True
            rule.threshold_value = preset[rule.rule_type]
            rule.threshold_unit = C.RULE_DEFAULT_UNIT[rule.rule_type]
            save_rule(conn, rule, account_id=account_id)


def save_account(conn: sqlite3.Connection, a: E.Account) -> None:
    conn.execute(
        """UPDATE accounts SET name=?, kind=?, base_currency=?, initial_balance=?,
           timezone=?, reset_hour=?, week_start=?, warning_threshold_pct=?,
           preferred_unit=?, one_R_pct=?, sound_enabled=?, notify_enabled=?,
           mt5_login=?, mt5_server=?, mt5_path=?, enforce_enabled=? WHERE id=?""",
        (a.name, a.kind, a.base_currency, a.initial_balance, a.timezone, a.reset_hour,
         a.week_start, a.warning_threshold_pct, a.preferred_unit, a.one_R_pct,
         int(a.sound_enabled), int(a.notify_enabled), a.mt5_login, a.mt5_server,
         a.mt5_path, int(a.enforce_enabled), a.id),
    )
    conn.commit()


# --- Règles ------------------------------------------------------------------
def load_rules(conn: sqlite3.Connection, account_id: int = 1) -> list[E.Rule]:
    rows = conn.execute("SELECT * FROM risk_rules WHERE account_id = ?",
                        (account_id,)).fetchall()
    by_type = {
        r["rule_type"]: E.Rule(rule_type=r["rule_type"], enabled=bool(r["enabled"]),
                               threshold_value=r["threshold_value"],
                               threshold_unit=r["threshold_unit"], action=r["action"])
        for r in rows
    }
    return [by_type[t] for t in C.RULE_TYPES if t in by_type]


def save_rule(conn: sqlite3.Connection, rule: E.Rule, account_id: int = 1) -> None:
    conn.execute(
        """UPDATE risk_rules SET enabled=?, threshold_value=?, threshold_unit=?,
           action=? WHERE account_id=? AND rule_type=?""",
        (int(rule.enabled), rule.threshold_value, rule.threshold_unit, rule.action,
         account_id, rule.rule_type),
    )
    conn.commit()


# --- Ajustements de solde ----------------------------------------------------
def load_adjustments(conn: sqlite3.Connection, account_id: int = 1) -> list[E.Adjustment]:
    rows = conn.execute(
        "SELECT * FROM balance_adjustments WHERE account_id = ? ORDER BY date",
        (account_id,)).fetchall()
    return [E.Adjustment(date=_parse_dt(r["date"]), amount=r["amount"], type=r["type"])
            for r in rows]


def add_adjustment(conn: sqlite3.Connection, amount: float, type_: str,
                   when: datetime, note: str = "", account_id: int = 1) -> None:
    conn.execute(
        """INSERT INTO balance_adjustments (account_id, date, amount, type, note)
           VALUES (?, ?, ?, ?, ?)""",
        (account_id, _iso(when), amount, type_, note),
    )
    conn.commit()


# --- Événements (log inviolable / A5) ---------------------------------------
def _log_event(conn: sqlite3.Connection, account_id: int, trade_id: Optional[int],
               event_type: str, when: datetime, payload: Optional[dict] = None) -> None:
    conn.execute(
        """INSERT INTO trade_events (account_id, trade_id, event_type, timestamp, payload)
           VALUES (?, ?, ?, ?, ?)""",
        (account_id, trade_id, event_type, _iso(when),
         json.dumps(payload, ensure_ascii=False) if payload else None),
    )


def load_trade_events(conn: sqlite3.Connection, account_id: int = 1) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM trade_events WHERE account_id = ? ORDER BY id DESC",
        (account_id,)).fetchall()


# --- Trades ------------------------------------------------------------------
def _row_to_trade(r: sqlite3.Row) -> E.Trade:
    return E.Trade(
        id=r["id"], instrument=r["instrument"], market=r["market"],
        direction=r["direction"], status=r["status"],
        opened_at=_parse_dt(r["opened_at"]), closed_at=_parse_dt(r["closed_at"]),
        trading_day=_parse_date(r["trading_day"]),
        planned_risk_pct=r["planned_risk_pct"], planned_risk_amount=r["planned_risk_amount"],
        planned_risk_R=r["planned_risk_R"], entry_price=r["entry_price"],
        stop_price=r["stop_price"], take_profit=r["take_profit"], size=r["size"],
        realized_pnl_amount=r["realized_pnl_amount"], realized_R=r["realized_R"],
        outcome=r["outcome"], emotion_tag=r["emotion_tag"], note=r["note"],
        setup=r["setup"], thesis=r["thesis"], external_id=r["external_id"],
    )


def load_trades(conn: sqlite3.Connection, account_id: Optional[int] = None,
                status: Optional[str] = None) -> list[E.Trade]:
    clauses, params = [], []
    if account_id is not None:
        clauses.append("account_id = ?")
        params.append(account_id)
    if status:
        clauses.append("status = ?")
        params.append(status)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    rows = conn.execute(f"SELECT * FROM trades{where} ORDER BY opened_at", params).fetchall()
    return [_row_to_trade(r) for r in rows]


def open_trade(conn: sqlite3.Connection, account: E.Account, instrument: str,
               market: str, direction: str, risk_pct: float, now: datetime,
               entry_price: Optional[float] = None, stop_price: Optional[float] = None,
               take_profit: Optional[float] = None, size: Optional[float] = None,
               emotion_tag: Optional[str] = None, note: Optional[str] = None,
               setup: Optional[str] = None, thesis: Optional[str] = None,
               external_id: Optional[str] = None) -> int:
    """Insère un trade OPEN pour `account`. `risk_pct` = fraction du capital (0.01 = 1%)."""
    trades = load_trades(conn, account_id=account.id)
    adjustments = load_adjustments(conn, account_id=account.id)
    dsb = E.day_start_balance(account, trades, adjustments, now)
    amount = dsb * risk_pct
    risk_R = risk_pct / account.one_R_pct if account.one_R_pct else 0.0
    tday = trading_day_of(now, account.timezone, account.reset_hour)

    cur = conn.execute(
        """INSERT INTO trades (account_id, external_id, instrument, market, direction,
           status, opened_at, trading_day, planned_risk_pct, planned_risk_amount,
           planned_risk_R, entry_price, stop_price, take_profit, size, emotion_tag,
           note, setup, thesis)
           VALUES (?, ?, ?, ?, ?, 'OPEN', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (account.id, external_id, instrument, market, direction, _iso(now),
         tday.isoformat(), risk_pct, amount, risk_R, entry_price, stop_price,
         take_profit, size, emotion_tag, note, setup, thesis),
    )
    tid = DB.last_insert_id(conn, cur)
    _log_event(conn, account.id, tid, "OPEN", now,
               {"instrument": instrument, "risk_pct": risk_pct, "risk_amount": amount,
                "direction": direction, "emotion": emotion_tag, "setup": setup})
    conn.commit()
    return tid


def insert_synced_open(conn: sqlite3.Connection, account_id: int, external_id: str,
                       instrument: str, direction: str, opened_at: datetime,
                       trading_day, risk_pct: float, risk_amount: float, risk_R: float,
                       entry_price, stop_price, take_profit, size, now: datetime,
                       market: str = "FOREX") -> int:
    """Insère un trade OPEN importé du broker (risque pré-calculé depuis le SL)."""
    cur = conn.execute(
        """INSERT INTO trades (account_id, external_id, instrument, market, direction,
           status, opened_at, trading_day, planned_risk_pct, planned_risk_amount,
           planned_risk_R, entry_price, stop_price, take_profit, size)
           VALUES (?, ?, ?, ?, ?, 'OPEN', ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (account_id, external_id, instrument, market, direction, _iso(opened_at),
         trading_day.isoformat(), risk_pct, risk_amount, risk_R, entry_price,
         stop_price, take_profit, size),
    )
    tid = DB.last_insert_id(conn, cur)
    _log_event(conn, account_id, tid, "SYNC", now,
               {"external_id": external_id, "action": "open", "risk_amount": risk_amount})
    conn.commit()
    return tid


def update_synced_open(conn: sqlite3.Connection, trade_id: int, account_id: int,
                       risk_pct: float, risk_amount: float, risk_R: float,
                       stop_price, now: datetime) -> None:
    """Met à jour le risque d'une position ouverte re-synchronisée (SL modifié)."""
    conn.execute(
        """UPDATE trades SET planned_risk_pct=?, planned_risk_amount=?, planned_risk_R=?,
           stop_price=? WHERE id=?""",
        (risk_pct, risk_amount, risk_R, stop_price, trade_id),
    )
    _log_event(conn, account_id, trade_id, "SYNC", now,
               {"action": "update", "risk_amount": risk_amount})
    conn.commit()


def close_trade(conn: sqlite3.Connection, trade_id: int, realized_pnl_amount: float,
                now: datetime) -> None:
    r = conn.execute(
        "SELECT account_id, planned_risk_amount FROM trades WHERE id=?", (trade_id,)
    ).fetchone()
    account_id = r["account_id"] if r else 1
    risk = r["planned_risk_amount"] if r else 0.0
    realized_R = realized_pnl_amount / risk if risk else 0.0
    outcome = ("WIN" if realized_pnl_amount > 1e-9
               else "LOSS" if realized_pnl_amount < -1e-9 else "BREAKEVEN")
    conn.execute(
        """UPDATE trades SET status='CLOSED', closed_at=?, realized_pnl_amount=?,
           realized_R=?, outcome=? WHERE id=?""",
        (_iso(now), realized_pnl_amount, realized_R, outcome, trade_id),
    )
    _log_event(conn, account_id, trade_id, "CLOSE", now,
               {"pnl": realized_pnl_amount, "R": realized_R, "outcome": outcome})
    conn.commit()


def cancel_trade(conn: sqlite3.Connection, trade_id: int, now: datetime) -> None:
    r = conn.execute("SELECT account_id FROM trades WHERE id=?", (trade_id,)).fetchone()
    account_id = r["account_id"] if r else 1
    conn.execute("UPDATE trades SET status='CANCELLED' WHERE id=?", (trade_id,))
    _log_event(conn, account_id, trade_id, "CANCEL", now)
    conn.commit()


# --- Journal d'alertes -------------------------------------------------------
def log_alert(conn: sqlite3.Connection, rule_type: str, level: str, when: datetime,
              context: str = "", account_id: int = 1) -> None:
    conn.execute(
        """INSERT INTO alerts_log (account_id, timestamp, rule_type, level, context)
           VALUES (?, ?, ?, ?, ?)""",
        (account_id, _iso(when), rule_type, level, context),
    )
    conn.commit()


def load_alerts(conn: sqlite3.Connection, account_id: int = 1) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM alerts_log WHERE account_id = ? ORDER BY timestamp DESC",
        (account_id,)).fetchall()


# --- Checklist pré-trade (A4) ------------------------------------------------
def load_checklist(conn: sqlite3.Connection, account_id: int = 1,
                   only_enabled: bool = False) -> list[sqlite3.Row]:
    where = "account_id = ?" + (" AND enabled = 1" if only_enabled else "")
    return conn.execute(
        f"SELECT * FROM checklist_items WHERE {where} ORDER BY position, id",
        (account_id,)).fetchall()


def add_checklist_item(conn: sqlite3.Connection, account_id: int, label: str) -> int:
    pos = conn.execute(
        "SELECT COALESCE(MAX(position), -1) + 1 AS p FROM checklist_items WHERE account_id = ?",
        (account_id,)).fetchone()["p"]
    cur = conn.execute(
        "INSERT INTO checklist_items (account_id, label, enabled, position) VALUES (?, ?, 1, ?)",
        (account_id, label, pos))
    rid = DB.last_insert_id(conn, cur)
    conn.commit()
    return rid


def set_checklist_item(conn: sqlite3.Connection, item_id: int,
                       enabled: Optional[bool] = None, label: Optional[str] = None) -> None:
    if enabled is not None:
        conn.execute("UPDATE checklist_items SET enabled=? WHERE id=?",
                     (int(enabled), item_id))
    if label is not None:
        conn.execute("UPDATE checklist_items SET label=? WHERE id=?", (label, item_id))
    conn.commit()


def delete_checklist_item(conn: sqlite3.Connection, item_id: int) -> None:
    conn.execute("DELETE FROM checklist_items WHERE id=?", (item_id,))
    conn.commit()


# --- Config de détection de tilt (C1) ----------------------------------------
def load_tilt_config(conn: sqlite3.Connection, account_id: int = 1) -> B.TiltConfig:
    r = conn.execute("SELECT * FROM tilt_config WHERE account_id = ?",
                     (account_id,)).fetchone()
    if r is None:
        return B.TiltConfig()
    return B.TiltConfig(
        min_gap_minutes=r["min_gap_minutes"],
        reentry_window_minutes=r["reentry_window_minutes"],
        escalation_ratio=r["escalation_ratio"],
        emotion_threshold=r["emotion_threshold"],
        overtrade_count=r["overtrade_count"],
        vigilance_threshold=r["vigilance_threshold"],
        tilt_threshold=r["tilt_threshold"],
    )


def save_tilt_config(conn: sqlite3.Connection, account_id: int, cfg: B.TiltConfig) -> None:
    conn.execute(
        """UPDATE tilt_config SET min_gap_minutes=?, reentry_window_minutes=?,
           escalation_ratio=?, emotion_threshold=?, overtrade_count=?,
           vigilance_threshold=?, tilt_threshold=? WHERE account_id=?""",
        (cfg.min_gap_minutes, cfg.reentry_window_minutes, cfg.escalation_ratio,
         cfg.emotion_threshold, cfg.overtrade_count, cfg.vigilance_threshold,
         cfg.tilt_threshold, account_id),
    )
    conn.commit()
