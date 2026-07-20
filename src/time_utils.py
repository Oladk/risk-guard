"""Gestion du temps : frontières de journée de trading et de semaine.

Règle du projet :
- Les timestamps sont stockés en UTC (aware).
- La "journée de trading" démarre à `reset_hour` dans le fuseau `tz` et dure 24h.
- La "semaine" va du lundi 00:00 au lundi suivant 00:00 (heure locale), calendaire,
  indépendamment de `reset_hour`.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

UTC = ZoneInfo("UTC")

_WEEKDAY_INDEX = {
    "MONDAY": 0,
    "TUESDAY": 1,
    "WEDNESDAY": 2,
    "THURSDAY": 3,
    "FRIDAY": 4,
    "SATURDAY": 5,
    "SUNDAY": 6,
}


def _as_aware_utc(dt: datetime) -> datetime:
    """Garantit un datetime aware en UTC (les naïfs sont supposés déjà UTC)."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def now_utc() -> datetime:
    return datetime.now(tz=UTC)


def trading_day_of(ts: datetime, tz: str, reset_hour: int) -> date:
    """Date de trading à laquelle appartient `ts`.

    La date est celle du *début* de la session : avec reset_hour=17, un timestamp
    à mardi 10:00 (avant 17:00) appartient à la session ouverte lundi 17:00 → date
    de trading = lundi.
    """
    local = _as_aware_utc(ts).astimezone(ZoneInfo(tz))
    if local.hour < reset_hour:
        local = local - timedelta(days=1)
    return local.date()


def trading_day_bounds(now: datetime, tz: str, reset_hour: int) -> tuple[datetime, datetime]:
    """Bornes UTC [start, end) de la journée de trading contenant `now`."""
    zone = ZoneInfo(tz)
    d = trading_day_of(now, tz, reset_hour)
    start_local = datetime.combine(d, time(hour=reset_hour), tzinfo=zone)
    end_local = start_local + timedelta(days=1)
    return start_local.astimezone(UTC), end_local.astimezone(UTC)


def week_bounds(now: datetime, tz: str, week_start: str = "MONDAY") -> tuple[datetime, datetime]:
    """Bornes UTC [start, end) de la semaine calendaire contenant `now`.

    Semaine = jour de départ 00:00 (heure locale) → même jour + 7 jours.
    """
    zone = ZoneInfo(tz)
    local = _as_aware_utc(now).astimezone(zone)
    start_index = _WEEKDAY_INDEX.get(week_start.upper(), 0)
    delta_days = (local.weekday() - start_index) % 7
    first_day = (local - timedelta(days=delta_days)).date()
    start_local = datetime.combine(first_day, time(0, 0), tzinfo=zone)
    end_local = start_local + timedelta(days=7)
    return start_local.astimezone(UTC), end_local.astimezone(UTC)


def next_daily_reset(now: datetime, tz: str, reset_hour: int) -> datetime:
    """Prochain instant de reset journalier (UTC) = fin de la journée courante."""
    _, end = trading_day_bounds(now, tz, reset_hour)
    return end


def next_weekly_reset(now: datetime, tz: str, week_start: str = "MONDAY") -> datetime:
    """Prochain instant de reset hebdomadaire (UTC) = fin de la semaine courante."""
    _, end = week_bounds(now, tz, week_start)
    return end


def in_window(ts: datetime | None, start: datetime, end: datetime) -> bool:
    """True si `ts` est dans [start, end). Timestamps comparés en UTC."""
    if ts is None:
        return False
    t = _as_aware_utc(ts)
    return start <= t < end
