"""Calculateur de taille de position.

À partir d'un montant de risque (déjà exprimé en devise du compte) et d'une
distance au stop, calcule la taille de position :
- Forex : en lots (contrat standard de 100 000 unités).
- BRVM / actions : en nombre d'actions.

Hypothèse de simplicité (V1) : la devise de cotation = la devise du compte, sauf
si un `conversion_rate` explicite est fourni. La conversion FX automatique complète
est hors scope (cf. SPEC §9).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from . import constants as C

FOREX_CONTRACT_SIZE = 100_000


def pip_size(pair: str) -> float:
    """Taille d'un pip : 0.01 pour les paires en JPY, 0.0001 sinon."""
    return 0.01 if "JPY" in pair.upper() else 0.0001


@dataclass
class SizingResult:
    market: str
    risk_amount: float          # risque en devise du compte
    distance: float             # |entrée - stop| en prix
    units: float                # unités de sous-jacent (quote ccy)
    size: float                 # lots (forex) ou actions (BRVM/autre)
    size_unit: str              # "lots" | "actions"
    distance_pips: Optional[float]
    pip_value_per_lot: Optional[float]  # valeur d'un pip pour 1 lot (devise compte)
    note: str = ""


def size_position(market: str, risk_amount: float, entry: float, stop: float,
                  pair: str = "", contract_size: int = FOREX_CONTRACT_SIZE,
                  conversion_rate: float = 1.0) -> SizingResult:
    """Calcule la taille de position.

    `risk_amount` : montant risqué en devise du compte.
    `conversion_rate` : 1 unité de devise de cotation = `conversion_rate` unités de
    devise du compte (défaut 1.0 = même devise).
    """
    distance = abs(entry - stop)
    if distance <= 0:
        raise ValueError("La distance entrée/stop doit être strictement positive.")
    if conversion_rate <= 0:
        raise ValueError("Le taux de conversion doit être strictement positif.")

    # Perte tolérée exprimée en devise de cotation.
    quote_risk = risk_amount / conversion_rate
    units = quote_risk / distance

    if market == "FOREX":
        lots = units / contract_size
        ps = pip_size(pair)
        distance_pips = distance / ps
        pip_value_per_lot = contract_size * ps * conversion_rate  # en devise compte
        note = ("Hypothèse : devise de cotation = devise du compte "
                if conversion_rate == 1.0 else f"Conversion appliquée : {conversion_rate}. ")
        return SizingResult(market, risk_amount, distance, units, lots, "lots",
                            distance_pips, pip_value_per_lot, note)

    # BRVM / actions / autre : 1 unité = 1 action.
    return SizingResult(market, risk_amount, distance, units, units, "actions",
                        None, None, "Nombre d'actions = risque / distance au stop.")
