"""Tests de la conversion multi-devises (A2)."""

import pytest

from src import db as DB
from src import fx


def test_convert_identity():
    assert fx.convert(100, "XOF", "XOF", {}) == 100


def test_convert_direct():
    rates = {("USD", "XOF"): 600.0}
    assert fx.convert(10, "USD", "XOF", rates) == pytest.approx(6000)


def test_convert_inverse():
    rates = {("USD", "XOF"): 600.0}
    assert fx.convert(6000, "XOF", "USD", rates) == pytest.approx(10)


def test_convert_missing_raises():
    with pytest.raises(ValueError):
        fx.convert(10, "USD", "EUR", {})


def test_try_convert_returns_none_when_missing():
    assert fx.try_convert(10, "USD", "EUR", {}) is None


def test_db_set_and_get_rate():
    conn = DB.get_conn(":memory:")
    DB.init_db(conn)
    fx.set_rate(conn, "USD", "XOF", 605.0)
    assert fx.get_rate(conn, "USD", "XOF") == pytest.approx(605.0)
    # sens inverse dérivé
    assert fx.get_rate(conn, "XOF", "USD") == pytest.approx(1 / 605.0)
    # upsert : mise à jour du taux
    fx.set_rate(conn, "USD", "XOF", 610.0)
    assert fx.get_rate(conn, "USD", "XOF") == pytest.approx(610.0)
