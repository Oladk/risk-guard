"""Presets de challenges prop-firm : bonne formation + API."""

from src import prop_presets as PP


def test_all_presets_well_formed():
    for key, p in PP.PRESETS.items():
        assert p.key == key
        assert 0 < p.daily_loss_pct <= 0.20, key
        assert 0 < p.max_loss_pct <= 0.30, key
        # Le drawdown journalier ne peut pas dépasser le drawdown total.
        assert p.daily_loss_pct <= p.max_loss_pct, key
        assert p.profit_target_pct is None or 0 < p.profit_target_pct <= 0.30, key
        assert p.min_trading_days >= 0, key
        assert p.drawdown_type in ("static", "trailing"), key


def test_keys_unique_and_lookup():
    keys = [k for k, _ in PP.names()]
    assert len(keys) == len(set(keys))
    assert PP.get("ftmo_p1").firm == "FTMO"
    assert PP.get("custom").firm == ""


def test_funded_has_no_target():
    assert PP.get("ftmo_funded").profit_target_pct is None


def test_label_and_summary():
    assert PP.get("ftmo_p1").label.startswith("FTMO")
    assert "Personnalisé" == PP.get("custom").label
    s = PP.get("ftmo_p1").summary()
    assert "5 %" in s and "10 %" in s
