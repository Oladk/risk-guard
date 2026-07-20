"""Tests du moteur de risque : agrégats, évaluation des 7 règles, contrôle à l'ouverture."""

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from src import constants as C
from src import risk_engine as E

UTC = ZoneInfo("UTC")
NOW = datetime(2026, 7, 7, 12, 0, tzinfo=UTC)  # mardi midi


# --- Helpers -----------------------------------------------------------------
def acct(**kw):
    base = dict(base_currency="USD", initial_balance=10_000.0, timezone="UTC",
                reset_hour=0, week_start="MONDAY", warning_threshold_pct=0.80,
                preferred_unit="PCT", one_R_pct=0.01)
    base.update(kw)
    return E.Account(**base)


def rule(rtype, value, unit="PCT", enabled=True, action="BLOCK"):
    return E.Rule(rule_type=rtype, enabled=enabled, threshold_value=value,
                  threshold_unit=unit, action=action)


def opened(amount, when=NOW, pct=None):
    return E.Trade(id=None, instrument="EURUSD", market="FOREX", direction="LONG",
                   status="OPEN", opened_at=when, planned_risk_pct=pct or (amount / 10_000),
                   planned_risk_amount=amount, planned_risk_R=(pct or amount / 10_000) / 0.01)


def closed(pnl, when, risk=100.0, opened_at=None):
    outcome = "WIN" if pnl > 0 else "LOSS" if pnl < 0 else "BREAKEVEN"
    return E.Trade(id=None, instrument="EURUSD", market="FOREX", direction="LONG",
                   status="CLOSED", opened_at=opened_at or when, closed_at=when,
                   planned_risk_pct=risk / 10_000, planned_risk_amount=risk,
                   planned_risk_R=(risk / 10_000) / 0.01,
                   realized_pnl_amount=pnl, realized_R=pnl / risk, outcome=outcome)


def state_of(rs, rtype):
    return next(s for s in rs.rule_states if s.rule_type == rtype)


def d(y, m, day, h=12):
    return datetime(y, m, day, h, tzinfo=UTC)


# --- Agrégats de base --------------------------------------------------------
def test_day_start_balance_counts_past_pnl_and_adjustments():
    trades = [closed(500, when=d(2026, 7, 6))]        # clôturé hier -> dans le solde
    adj = [E.Adjustment(date=d(2026, 7, 5), amount=1000, type="DEPOSIT")]
    dsb = E.day_start_balance(acct(), trades, adj, NOW)
    assert dsb == pytest.approx(11_500)


def test_realized_today_excludes_yesterday():
    trades = [closed(500, when=d(2026, 7, 6)), closed(-200, when=d(2026, 7, 7, 9))]
    start, end = _today_bounds()
    assert E.realized_pnl_in_window(trades, start, end) == pytest.approx(-200)


def test_open_risk_and_worst_case():
    trades = [opened(100), opened(100), closed(-50, when=d(2026, 7, 7, 9))]
    open_risk = E.open_risk_amount(trades)
    start, end = _today_bounds()
    realized = E.realized_pnl_in_window(trades, start, end)
    assert open_risk == pytest.approx(200)
    assert (open_risk - realized) == pytest.approx(250)  # worst-case drawdown


def _today_bounds():
    from src import time_utils as T
    return T.trading_day_bounds(NOW, "UTC", 0)


# --- daily_loss : niveaux OK / WARN / BLOCK ---------------------------------
def test_daily_loss_warn_at_80pct():
    a = acct()
    rules = [rule(C.RULE_DAILY_LOSS, 0.03)]  # L = 300
    trades = [closed(-250, when=d(2026, 7, 7, 9))]  # worst_case = 250 -> 83%
    rs = E.evaluate(a, rules, trades, [], NOW)
    s = state_of(rs, C.RULE_DAILY_LOSS)
    assert s.level == C.LEVEL_WARN
    assert not rs.locked


def test_daily_loss_block_and_lock_at_100pct():
    a = acct()
    rules = [rule(C.RULE_DAILY_LOSS, 0.03, action="BLOCK")]  # mode strict, L = 300
    trades = [closed(-300, when=d(2026, 7, 7, 9))]  # worst_case = 300 -> 100%
    rs = E.evaluate(a, rules, trades, [], NOW)
    s = state_of(rs, C.RULE_DAILY_LOSS)
    assert s.level == C.LEVEL_BLOCK
    assert rs.locked is True
    assert rs.unlock_at is not None


def test_advisory_rule_alerts_but_does_not_block():
    """Mode conseil (WARN) : un trade qui franchit la limite est autorisé, mais signalé."""
    a = acct()
    rules = [rule(C.RULE_DAILY_LOSS, 0.03, action="WARN")]
    trades = [opened(100), closed(-150, when=d(2026, 7, 7, 9))]
    chk = E.check_new_trade(a, rules, trades, [], NOW, 60)  # dépasserait la limite
    assert chk.allowed is True
    assert len(chk.advisories) == 1
    assert len(chk.blocking) == 0


def test_warn_rule_does_not_lock_even_at_100pct():
    """Mode conseil : à 100 % la jauge est rouge, mais aucun verrou n'est posé."""
    a = acct()
    rules = [rule(C.RULE_DAILY_LOSS, 0.03, action="WARN")]
    trades = [closed(-300, when=d(2026, 7, 7, 9))]
    rs = E.evaluate(a, rules, trades, [], NOW)
    assert rs.locked is False
    assert state_of(rs, C.RULE_DAILY_LOSS).level == C.LEVEL_BLOCK


