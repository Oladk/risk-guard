"""Exposition ajustée par corrélation (A3).

Le risque ouvert « simple » (somme) reste le garde-fou dur du moteur. Ici on calcule
en plus un **risque effectif** de portefeuille, qui tient compte des corrélations :
- deux longs corrélés positivement → risque proche de la somme,
- positions décorrélées → risque < somme (diversification),
- positions opposées corrélées → compensation partielle.

Formule : sqrt( Σ_i Σ_j wᵢ wⱼ ρᵢⱼ ), avec wᵢ = ±(risque planifié) selon le sens
(long +, short −) et ρ la corrélation (ρ=1 pour le même instrument, 0 si inconnue).
"""

from __future__ import annotations

import math
import sqlite3
from datetime import datetime
from typing import Callable, Optional

from . import constants as C
from .time_utils import UTC, _as_aware_utc

CorrMap = dict[tuple[str, str], float]


def make_lookup(corr_map: CorrMap) -> Callable[[str, str], float]:
    def lookup(a: str, b: str) -> float:
        if a == b:
            return 1.0
        if (a, b) in corr_map:
            return corr_map[(a, b)]
        if (b, a) in corr_map:
            return corr_map[(b, a)]
        return 0.0
    return lookup


def effective_risk(positions: list[tuple[str, str, float]], corr_map: CorrMap) -> float:
    """`positions` : liste de (instrument, direction, risque_planifié)."""
    lookup = make_lookup(corr_map)
    vec = [((1.0 if d == "LONG" else -1.0) * r, instr) for instr, d, r in positions]
    total = 0.0
    for wi, ai in vec:
        for wj, aj in vec:
            total += wi * wj * lookup(ai, aj)
    return math.sqrt(total) if total > 0 else 0.0


def effective_open_risk(trades, corr_map: CorrMap) -> float:
    positions = [(t.instrument, t.direction, t.planned_risk_amount)
                 for t in trades if t.status == C.STATUS_OPEN]
    return effective_risk(positions, corr_map)


# --- Stockage ----------------------------------------------------------------
def load_correlations(conn: sqlite3.Connection) -> CorrMap:
    rows = conn.execute("SELECT instrument_a, instrument_b, corr FROM correlations").fetchall()
    return {(r["instrument_a"], r["instrument_b"]): r["corr"] for r in rows}


def set_correlation(conn: sqlite3.Connection, a: str, b: str, corr: float,
                    when: Optional[datetime] = None) -> None:
    when = when or datetime.now(tz=UTC)
    conn.execute(
        """INSERT INTO correlations (instrument_a, instrument_b, corr, updated_at)
           VALUES (?, ?, ?, ?)
           ON CONFLICT(instrument_a, instrument_b)
           DO UPDATE SET corr=excluded.corr, updated_at=excluded.updated_at""",
        (a.upper(), b.upper(), max(-1.0, min(1.0, corr)), _as_aware_utc(when).isoformat()),
    )
    conn.commit()
