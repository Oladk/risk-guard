"""Moteur de risque — le cœur de l'outil.

Fonctions *pures* : elles prennent un instantané (compte, règles, trades,
ajustements) + `now`, et renvoient un état de risque. Aucune dépendance à la
base de données → entièrement testable avec `pytest`.

Convention : tous les montants sont en devise du compte. L'affichage en % ou en
R se fait via des helpers (`amount_to_pct`, `amount_to_r`).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional

from . import constants as C
from . import time_utils as T


# ---------------------------------------------------------------------------
# Structures de données (miroir des tables, mais découplées de SQLite)
# ---------------------------------------------------------------------------
@dataclass
class Account:
    base_currency: str
    initial_balance: float
    timezone: str
    reset_hour: int
    week_start: str
    warning_threshold_pct: float
    preferred_unit: str
    one_R_pct: float
    sound_enabled: bool = True
    notify_enabled: bool = False
    id: int = 1
    name: str = "Compte principal"
    kind: str = "MANUAL"
    mt5_login: Optional[int] = None
    mt5_server: str = ""
    mt5_path: str = ""
    enforce_enabled: bool = False


@dataclass
class Rule:
    rule_type: str
    enabled: bool
    threshold_value: float
    threshold_unit: str  # PCT | R | COUNT
    action: str = "BLOCK"  # BLOCK | WARN


@dataclass
class Adjustment:
    date: datetime  # UTC
    amount: float  # signé (+ dépôt, - retrait)
    type: str = "DEPOSIT"


@dataclass
class Trade:
    id: Optional[int]
    instrument: str
    market: str
    direction: str
    status: str
    opened_at: datetime
    planned_risk_pct: float
    planned_risk_amount: float
    planned_risk_R: float
    closed_at: Optional[datetime] = None
    trading_day: Optional[date] = None
    entry_price: Optional[float] = None
    stop_price: Optional[float] = None
    take_profit: Optional[float] = None
    size: Optional[float] = None
    realized_pnl_amount: Optional[float] = None
    realized_R: Optional[float] = None
    outcome: Optional[str] = None
    emotion_tag: Optional[str] = None
    note: Optional[str] = None
    setup: Optional[str] = None
    thesis: Optional[str] = None
    external_id: Optional[str] = None


# ---------------------------------------------------------------------------
# Résultats
# ---------------------------------------------------------------------------
@dataclass
class RuleState:
    rule_type: str
    label: str
    level: str  # OK | WARN | BLOCK (sévérité visuelle, selon le ratio)
    consumed: float  # montant consommé (ou compte)
    limit: float  # seuil (montant ou compte)
    ratio: Optional[float]  # consumed / limit (None si non pertinent)
    is_money: bool
    locks_globally: bool
    unlock_at: Optional[datetime]
    message: str
    action: str = "BLOCK"  # BLOCK (mode strict) | WARN (conseil) — défini par la règle


@dataclass
class RiskState:
    now: datetime
    day_start_balance: float
    week_start_balance: float
    realized_pnl_today: float
    realized_pnl_week: float
    open_risk: float
    worst_case_drawdown_today: float
    locked: bool
    global_level: str  # OK | WARN | BLOCK
    unlock_at: Optional[datetime]  # plus proche reset parmi les règles verrouillantes
    rule_states: list[RuleState] = field(default_factory=list)

    def blocking_rules(self) -> list[RuleState]:
        return [r for r in self.rule_states if r.level == C.LEVEL_BLOCK]

    def warning_rules(self) -> list[RuleState]:
        return [r for r in self.rule_states if r.level == C.LEVEL_WARN]


@dataclass
class CheckResult:
    # Violations de règles en mode strict (BLOCK) → le trade est refusé.
    blocking: list[tuple[str, str]] = field(default_factory=list)
    # Violations de règles en mode conseil (WARN) → alerte forte, mais trade autorisé.
    advisories: list[tuple[str, str]] = field(default_factory=list)

    @property
    def allowed(self) -> bool:
        return len(self.blocking) == 0

    @property
    def has_alerts(self) -> bool:
        return bool(self.blocking or self.advisories)


# ---------------------------------------------------------------------------
# Agrégats de base
# ---------------------------------------------------------------------------
def _active(trades: list[Trade]) -> list[Trade]:
    return [t for t in trades if t.status != C.STATUS_CANCELLED]


def realized_pnl_in_window(trades: list[Trade], start: datetime, end: datetime) -> float:
    total = 0.0
    for t in trades:
        if t.status == C.STATUS_CLOSED and T.in_window(t.closed_at, start, end):
            total += t.realized_pnl_amount or 0.0
    return total


def realized_pnl_before(trades: list[Trade], moment: datetime) -> float:
    """P&L réalisé de tous les trades clôturés strictement avant `moment`."""
    total = 0.0
    for t in trades:
        if t.status == C.STATUS_CLOSED and t.closed_at is not None:
            if T._as_aware_utc(t.closed_at) < moment:
                total += t.realized_pnl_amount or 0.0
    return total


def adjustments_before(adjustments: list[Adjustment], moment: datetime) -> float:
    total = 0.0
    for a in adjustments:
        if T._as_aware_utc(a.date) < moment:
            total += a.amount
    return total


def open_risk_amount(trades: list[Trade]) -> float:
    return sum(t.planned_risk_amount for t in trades if t.status == C.STATUS_OPEN)


def trades_opened_in_window(trades: list[Trade], start: datetime, end: datetime) -> int:
    return sum(1 for t in _active(trades) if T.in_window(t.opened_at, start, end))


def consecutive_losses(trades: list[Trade], start: datetime, end: datetime) -> int:
    """Pertes consécutives parmi les trades clôturés dans [start, end),
    en partant du plus récent. Un WIN ou BREAKEVEN interrompt la série."""
    closed = [
        t for t in trades
        if t.status == C.STATUS_CLOSED and T.in_window(t.closed_at, start, end)
    ]
    closed.sort(key=lambda t: T._as_aware_utc(t.closed_at), reverse=True)
    streak = 0
    for t in closed:
        if t.outcome == "LOSS":
            streak += 1
        else:
            break
    return streak


def day_start_balance(account: Account, trades: list[Trade],
                      adjustments: list[Adjustment], now: datetime) -> float:
    start, _ = T.trading_day_bounds(now, account.timezone, account.reset_hour)
    return (account.initial_balance
            + adjustments_before(adjustments, start)
            + realized_pnl_before(trades, start))


def week_start_balance(account: Account, trades: list[Trade],
                       adjustments: list[Adjustment], now: datetime) -> float:
    start, _ = T.week_bounds(now, account.timezone, account.week_start)
    return (account.initial_balance
            + adjustments_before(adjustments, start)
            + realized_pnl_before(trades, start))


# ---------------------------------------------------------------------------
# Conversions d'unités
# ---------------------------------------------------------------------------
def threshold_amount(rule: Rule, base_balance: float, one_R_pct: float) -> float:
    """Convertit le seuil d'une règle monétaire en montant devise."""
    if rule.threshold_unit == C.UNIT_PCT:
        return base_balance * rule.threshold_value
    if rule.threshold_unit == C.UNIT_R:
        return base_balance * (rule.threshold_value * one_R_pct)
    return rule.threshold_value  # COUNT : renvoyé tel quel


