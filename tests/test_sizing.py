"""Tests du calculateur de position (fonctions pures)."""

import pytest

from src import sizing as S


def test_brvm_shares():
    # Risque 10 000 XOF, stop à 100 XOF de l'entrée -> 100 actions.
    r = S.size_position("BRVM", risk_amount=10_000, entry=5_000, stop=4_900)
    assert r.size == pytest.approx(100)
    assert r.size_unit == "actions"


def test_forex_lots_same_currency():
    # Compte en USD, EURUSD, risque 100 USD, stop à 50 pips (0.0050).
    r = S.size_position("FOREX", risk_amount=100, entry=1.1000, stop=1.0950, pair="EURUSD")
    assert r.distance_pips == pytest.approx(50)
    assert r.size == pytest.approx(0.2)  # 0.2 lot
    # Vérif inverse : 0.2 lot * 100000 * 0.0050 = 100 USD de risque.
    assert r.size * S.FOREX_CONTRACT_SIZE * r.distance == pytest.approx(100)


def test_forex_jpy_pip_size():
    r = S.size_position("FOREX", risk_amount=100, entry=150.00, stop=149.50, pair="USDJPY")
    assert S.pip_size("USDJPY") == 0.01
    assert r.distance_pips == pytest.approx(50)


def test_conversion_rate_applied():
    # 1 unité quote = 600 (compte). Risque 60 000 compte -> 100 quote de perte tolérée.
    r = S.size_position("FOREX", risk_amount=60_000, entry=1.2000, stop=1.1950,
                        pair="GBPUSD", conversion_rate=600.0)
    # quote_risk = 100 ; distance 0.0050 ; units = 20 000 ; lots = 0.2
    assert r.units == pytest.approx(20_000)
    assert r.size == pytest.approx(0.2)


def test_zero_distance_raises():
    with pytest.raises(ValueError):
        S.size_position("BRVM", risk_amount=1_000, entry=100, stop=100)
