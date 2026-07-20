"""Tests de la couche données : schéma, seed, roundtrip trades/ajustements/alertes."""

from datetime import datetime
from zoneinfo import ZoneInfo

from src import constants as C
from src import db as DB
from src import repository as R

UTC = ZoneInfo("UTC")
NOW = datetime(2026, 7, 7, 12, 0, tzinfo=UTC)


def fresh_conn():
    conn = DB.get_conn(":memory:")
    DB.init_db(conn)
    return conn


def test_seed_creates_account_and_seven_rules():
    conn = fresh_conn()
    account = R.load_account(conn)
    assert account.base_currency == C.DEFAULT_ACCOUNT["base_currency"]
    rules = R.load_rules(conn)
    assert len(rules) == len(C.RULE_TYPES)
    assert {r.rule_type for r in rules} == set(C.RULE_TYPES)


def test_open_and_close_trade_roundtrip():
    conn = fresh_conn()
    account = R.load_account(conn)  # solde initial 1_000_000, one_R_pct 0.01
    tid = R.open_trade(conn, account, "EURUSD", "FOREX", "LONG",
                       risk_pct=0.01, now=NOW, emotion_tag="Calme")
    open_trades = R.load_trades(conn, status="OPEN")
    assert len(open_trades) == 1
    t = open_trades[0]
    assert t.id == tid
    assert t.planned_risk_amount == 10_000  # 1% de 1_000_000
    assert t.planned_risk_R == 1.0
    assert t.emotion_tag == "Calme"
    assert t.trading_day == NOW.date()

    R.close_trade(conn, tid, realized_pnl_amount=20_000, now=NOW)
    closed = R.load_trades(conn, status="CLOSED")
    assert len(closed) == 1
    c = closed[0]
    assert c.outcome == "WIN"
    assert c.realized_R == 2.0  # 20_000 / 10_000
    assert R.load_trades(conn, status="OPEN") == []


def test_adjustment_affects_day_start_balance():
    from src import risk_engine as E
    conn = fresh_conn()
    account = R.load_account(conn)
    R.add_adjustment(conn, amount=500_000, type_="DEPOSIT",
                     when=datetime(2026, 7, 6, 10, tzinfo=UTC))
    trades = R.load_trades(conn)
    adj = R.load_adjustments(conn)
    dsb = E.day_start_balance(account, trades, adj, NOW)
    assert dsb == 1_500_000


def test_save_rule_persists():
    conn = fresh_conn()
    rules = R.load_rules(conn)
    daily = next(r for r in rules if r.rule_type == C.RULE_DAILY_LOSS)
    daily.threshold_value = 0.05
    daily.enabled = False
    R.save_rule(conn, daily)
    reloaded = next(r for r in R.load_rules(conn) if r.rule_type == C.RULE_DAILY_LOSS)
    assert reloaded.threshold_value == 0.05
    assert reloaded.enabled is False


def test_alert_log_roundtrip():
    conn = fresh_conn()
    R.log_alert(conn, C.RULE_DAILY_LOSS, "BLOCK", NOW, context="test")
    alerts = R.load_alerts(conn)
    assert len(alerts) == 1
    assert alerts[0]["rule_type"] == C.RULE_DAILY_LOSS
    assert alerts[0]["level"] == "BLOCK"


def test_multi_account_isolation():
    conn = fresh_conn()
    acc1 = R.load_account(conn, 1)
    acc2_id = R.create_account(conn, name="BRVM", base_currency="XOF",
                               initial_balance=500_000, timezone="Africa/Abidjan")
    acc2 = R.load_account(conn, acc2_id)

    R.open_trade(conn, acc1, "EURUSD", "FOREX", "LONG", risk_pct=0.01, now=NOW)
    R.open_trade(conn, acc2, "SNTS", "BRVM", "LONG", risk_pct=0.01, now=NOW)

    t1 = R.load_trades(conn, account_id=1)
    t2 = R.load_trades(conn, account_id=acc2_id)
    assert len(t1) == 1 and t1[0].instrument == "EURUSD"
    assert len(t2) == 1 and t2[0].instrument == "SNTS"

    # Le nouveau compte a bien ses 7 règles seedées et son propre capital.
    assert len(R.load_rules(conn, acc2_id)) == len(C.RULE_TYPES)
    assert acc2.initial_balance == 500_000


