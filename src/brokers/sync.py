"""Réconciliation broker → journal : import des positions/deals + enforcement.

Pour un compte MT5, le broker est la **source de vérité** :
- une position ouverte absente du journal → créée (risque calculé depuis le SL),
- une position déjà connue dont le SL a bougé → risque mis à jour,
- une position du journal absente côté broker → clôturée (P&L depuis le deal).

Les trades manuels (external_id NULL) ne sont jamais touchés.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from .. import repository as R
from .. import risk_engine as E
from ..time_utils import trading_day_of
from .base import BrokerConnector


def position_risk_amount(entry: float, sl: Optional[float], volume: float,
                         tick_size: float, tick_value: float) -> float:
    """Risque planifié en devise du compte, calculé depuis la distance au stop.

    risque = (|entrée - SL| / tick_size) × tick_value × volume.
    Renvoie 0 si pas de stop (risque « inconnu » → à signaler)."""
    if not sl or tick_size <= 0 or tick_value <= 0 or volume <= 0:
        return 0.0
    return abs(entry - sl) / tick_size * tick_value * volume


@dataclass
class SyncResult:
    opened: int = 0
    updated: int = 0
    closed: int = 0
    no_stop: int = 0

    def summary(self) -> str:
        s = f"{self.opened} ouverte(s), {self.updated} mise(s) à jour, {self.closed} clôturée(s)"
        if self.no_stop:
            s += f" · ⚠️ {self.no_stop} position(s) sans stop (risque inconnu)"
        return s


def sync_account(conn, account: E.Account, connector: BrokerConnector, now: datetime,
                 deals_since: Optional[datetime] = None) -> SyncResult:
    connector.connect()
    try:
        positions = connector.positions()
        since = deals_since or (now - timedelta(days=7))
        deals = connector.closed_deals(since)
    finally:
        connector.disconnect()

    result = SyncResult()
    trades = R.load_trades(conn, account_id=account.id)
    adjustments = R.load_adjustments(conn, account_id=account.id)
    dsb = E.day_start_balance(account, trades, adjustments, now)

    existing = {t.external_id: t for t in trades
                if t.status == "OPEN" and t.external_id}
    seen: set[str] = set()

    for p in positions:
        seen.add(p.ticket)
        risk_amount = position_risk_amount(p.entry_price, p.sl, p.volume,
                                           p.tick_size, p.tick_value)
        if risk_amount <= 0:
            result.no_stop += 1
        risk_pct = (risk_amount / dsb) if dsb else 0.0
        risk_R = (risk_pct / account.one_R_pct) if account.one_R_pct else 0.0

        if p.ticket in existing:
            t = existing[p.ticket]
            changed = (abs((t.stop_price or 0.0) - (p.sl or 0.0)) > 1e-9
                       or abs(t.planned_risk_amount - risk_amount) > 1e-6)
            if changed:
                R.update_synced_open(conn, t.id, account.id, risk_pct, risk_amount,
                                     risk_R, p.sl, now)
                result.updated += 1
        else:
            tday = trading_day_of(p.opened_at, account.timezone, account.reset_hour)
            R.insert_synced_open(conn, account.id, p.ticket, p.symbol, p.direction,
                                 p.opened_at, tday, risk_pct, risk_amount, risk_R,
                                 p.entry_price, p.sl, p.tp, p.volume, now)
            result.opened += 1

    deal_by_ticket = {d.position_ticket: d for d in deals}
    for ext, t in existing.items():
        if ext not in seen:
            profit = deal_by_ticket[ext].profit if ext in deal_by_ticket else 0.0
            R.close_trade(conn, t.id, realized_pnl_amount=profit, now=now)
            result.closed += 1

    return result


def close_all_positions(connector: BrokerConnector) -> list[str]:
    """Enforcement : ferme toutes les positions ouvertes côté broker.

    À n'appeler que lorsque le compte est verrouillé ET que l'enforcement est activé
    (garde-fous côté appelant). Renvoie les tickets effectivement fermés."""
    connector.connect()
    closed: list[str] = []
    try:
        for p in connector.positions():
            if connector.close_position(p.ticket):
                closed.append(p.ticket)
    finally:
        connector.disconnect()
    return closed