def amount_to_pct(amount: float, base_balance: float) -> float:
    return amount / base_balance if base_balance else 0.0


def amount_to_r(amount: float, base_balance: float, one_R_pct: float) -> float:
    if not base_balance or not one_R_pct:
        return 0.0
    return (amount / base_balance) / one_R_pct


def format_amount(amount: float, account: Account, base_balance: float) -> str:
    """Formate un montant selon l'unité préférée (PCT ou R)."""
    if account.preferred_unit == C.UNIT_R:
        return f"{amount_to_r(amount, base_balance, account.one_R_pct):+.2f}R"
    return f"{amount_to_pct(amount, base_balance) * 100:+.2f}%"


# ---------------------------------------------------------------------------
# Évaluation de l'état de risque
# ---------------------------------------------------------------------------
def _level_from_ratio(ratio: float, warn: float) -> str:
    if ratio >= 1.0:
        return C.LEVEL_BLOCK
    if ratio >= warn:
        return C.LEVEL_WARN
    return C.LEVEL_OK


def evaluate(account: Account, rules: list[Rule], trades: list[Trade],
             adjustments: list[Adjustment], now: datetime) -> RiskState:
    """Calcule l'état de risque courant (jauges + verrou STOP)."""
    warn = account.warning_threshold_pct
    day_start, day_end = T.trading_day_bounds(now, account.timezone, account.reset_hour)
    week_start, week_end = T.week_bounds(now, account.timezone, account.week_start)

    dsb = day_start_balance(account, trades, adjustments, now)
    wsb = week_start_balance(account, trades, adjustments, now)
    realized_today = realized_pnl_in_window(trades, day_start, day_end)
    realized_week = realized_pnl_in_window(trades, week_start, week_end)
    open_risk = open_risk_amount(trades)
    worst_case = open_risk - realized_today

    daily_reset = T.next_daily_reset(now, account.timezone, account.reset_hour)
    weekly_reset = T.next_weekly_reset(now, account.timezone, account.week_start)

    states: list[RuleState] = []
    enabled = {r.rule_type: r for r in rules if r.enabled}

    for rule_type, rule in enabled.items():
        locks = rule_type in C.GLOBAL_LOCK_RULES
        label = C.RULE_LABELS.get(rule_type, rule_type)

        if rule_type == C.RULE_DAILY_LOSS:
            L = threshold_amount(rule, dsb, account.one_R_pct)
            consumed = worst_case
            ratio = consumed / L if L > 0 else 0.0
            level = _level_from_ratio(ratio, warn) if consumed > 0 else C.LEVEL_OK
            states.append(RuleState(rule_type, label, level, consumed, L, max(ratio, 0.0),
                                    True, locks, daily_reset,
                                    _msg_loss(consumed, L, dsb, account)))

        elif rule_type == C.RULE_WEEKLY_LOSS:
            L = threshold_amount(rule, wsb, account.one_R_pct)
            consumed = open_risk - realized_week
            ratio = consumed / L if L > 0 else 0.0
            level = _level_from_ratio(ratio, warn) if consumed > 0 else C.LEVEL_OK
            states.append(RuleState(rule_type, label, level, consumed, L, max(ratio, 0.0),
                                    True, locks, weekly_reset,
                                    _msg_loss(consumed, L, wsb, account)))

        elif rule_type == C.RULE_MAX_OPEN_EXPOSURE:
            L = threshold_amount(rule, dsb, account.one_R_pct)
            consumed = open_risk
            ratio = consumed / L if L > 0 else 0.0
            level = _level_from_ratio(ratio, warn)
            states.append(RuleState(rule_type, label, level, consumed, L, ratio,
                                    True, locks, None,
                                    f"Risque ouvert {format_amount(consumed, account, dsb)} "
                                    f"/ max {format_amount(L, account, dsb)} (se libère à la clôture)"))

        elif rule_type == C.RULE_DAILY_PROFIT_TARGET:
            target = threshold_amount(rule, dsb, account.one_R_pct)
            consumed = realized_today
            ratio = consumed / target if target > 0 else 0.0
            level = _level_from_ratio(ratio, warn) if consumed > 0 else C.LEVEL_OK
            states.append(RuleState(rule_type, label, level, consumed, target, max(ratio, 0.0),
                                    True, locks, daily_reset,
                                    f"Gain du jour {format_amount(consumed, account, dsb)} "
                                    f"/ objectif {format_amount(target, account, dsb)}"))

        elif rule_type == C.RULE_MAX_CONSECUTIVE_LOSSES:
            N = int(rule.threshold_value)
            streak = consecutive_losses(trades, day_start, day_end)
            level = (C.LEVEL_BLOCK if streak >= N
                     else C.LEVEL_WARN if streak >= max(N - 1, 1) and streak > 0
                     else C.LEVEL_OK)
            ratio = streak / N if N > 0 else 0.0
            states.append(RuleState(rule_type, label, level, streak, N, ratio,
                                    False, locks, daily_reset,
                                    f"{streak} perte(s) consécutive(s) / max {N}"))

        elif rule_type == C.RULE_MAX_TRADES_DAY:
            N = int(rule.threshold_value)
            count = trades_opened_in_window(trades, day_start, day_end)
            level = (C.LEVEL_BLOCK if count >= N
                     else C.LEVEL_WARN if count >= max(N - 1, 1) and count > 0
                     else C.LEVEL_OK)
            ratio = count / N if N > 0 else 0.0
            states.append(RuleState(rule_type, label, level, count, N, ratio,
                                    False, locks, daily_reset,
                                    f"{count} trade(s) aujourd'hui / max {N}"))

        elif rule_type == C.RULE_PER_TRADE_RISK:
            L = threshold_amount(rule, dsb, account.one_R_pct)
            states.append(RuleState(rule_type, label, C.LEVEL_OK, 0.0, L, None,
                                    True, False, None,
                                    f"Risque max par trade : {format_amount(L, account, dsb)}"))

    # Reporte l'action de chaque règle sur son état.
    for s in states:
        s.action = enabled[s.rule_type].action

    # Le verrou (mode strict) ne s'active QUE pour des règles en action BLOCK.
    def _locks(s: RuleState) -> bool:
        return s.level == C.LEVEL_BLOCK and s.locks_globally and s.action == "BLOCK"

    locked = any(_locks(s) for s in states)
    global_level = C.LEVEL_OK
    if any(s.level == C.LEVEL_BLOCK for s in states):
        global_level = C.LEVEL_BLOCK
    elif any(s.level == C.LEVEL_WARN for s in states):
        global_level = C.LEVEL_WARN

    lock_times = [s.unlock_at for s in states if _locks(s) and s.unlock_at]
    unlock_at = min(lock_times) if lock_times else None

    return RiskState(
        now=now, day_start_balance=dsb, week_start_balance=wsb,
        realized_pnl_today=realized_today, realized_pnl_week=realized_week,
        open_risk=open_risk, worst_case_drawdown_today=worst_case,
        locked=locked, global_level=global_level, unlock_at=unlock_at,
        rule_states=states,
    )


