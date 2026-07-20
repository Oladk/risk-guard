"""Connecteur factice pour les tests (aucune dépendance externe)."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from .base import BrokerDeal, BrokerPosition


class MockConnector:
    def __init__(self, positions: Optional[list[BrokerPosition]] = None,
                 deals: Optional[list[BrokerDeal]] = None):
        self._positions = list(positions or [])
        self._deals = list(deals or [])
        self.closed: list[str] = []
        self.connected = False

    def connect(self) -> None:
        self.connected = True

    def positions(self) -> list[BrokerPosition]:
        return list(self._positions)

    def closed_deals(self, since: datetime) -> list[BrokerDeal]:
        return [d for d in self._deals if d.closed_at >= since]

    def close_position(self, ticket: str) -> bool:
        before = len(self._positions)
        self._positions = [p for p in self._positions if p.ticket != ticket]
        if len(self._positions) < before:
            self.closed.append(ticket)
            return True
        return False

    def disconnect(self) -> None:
        self.connected = False
