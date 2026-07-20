"""Façade applicative : connexion + évaluation de l'état de risque en un appel.

Multi-comptes : `evaluate_now` prend un `account_id` (défaut 1). `now` reste le
2e argument positionnel pour ne casser aucun appel existant.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Optional

from . import db as DB
from . import repository as R
from . import risk_engine as E
from . import time_utils as T


def connect() -> sqlite3.Connection:
    conn = DB.get_conn()
    DB.init_db(conn)
    return conn


def evaluate_now(conn: sqlite3.Connection, now: Optional[datetime] = None,
                 account_id: int = 1):
    """Renvoie (account, rules, trades, adjustments, risk_state, now) pour un compte."""
    now = now or T.now_utc()
    account = R.load_account(conn, account_id)
    rules = R.load_rules(conn, account.id)
    trades = R.load_trades(conn, account_id=account.id)
    adjustments = R.load_adjustments(conn, account_id=account.id)
    rs = E.evaluate(account, rules, trades, adjustments, now)
    return account, rules, trades, adjustments, rs, now