def test_daily_loss_ok_when_in_profit():
    a = acct()
    rules = [rule(C.RULE_DAILY_LOSS, 0.03)]
    trades = [closed(800, when=d(2026, 7, 7, 9))]  # gros gain -> worst_case négatif
    rs = E.evaluate(a, rules, trades, [], NOW)
    assert state_of(rs, C.RULE_DAILY_LOSS).level == C.LEVEL_OK
    assert not rs.locked


# --- Contrôle à l'ouverture --------------------------------------------------
def test_check_new_trade_refused_when_daily_limit_would_break():
    a = acct()
    rules = [rule(C.RULE_DAILY_LOSS, 0.03)]  # L = 300
    trades = [opened(100), closed(-150, when=d(2026, 7, 7, 9))]
    # projected = (100 + r) - (-150) = 250 + r ; refuse si >= 300 -> r >= 50
    assert E.check_new_trade(a, rules, trades, [], NOW, 60).allowed is False
    assert E.check_new_trade(a, rules, trades, [], NOW, 40).allowed is True


def test_per_trade_risk_limit():
    a = acct()
    rules = [rule(C.RULE_PER_TRADE_RISK, 0.01)]  # max 100
    assert E.check_new_trade(a, rules, [], [], NOW, 150).allowed is False
    assert E.check_new_trade(a, rules, [], [], NOW, 100).allowed is True
    assert E.check_new_trade(a, rules, [], [], NOW, 101).allowed is False


def test_max_open_exposure():
    a = acct()
    rules = [rule(C.RULE_MAX_OPEN_EXPOSURE, 0.02)]  # max 200
    trades = [opened(150)]
    assert E.check_new_trade(a, rules, trades, [], NOW, 60).allowed is False  # 210 > 200
    assert E.check_new_trade(a, rules, trades, [], NOW, 50).allowed is True   # 200


def test_max_trades_per_day():
    a = acct()
    rules = [rule(C.RULE_MAX_TRADES_DAY, 3, unit="COUNT")]
    trades = [opened(10, when=d(2026, 7, 7, 8)),
              opened(10, when=d(2026, 7, 7, 9)),
              opened(10, when=d(2026, 7, 7, 10))]
    rs = E.evaluate(a, rules, trades, [], NOW)
    assert state_of(rs, C.RULE_MAX_TRADES_DAY).level == C.LEVEL_BLOCK
    assert rs.locked is True
    assert E.check_new_trade(a, rules, trades, [], NOW, 10).allowed is False


# --- Pertes consécutives (anti-tilt) ----------------------------------------
def test_consecutive_losses_triggers_block():
    a = acct()
    rules = [rule(C.RULE_MAX_CONSECUTIVE_LOSSES, 3, unit="COUNT")]
    trades = [closed(-50, when=d(2026, 7, 7, 9)),
              closed(-50, when=d(2026, 7, 7, 10)),
              closed(-50, when=d(2026, 7, 7, 11))]
    rs = E.evaluate(a, rules, trades, [], NOW)
    assert state_of(rs, C.RULE_MAX_CONSECUTIVE_LOSSES).consumed == 3
    assert rs.locked is True
    assert E.check_new_trade(a, rules, trades, [], NOW, 10).allowed is False


def test_win_resets_consecutive_loss_streak():
    a = acct()
    rules = [rule(C.RULE_MAX_CONSECUTIVE_LOSSES, 3, unit="COUNT")]
    trades = [closed(-50, when=d(2026, 7, 7, 9)),
              closed(80, when=d(2026, 7, 7, 10)),   # win au milieu
              closed(-50, when=d(2026, 7, 7, 11))]  # 1 seule perte depuis
    rs = E.evaluate(a, rules, trades, [], NOW)
    assert state_of(rs, C.RULE_MAX_CONSECUTIVE_LOSSES).consumed == 1
    assert not rs.locked


# --- Stop-win : empêcher de rendre les gains après une série gagnante --------
def test_daily_profit_target_stops_after_gains():
    a = acct()
    rules = [rule(C.RULE_DAILY_PROFIT_TARGET, 0.05)]  # objectif 500
    trades = [closed(800, when=d(2026, 7, 7, 9))]
    rs = E.evaluate(a, rules, trades, [], NOW)
    assert state_of(rs, C.RULE_DAILY_PROFIT_TARGET).level == C.LEVEL_BLOCK
    assert rs.locked is True
    assert E.check_new_trade(a, rules, trades, [], NOW, 50).allowed is False


def test_gains_alone_do_not_block_without_profit_target():
    # Après des gains, la limite de perte journalière NE doit PAS bloquer
    a = acct()
    rules = [rule(C.RULE_DAILY_LOSS, 0.03)]
    trades = [closed(800, when=d(2026, 7, 7, 9))]
    assert E.check_new_trade(a, rules, trades, [], NOW, 100).allowed is True


# --- R-multiple : cohérence avec les seuils exprimés en R -------------------
def test_threshold_in_R_units():
    a = acct(one_R_pct=0.01)  # 1R = 1% = 100
    # daily_loss = 3R -> 300
    r = rule(C.RULE_DAILY_LOSS, 3, unit="R")
    amt = E.threshold_amount(r, 10_000, a.one_R_pct)
    assert amt == pytest.approx(300)


# --- Week loss ---------------------------------------------------------------
def test_weekly_loss_block():
    a = acct()
    rules = [rule(C.RULE_WEEKLY_LOSS, 0.06)]  # L = 600
    # deux pertes cette semaine (lundi + mardi) totalisant -600
    trades = [closed(-300, when=d(2026, 7, 6, 12)),   # lundi
              closed(-300, when=d(2026, 7, 7, 9))]     # mardi
    rs = E.evaluate(a, rules, trades, [], NOW)
    s = state_of(rs, C.RULE_WEEKLY_LOSS)
    assert s.level == C.LEVEL_BLOCK
    assert rs.locked is True
