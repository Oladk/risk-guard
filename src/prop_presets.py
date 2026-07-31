"""Presets de règles de challenges prop-firm — la fondation du repositionnement.

Un challenge prop-firm = un compte à passer sans enfreindre des règles de risque
(perte journalière max, drawdown total max, objectif de profit, jours minimum).
Ces règles mappent presque 1:1 sur le moteur de Vigie. Ce module fournit une
bibliothèque de presets pour pré-remplir les limites selon la firme et la phase.

⚠️ AVERTISSEMENT : les conditions des firmes changent souvent et varient selon le
type de compte. Ces presets sont des **points de départ courants** — l'utilisateur
DOIT confirmer les chiffres exacts avec sa firme avant de s'y fier. Les modèles
« génériques » couvrent les structures habituelles quand la firme précise diffère.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class PropPreset:
    """Un preset de challenge. Les pourcentages sont en décimal (0.05 = 5 %)."""
    key: str
    firm: str                       # nom de la firme (vide pour un modèle générique)
    plan: str                       # ex. "2 étapes · Phase 1"
    daily_loss_pct: float           # perte journalière max
    max_loss_pct: float             # drawdown total max (échec du challenge)
    profit_target_pct: Optional[float]  # objectif de profit (None = compte financé)
    min_trading_days: int           # nombre minimum de jours de trading
    drawdown_type: str              # "static" (depuis le solde initial) | "trailing" (depuis le pic)
    note: str = ""

    @property
    def label(self) -> str:
        return f"{self.firm} — {self.plan}" if self.firm else self.plan

    def summary(self) -> str:
        tgt = "aucun (financé)" if self.profit_target_pct is None else f"{self.profit_target_pct*100:.0f} %"
        dd = {"static": "statique (solde initial)", "trailing": "trailing (pic d'equity)"}[self.drawdown_type]
        return (f"Perte/jour {self.daily_loss_pct*100:.0f} % · Drawdown max {self.max_loss_pct*100:.0f} % "
                f"({dd}) · Objectif {tgt} · min {self.min_trading_days} j")


# Bibliothèque. FTMO = conditions publiques stables et très documentées ; les
# « Modèle … » couvrent les structures génériques (1 étape, trailing, financé).
_PRESETS = [
    PropPreset("ftmo_p1", "FTMO", "2 étapes · Phase 1 (Challenge)",
               0.05, 0.10, 0.10, 0, "static",
               "Perte journalière calculée sur l'equity ; drawdown max sur le solde initial."),
    PropPreset("ftmo_p2", "FTMO", "2 étapes · Phase 2 (Verification)",
               0.05, 0.10, 0.05, 0, "static",
               "Même risque, objectif réduit de moitié."),
    PropPreset("ftmo_funded", "FTMO", "Compte financé",
               0.05, 0.10, None, 0, "static",
               "Plus d'objectif : il s'agit de garder le compte en respectant le drawdown."),
    PropPreset("gen_2step_p1", "", "Modèle 2 étapes · Phase 1",
               0.05, 0.10, 0.08, 3, "static",
               "Structure la plus répandue. Objectif souvent 8–10 %."),
    PropPreset("gen_1step", "", "Modèle 1 étape (drawdown statique)",
               0.04, 0.08, 0.10, 0, "static",
               "Une seule phase, limites plus serrées."),
    PropPreset("gen_trailing", "", "Modèle drawdown trailing (instant / 1 étape)",
               0.05, 0.06, 0.08, 0, "trailing",
               "Le drawdown suit le pic d'equity : plus dangereux quand on est en profit."),
    PropPreset("custom", "", "Personnalisé",
               0.05, 0.10, 0.08, 0, "static",
               "Saisis les chiffres exacts de ton compte."),
]

PRESETS = {p.key: p for p in _PRESETS}


def names() -> list[tuple[str, str]]:
    """(key, label) dans l'ordre d'affichage."""
    return [(p.key, p.label) for p in _PRESETS]


def get(key: str) -> PropPreset:
    return PRESETS[key]
