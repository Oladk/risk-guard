"""Tests de l'exposition ajustée par corrélation (A3)."""

import math

import pytest

from src import correlation as CO
from src import db as DB


def test_effective_equals_sum_when_fully_correlated_same_direction():
    positions = [("EURUSD", "LONG", 100), ("GBPUSD", "LONG", 100)]
    corr = {("EURUSD", "GBPUSD"): 1.0}
    assert CO.effective_risk(positions, corr) == pytest.approx(200)


def test_effective_less_than_sum_when_uncorrelated():
    positions = [("EURUSD", "LONG", 100), ("XAUUSD", "LONG", 100)]
    # corrélation inconnue = 0 -> diversification
    assert CO.effective_risk(positions, {}) == pytest.approx(math.sqrt(2) * 100)


def test_opposite_directions_offset_when_correlated():
    positions = [("EURUSD", "LONG", 100), ("GBPUSD", "SHORT", 100)]
    corr = {("EURUSD", "GBPUSD"): 1.0}
    # w = [+100, -100], ρ=1 -> variance nulle -> risque effectif ~0
    assert CO.effective_risk(positions, corr) == pytest.approx(0.0, abs=1e-6)


def test_same_instrument_treated_as_corr_1():
    positions = [("EURUSD", "LONG", 100), ("EURUSD", "LONG", 100)]
    assert CO.effective_risk(positions, {}) == pytest.approx(200)


def test_single_position_equals_its_risk():
    assert CO.effective_risk([("EURUSD", "LONG", 100)], {}) == pytest.approx(100)


def test_db_set_load_correlation_is_symmetric():
    conn = DB.get_conn(":memory:")
    DB.init_db(conn)
    CO.set_correlation(conn, "EURUSD", "GBPUSD", 0.85)
    m = CO.load_correlations(conn)
    assert m[("EURUSD", "GBPUSD")] == pytest.approx(0.85)
    lookup = CO.make_lookup(m)
    assert lookup("GBPUSD", "EURUSD") == pytest.approx(0.85)  # symétrique
