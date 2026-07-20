"""Interface commune des connecteurs broker + structures de données."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Protocol


@dataclass
class BrokerPosition:
    ticket: str
    symbol: str
    direction: str          # LONG | SHORT
    volume: float           # lots
    entry_price: float
    opened_at: datetime
    sl: Optional[float] = None
    tp: Optional[float] = None
    tick_size: float = 0.0
    tick_value: float = 0.0  # valeur d'un tick pour 1 lot, en devise du compte


@dataclass
class BrokerDeal:
    position_ticket: str
    symbol: str
    profit: float           # P&L réalisé en devise du compte
    closed_at: datetime


class BrokerConnector(Protocol):
    """Contrat minimal qu'un connecteur (MT5, mock…) doit remplir."""

    def connect(self) -> None: ...
    def positions(self) -> list[BrokerPosition]: ...
    def closed_deals(self, since: datetime) -> list[BrokerDeal]: ...
    def close_position(self, ticket: str) -> bool: ...
    def disconnect(self) -> None: ...
