"""Tests du sync broker (Track B) via un connecteur mock — aucun terminal MT5."""

from datetime import datetime, timezone

import pytest

from src import db as DB
from src import repository as R
from src.brokers import sync as SY
from src.brokers.base import BrokerDeal, BrokerPosition
from src.brokers.mock import MockConnector

UTC = timezone.utc
NOW = datetime(2026, 7, 7, 12, 0, tzinfo=UTC)


def fresh():
    conn = DB.get_conn(":memory:")
    DB.init_db(conn)
    return conn


def mt5_account(conn):
    acc = R.load_account(conn)
    acc.kind = "MT5"
    R.save_account(conn, acc)
    return R.load_account(conn)


def pos(ticket, symbol="EURUSD", direction="LONG", vol=1.0, entry=1.10000,
        sl=1.09500, tick_size=0.0001, tick_value=1.0, when=NOW):
    return BrokerPosition(ticket=ticket, symbol=symbol, direction=direction, volume=vol,
                          entry_price=entry, opened_at=when, sl=sl, tp=None,
                          tick_size=tick_size, tick_value=tick_value)


def test_position_risk_amount():
    # |1.10 - 1.095| = 0.005 ; /0.0001 = 50 ticks ; ×1.0 ×1 lot = 50
    assert SY.position_risk_amount(1.10, 1.095, 1.0, 0.0001, 1.0) == pytest.approx(50)
    # pas de stop -> risque inconnu = 0
    assert SY.position_risk_amount(1.10, None, 1.0, 0.0001, 1.0) == 0.0


def test_sync_opens_positions():
    conn = fresh()
    acc = mt5_account(conn)
    mock = MockConnector(positions=[pos("111"), pos("222", symbol="GBPUSD")])
    res = SY.sync_account(conn, acc, mock, NOW)
    assert res.opened == 2
    trades = R.load_trades(conn, account_id=acc.id, status="OPEN")
    assert {t.external_id for t in trades} == {"111", "222"}
    assert all(t.planned_risk_amount > 0 for t in trades)


def test_sync_is_idempotent():
    conn = fresh()
    acc = mt5_account(conn)
    mock = MockConnector(positions=[pos("111")])
    SY.sync_account(conn, acc, mock, NOW)
    res2 = SY.sync_account(conn, acc, mock, NOW)
    assert res2.opened == 0 and res2.updated == 0
    assert len(R.load_trades(conn, account_id=acc.id, status="OPEN")) == 1


def test_sync_closes_disappeared_position_with_deal_profit():
    conn = fresh()
    acc = mt5_account(conn)
    mock = MockConnector(positions=[pos("111")])
    SY.sync_account(conn, acc, mock, NOW)
    mock._positions = []
    mock._deals = [BrokerDeal(position_ticket="111", symbol="EURUSD",
                              profit=200.0, closed_at=NOW)]
    res = SY.sync_account(conn, acc, mock, NOW)
    assert res.closed == 1
    closed = R.load_trades(conn, account_id=acc.id, status="CLOSED")
    assert len(closed) == 1 and closed[0].realized_pnl_amount == 200.0


def test_sync_flags_position_without_stop():
    conn = fresh()
    acc = mt5_account(conn)
    mock = MockConnector(positions=[pos("111", sl=None)])
    res = SY.sync_account(conn, acc, mock, NOW)
    assert res.no_stop == 1
    t = R.load_trades(conn, account_id=acc.id, status="OPEN")[0]
    assert t.planned_risk_amount == 0.0


def test_sync_updates_when_stop_tightened():
    conn = fresh()
    acc = mt5_account(conn)
    mock = MockConnector(positions=[pos("111", sl=1.09500)])
    SY.sync_account(conn, acc, mock, NOW)
    before = R.load_trades(conn, account_id=acc.id, status="OPEN")[0].planned_risk_amount
    mock._positions = [pos("111", sl=1.09800)]  # stop resserré
    res = SY.sync_account(conn, acc, mock, NOW)
    assert res.updated == 1
    after = R.load_trades(conn, account_id=acc.id, status="OPEN")[0].planned_risk_amount
    assert after < before


def test_sync_ignores_manual_trades():
    conn = fresh()
    acc = mt5_account(conn)
    # trade manuel (external_id NULL) ne doit pas être clôturé par le sync
    R.open_trade(conn, acc, "MANUELLE", "FOREX", "LONG", risk_pct=0.01, now=NOW)
    mock = MockConnector(positions=[])
    res = SY.sync_account(conn, acc, mock, NOW)
    assert res.closed == 0
    assert len(R.load_trades(conn, account_id=acc.id, status="OPEN")) == 1


def test_close_all_positions_enforcement():
    mock = MockConnector(positions=[pos("111"), pos("222")])
    closed = SY.close_all_positions(mock)
    assert set(closed) == {"111", "222"}
    assert mock.positions() == []