def _msg_loss(consumed: float, limit: float, base: float, account: Account) -> str:
    pct = amount_to_pct(consumed, base) * 100
    lim_pct = amount_to_pct(limit, base) * 100
    return f"Perte potentielle {pct:.2f}% / limite {lim_pct:.2f}%"


# ---------------------------------------------------------------------------
# Contrôle à l'ouverture d'un nouveau trade
# ---------------------------------------------------------------------------
def check_new_trade(account: Account, rules: list[Rule], trades: list[Trade],
                    adjustments: list[Adjustment], now: datetime,
                    new_risk_amount: float) -> CheckResult:
    """Décide si un nouveau trade risquant `new_risk_amount` peut être ouvert."""
    day_start, day_end = T.trading_day_bounds(now, account.timezone, account.reset_hour)
    week_start, week_end = T.week_bounds(now, account.timezone, account.week_start)

    dsb = day_start_balance(account, trades, adjustments, now)
    wsb = week_start_balance(account, trades, adjustments, now)
    realized_today = realized_pnl_in_window(trades, day_start, day_end)
    realized_week = realized_pnl_in_window(trades, week_start, week_end)
    open_risk = open_risk_amount(trades)

    violations: list[tuple[str, str]] = []
    enabled = {r.rule_type: r for r in rules if r.enabled}

    for rule_type, rule in enabled.items():
        if rule_type == C.RULE_PER_TRADE_RISK:
            L = threshold_amount(rule, dsb, account.one_R_pct)
            if new_risk_amount > L + 1e-9:
                violations.append((rule_type,
                    f"Risque du trade {amount_to_pct(new_risk_amount, dsb)*100:.2f}% "
                    f"> max autorisé {amount_to_pct(L, dsb)*100:.2f}% par trade."))

        elif rule_type == C.RULE_DAILY_LOSS:
            L = threshold_amount(rule, dsb, account.one_R_pct)
            projected = (open_risk + new_risk_amount) - realized_today
            if projected >= L - 1e-9:
                violations.append((rule_type,
                    f"Ce trade porterait la perte potentielle du jour à "
                    f"{amount_to_pct(projected, dsb)*100:.2f}% ≥ limite "
                    f"{amount_to_pct(L, dsb)*100:.2f}%."))

        elif rule_type == C.RULE_WEEKLY_LOSS:
            L = threshold_amount(rule, wsb, account.one_R_pct)
            projected = (open_risk + new_risk_amount) - realized_week
            if projected >= L - 1e-9:
                violations.append((rule_type,
                    f"Ce trade porterait la perte potentielle de la semaine à "
                    f"{amount_to_pct(projected, wsb)*100:.2f}% ≥ limite "
                    f"{amount_to_pct(L, wsb)*100:.2f}%."))

        elif rule_type == C.RULE_MAX_OPEN_EXPOSURE:
            L = threshold_amount(rule, dsb, account.one_R_pct)
            projected = open_risk + new_risk_amount
            if projected > L + 1e-9:
                violations.append((rule_type,
                    f"Ce trade porterait le risque ouvert total à "
                    f"{amount_to_pct(projected, dsb)*100:.2f}% > max "
                    f"{amount_to_pct(L, dsb)*100:.2f}%."))

        elif rule_type == C.RULE_MAX_TRADES_DAY:
            N = int(rule.threshold_value)
            count = trades_opened_in_window(trades, day_start, day_end)
            if count >= N:
                violations.append((rule_type,
                    f"Limite de {N} trade(s) par jour déjà atteinte ({count})."))

        elif rule_type == C.RULE_MAX_CONSECUTIVE_LOSSES:
            N = int(rule.threshold_value)
            streak = consecutive_losses(trades, day_start, day_end)
            if streak >= N:
                violations.append((rule_type,
                    f"{streak} pertes consécutives : limite de {N} atteinte. "
                    f"Pause jusqu'au prochain reset."))

        elif rule_type == C.RULE_DAILY_PROFIT_TARGET:
            target = threshold_amount(rule, dsb, account.one_R_pct)
            if realized_today >= target - 1e-9:
                violations.append((rule_type,
                    f"Objectif de gain du jour atteint "
                    f"({amount_to_pct(realized_today, dsb)*100:.2f}%). Stop-win : on s'arrête."))

    # Route chaque violation selon l'action de la règle : BLOCK = strict (refus),
    # WARN = conseil (alerte forte mais trade autorisé).
    blocking, advisories = [], []
    for rule_type, msg in violations:
        if enabled[rule_type].action == "BLOCK":
            blocking.append((rule_type, msg))
        else:
            advisories.append((rule_type, msg))
    return CheckResult(blocking=blocking, advisories=advisories)
