"""Adaptateur MetaTrader 5 (terminal local Windows) — lecture + fermeture.

Nécessite le paquet `MetaTrader5` (`pip install MetaTrader5`) et un terminal MT5
installé/connecté. L'import est différé pour que le reste de l'app (et les tests)
fonctionne sans ce paquet.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from .base import BrokerDeal, BrokerPosition


class MT5Connector:
    def __init__(self, login: Optional[int] = None, password: str = "",
                 server: str = "", path: str = ""):
        self.login = login
        self.password = password
        self.server = server
        self.path = path
        self._mt5 = None

    def _lib(self):
        if self._mt5 is None:
            try:
                import MetaTrader5 as mt5  # noqa: N813
            except ImportError as e:
                raise RuntimeError(
                    "Le paquet 'MetaTrader5' n'est pas installé (pip install MetaTrader5). "
                    "Requis pour la synchronisation MT5.") from e
            self._mt5 = mt5
        return self._mt5

    def connect(self) -> None:
        mt5 = self._lib()
        kwargs = {"path": self.path} if self.path else {}
        if not mt5.initialize(**kwargs):
            raise RuntimeError(f"Échec initialize() MT5 : {mt5.last_error()}")
        if self.login:
            if not mt5.login(int(self.login), password=self.password, server=self.server):
                raise RuntimeError(f"Échec login() MT5 : {mt5.last_error()}")

    def positions(self) -> list[BrokerPosition]:
        mt5 = self._lib()
        out: list[BrokerPosition] = []
        for p in (mt5.positions_get() or []):
            info = mt5.symbol_info(p.symbol)
            tick_size = getattr(info, "trade_tick_size", 0.0) if info else 0.0
            tick_value = getattr(info, "trade_tick_value", 0.0) if info else 0.0
            direction = "LONG" if p.type == mt5.POSITION_TYPE_BUY else "SHORT"
            out.append(BrokerPosition(
                ticket=str(p.ticket), symbol=p.symbol, direction=direction,
                volume=p.volume, entry_price=p.price_open,
                opened_at=datetime.fromtimestamp(p.time, tz=timezone.utc),
                sl=(p.sl or None), tp=(p.tp or None),
                tick_size=tick_size, tick_value=tick_value))
        return out

    def closed_deals(self, since: datetime) -> list[BrokerDeal]:
        mt5 = self._lib()
        deals = mt5.history_deals_get(since, datetime.now(tz=timezone.utc)) or []
        out: list[BrokerDeal] = []
        for d in deals:
            if getattr(d, "entry", None) == mt5.DEAL_ENTRY_OUT:  # sortie de position
                out.append(BrokerDeal(
                    position_ticket=str(d.position_id), symbol=d.symbol,
                    profit=d.profit,
                    closed_at=datetime.fromtimestamp(d.time, tz=timezone.utc)))
        return out

    def close_position(self, ticket: str) -> bool:
        mt5 = self._lib()
        matches = [p for p in (mt5.positions_get() or []) if str(p.ticket) == str(ticket)]
        if not matches:
            return False
        p = matches[0]
        order_type = (mt5.ORDER_TYPE_SELL if p.type == mt5.POSITION_TYPE_BUY
                      else mt5.ORDER_TYPE_BUY)
        tick = mt5.symbol_info_tick(p.symbol)
        price = tick.bid if order_type == mt5.ORDER_TYPE_SELL else tick.ask
        request = {
            "action": mt5.TRADE_ACTION_DEAL, "position": p.ticket, "symbol": p.symbol,
            "volume": p.volume, "type": order_type, "price": price,
            "deviation": 20, "comment": "RiskGuard STOP",
        }
        res = mt5.order_send(request)
        return res is not None and res.retcode == mt5.TRADE_RETCODE_DONE

    def disconnect(self) -> None:
        if self._mt5 is not None:
            self._mt5.shutdown()
