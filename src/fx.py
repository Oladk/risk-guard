"""Conversion multi-devises (A2).

`convert` est pur (testable). Les taux sont stockés dans `fx_rates` (saisie manuelle,
fetch optionnel plus tard). Un taux `from->to` sert aussi en sens inverse (1/taux)
tant que le sens direct n'est pas défini.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Optional

from .time_utils import UTC, _as_aware_utc

Rates = dict[tuple[str, str], float]


def convert(amount: float, from_ccy: str, to_ccy: str, rates: Rates) -> float:
    """Convertit `amount` de `from_ccy` vers `to_ccy`. Lève ValueError si aucun taux."""
    if from_ccy == to_ccy:
        return amount
    direct = rates.get((from_ccy, to_ccy))
    if direct is not None:
        return amount * direct
    inverse = rates.get((to_ccy, from_ccy))
    if inverse:
        return amount / inverse
    raise ValueError(f"Taux de conversion {from_ccy}->{to_ccy} introuvable.")


def try_convert(amount: float, from_ccy: str, to_ccy: str,
                rates: Rates) -> Optional[float]:
    try:
        return convert(amount, from_ccy, to_ccy, rates)
    except ValueError:
        return None


# --- Stockage ----------------------------------------------------------------
def load_rates(conn: sqlite3.Connection) -> Rates:
    rows = conn.execute("SELECT from_ccy, to_ccy, rate FROM fx_rates").fetchall()
    return {(r["from_ccy"], r["to_ccy"]): r["rate"] for r in rows}


def set_rate(conn: sqlite3.Connection, from_ccy: str, to_ccy: str, rate: float,
             when: Optional[datetime] = None) -> None:
    when = when or datetime.now(tz=UTC)
    conn.execute(
        """INSERT INTO fx_rates (from_ccy, to_ccy, rate, updated_at) VALUES (?, ?, ?, ?)
           ON CONFLICT(from_ccy, to_ccy)
           DO UPDATE SET rate=excluded.rate, updated_at=excluded.updated_at""",
        (from_ccy.upper(), to_ccy.upper(), rate, _as_aware_utc(when).isoformat()),
    )
    conn.commit()


def get_rate(conn: sqlite3.Connection, from_ccy: str, to_ccy: str) -> Optional[float]:
    """Taux effectif from->to (direct, inverse, ou 1.0 si identique)."""
    return try_convert(1.0, from_ccy.upper(), to_ccy.upper(), load_rates(conn))
