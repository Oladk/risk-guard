"""Tests de l'intelligence comportementale (Track C)."""

from datetime import datetime, timezone

import pytest

from src import behavior as B
from src import risk_engine as E

UTC = timezone.utc
NOW = datetime(2026, 7, 7, 15, 0, tzinfo=UTC)
DAY_START = datetime(2026, 7, 7, 0, 0, tzinfo=UTC)
DAY_END = datetime(2026, 7, 8, 0, 0, tzinfo=UTC)


def at(h, m=0):
    return datetime(2026, 7, 7, h, m, tzinfo=UTC)


def opened(when, risk_pct=0.01, emotion=None):
    return E.Trade(id=None, instrument="EURUSD", market="FOREX", direction="LONG",
                   status="OPEN", opened_at=when, planned_risk_pct=risk_pct,
                   planned_risk_amount=risk_pct * 10_000, planned_risk_R=risk_pct / 0.01,
                   emotion_tag=emotion)


def closed(closed_at, outcome, R=None, opened_at=None, risk_pct=0.01):
    R = R if R is not None else (1.0 if outcome == "WIN" else -1.0 if outcome == "LOSS" else 0.0)
    return E.Trade(id=None, instrument="EURUSD", market="FOREX", direction="LONG",
                   status="CLOSED", opened_at=opened_at or closed_at, closed_at=closed_at,
                   planned_risk_pct=risk_pct, planned_risk_amount=risk_pct * 10_000,
                   planned_risk_R=risk_pct / 0.01, realized_pnl_amount=R * risk_pct * 10_000,
                   realized_R=R, outcome=outcome)


def codes(assessment):
    return {s.code for s in assessment.signals}


# --- C1 : tilt ---------------------------------------------------------------
def test_calm_when_no_trades():
    a = B.assess_tilt([], NOW, DAY_START, DAY_END)
    assert a.level == "CALME" and a.score == 0


def test_rapid_reentry():
    a = B.assess_tilt([opened(at(14, 0)), opened(at(14, 2))], NOW, DAY_START, DAY_END)
    assert "rapid_reentry" in codes(a)
    assert a.level == "VIGILANCE"


def test_reentry_after_loss():
    trades = [closed(at(14, 0), "LOSS"), opened(at(14, 5))]
    a = B.assess_tilt(trades, NOW, DAY_START, DAY_END)
    assert "reentry_after_loss" in codes(a)


def test_size_escalation_after_loss():
    trades = [opened(at(13, 0), risk_pct=0.01), closed(at(13, 30), "LOSS"),
              opened(at(14, 0), risk_pct=0.02)]
    a = B.assess_tilt(trades, NOW, DAY_START, DAY_END)
    assert "size_escalation" in codes(a)


def test_emotion_frequency_signal():
    trades = [opened(at(10, 0), emotion="Revenge"), opened(at(11, 0), emotion="FOMO")]
    a = B.assess_tilt(trades, NOW, DAY_START, DAY_END)
    assert "emotion" in codes(a)


def test_overtrading_signal():
    trades = [opened(at(9, i * 10)) for i in range(6)]  # 6 trades espacés de 10 min
    a = B.assess_tilt(trades, NOW, DAY_START, DAY_END)
    assert "overtrading" in codes(a)
    assert "rapid_reentry" not in codes(a)  # 10 min > seuil


def test_combined_signals_reach_tilt():
    trades = [closed(at(14, 0), "LOSS"), opened(at(14, 1)), opened(at(14, 3))]
    a = B.assess_tilt(trades, NOW, DAY_START, DAY_END)
    assert a.level == "TILT"
    assert {"rapid_reentry", "reentry_after_loss"} <= codes(a)


# --- C2 : stats prescriptives ------------------------------------------------
def test_conditional_winrate_after_loss():
    seq = [closed(at(9), "LOSS"), closed(at(10), "WIN"), closed(at(11), "LOSS"),
           closed(at(12), "LOSS"), closed(at(13), "WIN")]
    wr_after, wr_overall, n = B.conditional_winrate_after_loss(seq)
    assert n == 3
    assert wr_after == pytest.approx(2 / 3)
    assert wr_overall == pytest.approx(0.4)


def test_expectancy_R():
    seq = [closed(at(9), "WIN", R=2.0), closed(at(10), "LOSS", R=-1.0)]
    assert B.expectancy_R(seq) == pytest.approx(0.5)


# --- C3 : suggestions --------------------------------------------------------
def test_suggest_limits_insufficient_sample():
    seq = [closed(at(9), "WIN") for _ in range(5)]
    assert B.suggest_limits(seq, min_trades=20) is None


def test_suggest_limits_positive_edge_is_capped():
    wins = [closed(at(9), "WIN", R=1.5) for _ in range(12)]
    losses = [closed(at(10), "LOSS", R=-1.0) for _ in range(8)]
    s = B.suggest_limits(wins + losses, min_trades=20)
    assert s is not None
    assert s.win_rate == pytest.approx(0.6)
    assert s.payoff == pytest.approx(1.5)
    assert s.per_trade_pct == pytest.approx(0.02)   # demi-Kelly plafonné
    assert s.daily_loss_pct == pytest.approx(0.06)
    assert s.n == 20


def test_suggest_limits_negative_edge_floors():
    wins = [closed(at(9), "WIN", R=1.0) for _ in range(5)]
    losses = [closed(at(10), "LOSS", R=-1.0) for _ in range(15)]
    s = B.suggest_limits(wins + losses, min_trades=20)
    assert s is not None
    assert s.kelly <= 0
    assert s.per_trade_pct == pytest.approx(0.0025)  # plancher
