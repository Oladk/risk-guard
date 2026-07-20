"""Tests des notifications : aucun envoi réel (tout est mocké)."""

from unittest.mock import MagicMock

from src import notify as N


def test_send_email_disabled_or_missing():
    assert N.send_email({"enabled": False}, "s", "b") is False
    assert N.send_email(None, "s", "b") is False


def test_send_ntfy_disabled():
    assert N.send_ntfy({"enabled": False}, "s", "b") is False


def test_send_email_enabled(monkeypatch):
    fake_smtp = MagicMock()
    monkeypatch.setattr(N.smtplib, "SMTP", fake_smtp)
    cfg = {"enabled": True, "smtp_host": "smtp.test", "smtp_port": 587,
           "sender": "a@b.c", "app_password": "secret", "recipient": "d@e.f"}
    assert N.send_email(cfg, "sujet", "corps") is True
    assert fake_smtp.called


def test_send_ntfy_enabled(monkeypatch):
    posted = {}

    def fake_post(url, **kw):
        posted["url"] = url
        posted["headers"] = kw.get("headers")
        return MagicMock(status_code=200)

    monkeypatch.setattr(N.requests, "post", fake_post)
    cfg = {"enabled": True, "topic": "mytopic", "server": "https://ntfy.sh"}
    assert N.send_ntfy(cfg, "sujet", "corps") is True
    assert posted["url"].endswith("/mytopic")
    assert posted["headers"]["Title"] == "sujet"


def test_notify_catches_errors(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("réseau indisponible")

    monkeypatch.setattr(N, "send_email", boom)
    res = N.notify("s", "b", email_cfg={"enabled": True}, ntfy_cfg=None)
    assert "error" in str(res["email"])


def test_build_message():
    subject, body = N.build_message("BLOCK", ["Perte max journalière : atteinte"],
                                    when_local="07/07 00:00")
    assert "Blocage" in subject
    assert "Perte max journalière" in body
    assert "reset" in body.lower()


def test_daily_digest_builds(tmp_path):
    import os
    os.environ["RISK_DB_PATH"] = str(tmp_path / "risk.db")
    from scripts import daily_digest as DG
    from src import service

    conn = service.connect()
    account, rules, trades, adj, rs, now = service.evaluate_now(conn)
    subject, body = DG.build_digest(account, rs, now)
    assert "récap" in subject
    assert "Solde de début de journée" in body
