"""Tests des frontières temporelles (journée de trading, semaine)."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from src import time_utils as T

UTC = ZoneInfo("UTC")


def dt(y, m, d, h=12, mi=0, tz="UTC"):
    return datetime(y, m, d, h, mi, tzinfo=ZoneInfo(tz))


# --- Journée de trading, reset à minuit -------------------------------------
def test_trading_day_bounds_midnight_utc():
    now = dt(2026, 7, 7, 10)  # mardi 10:00 UTC
    start, end = T.trading_day_bounds(now, "UTC", 0)
    assert start == dt(2026, 7, 7, 0)
    assert end == dt(2026, 7, 8, 0)
    assert end - start == timedelta(days=1)
    assert start <= now < end


def test_trading_day_bounds_midnight_utc_plus_1():
    # Africa/Porto-Novo = UTC+1, minuit local = 23:00 UTC la veille
    now = dt(2026, 7, 7, 10, tz="Africa/Porto-Novo")
    start, end = T.trading_day_bounds(now, "Africa/Porto-Novo", 0)
    assert start == dt(2026, 7, 6, 23)  # 07-07 00:00 +01:00
    assert end == dt(2026, 7, 7, 23)


# --- Journée de trading, reset à 17:00 (clôture forex NY simulée) ------------
def test_trading_day_reset_17h_before_reset_belongs_to_previous_day():
    now = dt(2026, 7, 7, 10)  # 10:00 < 17:00 -> session ouverte la veille
    assert T.trading_day_of(now, "UTC", 17) == dt(2026, 7, 6).date()
    start, end = T.trading_day_bounds(now, "UTC", 17)
    assert start == dt(2026, 7, 6, 17)
    assert end == dt(2026, 7, 7, 17)
    assert start <= now < end


def test_trading_day_reset_17h_after_reset_is_current_day():
    now = dt(2026, 7, 7, 18)  # 18:00 >= 17:00 -> session du jour même
    assert T.trading_day_of(now, "UTC", 17) == dt(2026, 7, 7).date()
    start, end = T.trading_day_bounds(now, "UTC", 17)
    assert start == dt(2026, 7, 7, 17)
    assert end == dt(2026, 7, 8, 17)


def test_two_trades_across_17h_reset_are_different_days():
    before = dt(2026, 7, 7, 16, 59)
    after = dt(2026, 7, 7, 17, 1)
    d1 = T.trading_day_of(before, "UTC", 17)
    d2 = T.trading_day_of(after, "UTC", 17)
    assert d1 != d2
    assert d2 - d1 == timedelta(days=1)


# --- Semaine -----------------------------------------------------------------
def test_week_bounds_starts_on_monday():
    now = dt(2026, 7, 8, 12)  # un mercredi
    start, end = T.week_bounds(now, "UTC", "MONDAY")
    assert start.astimezone(UTC).weekday() == 0  # lundi
    assert end - start == timedelta(days=7)
    assert start <= now < end


def test_week_bounds_local_midnight():
    now = dt(2026, 7, 8, 0, 30, tz="Africa/Porto-Novo")
    start, end = T.week_bounds(now, "Africa/Porto-Novo", "MONDAY")
    # lundi 00:00 heure locale = dimanche 23:00 UTC
    assert start.astimezone(ZoneInfo("Africa/Porto-Novo")).weekday() == 0
    assert start.astimezone(ZoneInfo("Africa/Porto-Novo")).hour == 0


def test_in_window_boundaries():
    start = dt(2026, 7, 7, 0)
    end = dt(2026, 7, 8, 0)
    assert T.in_window(dt(2026, 7, 7, 0), start, end) is True   # borne basse incluse
    assert T.in_window(dt(2026, 7, 8, 0), start, end) is False  # borne haute exclue
    assert T.in_window(None, start, end) is False
