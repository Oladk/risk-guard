"""Jauges de risque et helpers de formatage."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import streamlit as st

from src import constants as C
from src import risk_engine as E

LEVEL_COLORS = {
    C.LEVEL_OK: "#2ecc71",
    C.LEVEL_WARN: "#f39c12",
    C.LEVEL_BLOCK: "#e63946",
}

LEVEL_ICONS = {C.LEVEL_OK: "🟢", C.LEVEL_WARN: "🟠", C.LEVEL_BLOCK: "🔴"}

_NO_DECIMALS = {"XOF", "XAF", "JPY", "KRW", "CLP"}


def format_money(amount: float, currency: str) -> str:
    if currency in _NO_DECIMALS:
        return f"{amount:,.0f} {currency}".replace(",", " ")
    return f"{amount:,.2f} {currency}".replace(",", " ")


def format_local_time(dt: datetime | None, tz: str) -> str:
    if dt is None:
        return "—"
    local = dt.astimezone(ZoneInfo(tz))
    return local.strftime("%d/%m %H:%M")


def _bar_html(label: str, detail: str, ratio: float, color: str) -> str:
    pct = int(min(max(ratio, 0.0), 1.0) * 100)
    return f"""
    <div style="margin-bottom:14px;">
      <div style="display:flex;justify-content:space-between;align-items:baseline;
                  font-size:0.9rem;margin-bottom:4px;">
        <span style="color:#c8cdd8;">{label}</span>
        <span style="color:{color};font-weight:600;">{detail}</span>
      </div>
      <div style="background:#2b2f3a;border-radius:6px;height:11px;overflow:hidden;">
        <div style="width:{pct}%;height:100%;background:{color};
                    transition:width .35s ease;"></div>
      </div>
    </div>"""


def render_rule_gauge(state: E.RuleState, account: E.Account, base_balance: float) -> None:
    """Affiche une jauge pour une règle. Les règles COUNT montrent n/N ;
    les règles monétaires montrent le % consommé."""
    color = LEVEL_COLORS[state.level]
    ratio = state.ratio if state.ratio is not None else 0.0

    if not state.is_money:  # COUNT (pertes consécutives, trades/jour)
        detail = f"{int(state.consumed)} / {int(state.limit)}"
    else:
        consumed_pct = E.amount_to_pct(state.consumed, base_balance) * 100
        limit_pct = E.amount_to_pct(state.limit, base_balance) * 100
        if account.preferred_unit == C.UNIT_R:
            consumed_r = E.amount_to_r(state.consumed, base_balance, account.one_R_pct)
            limit_r = E.amount_to_r(state.limit, base_balance, account.one_R_pct)
            detail = f"{consumed_r:.2f}R / {limit_r:.2f}R"
        else:
            detail = f"{consumed_pct:.2f}% / {limit_pct:.2f}%"

    label = f"{LEVEL_ICONS[state.level]} {state.label}"
    st.markdown(_bar_html(label, detail, ratio, color), unsafe_allow_html=True)
