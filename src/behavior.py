"""Intelligence comportementale (Track C).

Fonctions *pures* et *explicables* (pas de boîte noire) sur le flux de trades :
- C1 : détection de tilt en temps réel (ré-entrées, montée de taille, émotions…),
- C2 : statistiques prescriptives (win rate conditionnel, espérance),
- C3 : tailles/limites recommandées data-driven (demi-Kelly plafonné).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from .time_utils import _as_aware_utc, in_window


def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


# ===========================================================================
# C1 — Détection de tilt
# ===========================================================================
@dataclass
class TiltConfig:
    min_gap_minutes: float = 5.0          # ré-entrées rapprochées
    reentry_window_minutes: float = 15.0  # ré-entrée après une perte
    escalation_ratio: float = 1.5         # montée de taille (×)
    emotion_threshold: int = 2            # nb de trades Revenge/FOMO
    overtrade_count: int = 6              # nb de trades/jour
    w_rapid: int = 25
    w_reentry_loss: int = 30
    w_escalation: int = 25
    w_emotion: int = 20
    w_overtrade: int = 15
    vigilance_threshold: int = 25
    tilt_threshold: int = 50


@dataclass
class TiltSignal:
    code: str
    label: str
    detail: str
    weight: int


@dataclass
class TiltAssessment:
    score: int
    level: str  # CALME | VIGILANCE | TILT
    signals: list[TiltSignal] = field(default_factory=list)


def assess_tilt(trades, now: datetime, day_start: datetime, day_end: datetime,
                cfg: Optional[TiltConfig] = None) -> TiltAssessment:
    cfg = cfg or TiltConfig()
    today = sorted([t for t in trades if in_window(t.opened_at, day_start, day_end)],
                   key=lambda t: _as_aware_utc(t.opened_at))
    closed = sorted([t for t in trades if t.status == "CLOSED" and t.closed_at],
                    key=lambda t: _as_aware_utc(t.closed_at))
    signals: list[TiltSignal] = []

    # Ré-entrées rapprochées (les 2 dernières ouvertures du jour)
    if len(today) >= 2:
        gap = (_as_aware_utc(today[-1].opened_at)
               - _as_aware_utc(today[-2].opened_at)).total_seconds() / 60
        if gap < cfg.min_gap_minutes:
            signals.append(TiltSignal("rapid_reentry", "Ré-entrées rapprochées",
                                       f"2 trades en {gap:.0f} min", cfg.w_rapid))

    # Ré-entrée juste après une perte
    if today:
        last = today[-1]
        prior_losses = [t for t in closed if t.outcome == "LOSS"
                        and _as_aware_utc(t.closed_at) <= _as_aware_utc(last.opened_at)]
        if prior_losses:
            gapm = (_as_aware_utc(last.opened_at)
                    - _as_aware_utc(prior_losses[-1].closed_at)).total_seconds() / 60
            if 0 <= gapm < cfg.reentry_window_minutes:
                signals.append(TiltSignal("reentry_after_loss", "Ré-entrée après une perte",
                                          f"nouveau trade {gapm:.0f} min après une perte",
                                          cfg.w_reentry_loss))

    # Montée de taille après une perte
    if len(today) >= 2:
        last, prev = today[-1], today[-2]
        prior_closed = [t for t in closed
                        if _as_aware_utc(t.closed_at) <= _as_aware_utc(last.opened_at)]
        if (last.planned_risk_pct > prev.planned_risk_pct * cfg.escalation_ratio
                and prior_closed and prior_closed[-1].outcome == "LOSS"):
            signals.append(TiltSignal("size_escalation", "Montée de taille après perte",
                                       f"risque {last.planned_risk_pct*100:.2f}% "
                                       f"vs {prev.planned_risk_pct*100:.2f}%", cfg.w_escalation))

    # Fréquence d'émotions à risque
    emo = sum(1 for t in today if (t.emotion_tag or "") in ("Revenge", "FOMO"))
    if emo >= cfg.emotion_threshold:
        signals.append(TiltSignal("emotion", "Émotions à risque",
                                   f"{emo} trades Revenge/FOMO aujourd'hui", cfg.w_emotion))

    # Sur-trading
    if len(today) >= cfg.overtrade_count:
        signals.append(TiltSignal("overtrading", "Sur-trading",
                                   f"{len(today)} trades aujourd'hui", cfg.w_overtrade))

    score = min(100, sum(s.weight for s in signals))
    level = ("TILT" if score >= cfg.tilt_threshold
             else "VIGILANCE" if score >= cfg.vigilance_threshold else "CALME")
    return TiltAssessment(score=score, level=level, signals=signals)


# ===========================================================================
# C2 — Statistiques prescriptives
# ===========================================================================
def _decided(closed) -> list:
    return [t for t in closed if t.outcome in ("WIN", "LOSS")]


def winrate(closed) -> float:
    d = _decided(closed)
    return (sum(1 for t in d if t.outcome == "WIN") / len(d)) if d else 0.0


def expectancy_R(closed) -> float:
    rs = [t.realized_R for t in _decided(closed) if t.realized_R is not None]
    return _mean(rs)


def conditional_winrate_after_loss(closed) -> tuple[Optional[float], float, int]:
    """(win rate après une perte, win rate global, n après perte)."""
    seq = sorted(_decided(closed), key=lambda t: _as_aware_utc(t.closed_at))
    after = [seq[i].outcome == "WIN" for i in range(1, len(seq))
             if seq[i - 1].outcome == "LOSS"]
    wr_overall = _mean([t.outcome == "WIN" for t in seq])
    wr_after = _mean(after) if after else None
    return wr_after, wr_overall, len(after)


# ===========================================================================
# C3 — Tailles / limites recommandées (data-driven)
# ===========================================================================
@dataclass
class Suggestion:
    per_trade_pct: float
    daily_loss_pct: float
    win_rate: float
    payoff: float
    kelly: float
    n: int
    rationale: str


def suggest_limits(closed, min_trades: int = 20, floor_per_trade: float = 0.0025,
                   cap_per_trade: float = 0.02) -> Optional[Suggestion]:
    """Suggère un risque/trade et une perte max journalière depuis l'historique.

    Basé sur le demi-Kelly (fraction de Kelly divisée par 2), plafonné et planché.
    Explicable : f* = W - (1-W)/b, où b = gain moyen (R) / perte moyenne (R)."""
    decided = _decided(closed)
    if len(decided) < min_trades:
        return None
    wins = [t.realized_R for t in decided if t.outcome == "WIN" and t.realized_R is not None]
    losses = [abs(t.realized_R) for t in decided if t.outcome == "LOSS" and t.realized_R is not None]
    W = len(wins) / len(decided)
    avg_win, avg_loss = _mean(wins), _mean(losses)
    if avg_loss <= 0:
        return None
    b = avg_win / avg_loss
    kelly = W - (1 - W) / b if b > 0 else 0.0
    half = max(kelly / 2, 0.0)
    per_trade = min(max(half, floor_per_trade), cap_per_trade)
    daily = min(per_trade * 3, cap_per_trade * 3)
    rationale = (f"WR {W*100:.0f}% · ratio gain/perte {b:.2f}R → Kelly {kelly*100:.1f}%, "
                 f"demi-Kelly plafonné à {cap_per_trade*100:.1f}%.")
    return Suggestion(per_trade_pct=per_trade, daily_loss_pct=daily, win_rate=W,
                      payoff=b, kelly=kelly, n=len(decided), rationale=rationale)