def test_trade_events_are_appended():
    conn = fresh_conn()
    account = R.load_account(conn)
    tid = R.open_trade(conn, account, "EURUSD", "FOREX", "LONG", risk_pct=0.01, now=NOW)
    R.close_trade(conn, tid, realized_pnl_amount=5000, now=NOW)
    events = R.load_trade_events(conn, account_id=1)
    types = [e["event_type"] for e in events]
    assert "OPEN" in types
    assert "CLOSE" in types
    assert len(events) == 2  # log append-only : un événement par mutation


def test_cancel_trade_logs_event():
    conn = fresh_conn()
    account = R.load_account(conn)
    tid = R.open_trade(conn, account, "EURUSD", "FOREX", "LONG", risk_pct=0.01, now=NOW)
    R.cancel_trade(conn, tid, now=NOW)
    assert R.load_trades(conn, account_id=1, status=C.STATUS_OPEN) == []
    events = R.load_trade_events(conn, account_id=1)
    assert any(e["event_type"] == "CANCEL" for e in events)


def test_checklist_seeded_and_crud():
    conn = fresh_conn()
    assert len(R.load_checklist(conn, 1)) == len(C.DEFAULT_CHECKLIST)
    iid = R.add_checklist_item(conn, 1, "Nouvelle règle")
    assert len(R.load_checklist(conn, 1)) == len(C.DEFAULT_CHECKLIST) + 1
    R.set_checklist_item(conn, iid, enabled=False)
    assert len(R.load_checklist(conn, 1, only_enabled=True)) == len(C.DEFAULT_CHECKLIST)
    R.delete_checklist_item(conn, iid)
    assert len(R.load_checklist(conn, 1)) == len(C.DEFAULT_CHECKLIST)


def test_create_account_seeds_checklist():
    conn = fresh_conn()
    aid = R.create_account(conn, name="BRVM", base_currency="XOF",
                           initial_balance=500_000, timezone="UTC")
    assert len(R.load_checklist(conn, aid)) == len(C.DEFAULT_CHECKLIST)


def test_open_trade_stores_setup_and_thesis():
    conn = fresh_conn()
    account = R.load_account(conn)
    R.open_trade(conn, account, "EURUSD", "FOREX", "LONG", risk_pct=0.01, now=NOW,
                 setup="Breakout H4", thesis="Cassure de résistance")
    t = R.load_trades(conn, account_id=1)[0]
    assert t.setup == "Breakout H4"
    assert t.thesis == "Cassure de résistance"


def test_tilt_config_seeded_and_saved():
    conn = fresh_conn()
    cfg = R.load_tilt_config(conn, 1)
    assert cfg.tilt_threshold == C.DEFAULT_TILT["tilt_threshold"]
    cfg.overtrade_count = 10
    R.save_tilt_config(conn, 1, cfg)
    assert R.load_tilt_config(conn, 1).overtrade_count == 10


def test_create_account_seeds_tilt_config():
    conn = fresh_conn()
    aid = R.create_account(conn, name="X", base_currency="XOF",
                           initial_balance=100_000, timezone="UTC")
    assert R.load_tilt_config(conn, aid).tilt_threshold == C.DEFAULT_TILT["tilt_threshold"]


def test_onboarding_flag_and_risk_profile():
    conn = fresh_conn()
    assert R.is_onboarded(conn, 1) is False  # compte neuf
    R.apply_risk_profile(conn, 1, "Prudent")
    daily = next(r for r in R.load_rules(conn, 1) if r.rule_type == C.RULE_DAILY_LOSS)
    assert daily.enabled is True
    assert daily.threshold_value == C.RISK_PROFILES["Prudent"][C.RULE_DAILY_LOSS]
    R.mark_onboarded(conn, 1)
    assert R.is_onboarded(conn, 1) is True
