"""Phase 2 — smoke tests de l'app Streamlit + intégration bout-en-bout.

Les pages tournent sans exception (AppTest), et le flux réel
(ouvrir → clôturer → verrou) déclenche bien le mode STOP.
"""

import os
import pathlib
from datetime import datetime
from zoneinfo import ZoneInfo

from streamlit.testing.v1 import AppTest

ROOT = pathlib.Path(__file__).resolve().parent.parent
UTC = ZoneInfo("UTC")


def _run(rel_path: str, tmp_path) -> AppTest:
    os.environ["RISK_DB_PATH"] = str(tmp_path / "risk.db")
    at = AppTest.from_file(str(ROOT / rel_path), default_timeout=60)
    at.run()
    return at


def test_fresh_account_shows_onboarding(tmp_path):
    at = _run("app.py", tmp_path)
    assert not at.exception
    assert any("Bienvenue" in t.value for t in at.title)  # compte neuf -> assistant


def test_cockpit_runs_after_onboarding(tmp_path):
    os.environ["RISK_DB_PATH"] = str(tmp_path / "risk.db")
    from src import repository as R
    from src import service
    conn = service.connect()
    R.mark_onboarded(conn, 1)
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60)
    at.run()
    assert not at.exception
    assert any("Cockpit" in t.value for t in at.title)


def test_journal_runs_without_exception(tmp_path):
    at = _run("pages/1_Journal.py", tmp_path)
    assert not at.exception


def test_config_runs_without_exception(tmp_path):
    at = _run("pages/2_Regles_et_compte.py", tmp_path)
    assert not at.exception


def test_calculator_runs_without_exception(tmp_path):
    at = _run("pages/3_Calculateur.py", tmp_path)
    assert not at.exception


def test_analytics_runs_empty(tmp_path):
    at = _run("pages/4_Analytics.py", tmp_path)
    assert not at.exception


def test_analytics_runs_with_data(tmp_path):
    os.environ["RISK_DB_PATH"] = str(tmp_path / "risk.db")
    from src import repository as R
    from src import service

    conn = service.connect()
    account = R.load_account(conn)
    now = datetime(2026, 7, 7, 12, 0, tzinfo=UTC)
    for pnl, emo in [(200.0, "Calme"), (-100.0, "FOMO"), (150.0, "Discipliné")]:
        tid = R.open_trade(conn, account, "EURUSD", "FOREX", "LONG",
                           risk_pct=0.01, now=now, emotion_tag=emo)
        R.close_trade(conn, tid, realized_pnl_amount=pnl, now=now)

    at = AppTest.from_file(str(ROOT / "pages/4_Analytics.py"), default_timeout=60)
    at.run()
    assert not at.exception


def test_login_shown_when_auth_required(tmp_path, monkeypatch):
    os.environ["RISK_DB_PATH"] = str(tmp_path / "risk.db")
    monkeypatch.setenv("RISK_REQUIRE_AUTH", "1")
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60)
    at.run()
    assert not at.exception
    # Le gate a affiché la connexion et stoppé la page (pas de cockpit).
    assert any("Connexion" in t.value for t in at.title)
    assert not any("Cockpit" in t.value for t in at.title)


def test_coach_runs_empty(tmp_path):
    at = _run("pages/5_Coach.py", tmp_path)
    assert not at.exception


def test_coach_runs_with_data(tmp_path):
    os.environ["RISK_DB_PATH"] = str(tmp_path / "risk.db")
    from src import repository as R
    from src import service

    conn = service.connect()
    account = R.load_account(conn)
    now = datetime(2026, 7, 7, 12, 0, tzinfo=UTC)
    for pnl, emo in [(200.0, "Calme"), (-100.0, "Revenge"), (150.0, "Discipliné"),
                     (-50.0, "FOMO")]:
        tid = R.open_trade(conn, account, "EURUSD", "FOREX", "LONG",
                           risk_pct=0.01, now=now, emotion_tag=emo, setup="Breakout")
        R.close_trade(conn, tid, realized_pnl_amount=pnl, now=now)

    at = AppTest.from_file(str(ROOT / "pages/5_Coach.py"), default_timeout=60)
    at.run()
    assert not at.exception


def test_end_to_end_daily_loss_locks(tmp_path):
    os.environ["RISK_DB_PATH"] = str(tmp_path / "risk.db")
    from src import constants as C
    from src import repository as R
    from src import service

    conn = service.connect()

    # Compte déterministe : UTC, reset minuit, solde 10 000, 1R = 1%.
    acc = R.load_account(conn)
    acc.timezone = "UTC"
    acc.reset_hour = 0
    acc.initial_balance = 10_000.0
    acc.one_R_pct = 0.01
    R.save_account(conn, acc)

    # N'activer que la perte max journalière (3%) pour isoler la règle.
    for rule in R.load_rules(conn):
        rule.enabled = rule.rule_type == C.RULE_DAILY_LOSS
        if rule.rule_type == C.RULE_DAILY_LOSS:
            rule.threshold_value = 0.03
            rule.threshold_unit = C.UNIT_PCT
            rule.action = "BLOCK"  # mode strict pour tester le verrou
        R.save_rule(conn, rule)

    now = datetime(2026, 7, 7, 12, 0, tzinfo=UTC)
    account = R.load_account(conn)

    # Ouvre puis clôture une perte de 300 (= 3% de 10 000) → limite atteinte.
    tid = R.open_trade(conn, account, "EURUSD", "FOREX", "LONG", risk_pct=0.02, now=now)
    R.close_trade(conn, tid, realized_pnl_amount=-300.0, now=now)

    *_, rs, _ = service.evaluate_now(conn, now)
    assert rs.locked is True
    assert rs.global_level == C.LEVEL_BLOCK

    # Un nouveau trade doit être refusé.
    from src import risk_engine as E
    check = E.check_new_trade(account, R.load_rules(conn), R.load_trades(conn),
                              R.load_adjustments(conn), now, 100.0)
    assert check.allowed is False
