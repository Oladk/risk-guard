"""Jauges de risque et helpers de formatage."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import streamlit as st

from src import constants as C
from src import risk_engine as E
from src import theme as TH

LEVEL_COLORS = {
    C.LEVEL_OK: "#2ecc71",
    C.LEVEL_WARN: "#f39c12",
    C.LEVEL_BLOCK: "#e63946",
}

LEVEL_ICONS = {C.LEVEL_OK: "🟢", C.LEVEL_WARN: "🟠", C.LEVEL_BLOCK: "🔴"}

_NO_DECIMALS = {"XOF", "XAF", "JPY", "KRW", "CLP"}


def _flush(html: str) -> str:
    """Retire l'indentation de chaque ligne : sinon Streamlit interprète un bloc
    HTML indenté de 4+ espaces comme un bloc de code (et l'échappe au lieu de le rendre)."""
    return "\n".join(line.lstrip() for line in html.splitlines())


def format_money(amount: float, currency: str) -> str:
    if currency in _NO_DECIMALS:
        return f"{amount:,.0f} {currency}".replace(",", " ")
    return f"{amount:,.2f} {currency}".replace(",", " ")


def format_local_time(dt: datetime | None, tz: str) -> str:
    if dt is None:
        return "—"
    local = dt.astimezone(ZoneInfo(tz))
    return local.strftime("%d/%m %H:%M")


def _bar_html(label: str, detail: str, ratio: float, color: str, dim: bool = False) -> str:
    pct = int(min(max(ratio, 0.0), 1.0) * 100)
    p = TH.pal()
    # En cas de limite franchie ailleurs, les jauges « OK » sont estompées pour
    # ne pas rivaliser visuellement avec le rouge (retour pilote : vert à côté du rouge).
    opacity = "opacity:0.4;" if dim else ""
    return f"""
    <div style="margin-bottom:14px;{opacity}">
      <div style="display:flex;justify-content:space-between;align-items:baseline;
                  font-size:0.9rem;margin-bottom:4px;">
        <span style="color:{p['muted_soft']};">{label}</span>
        <span style="color:{color};font-weight:600;">{detail}</span>
      </div>
      <div style="background:{p['track']};border-radius:6px;height:11px;overflow:hidden;">
        <div style="width:{pct}%;height:100%;background:{color};
                    transition:width .35s ease;"></div>
      </div>
    </div>"""


SEVERITY_RANK = {C.LEVEL_BLOCK: 0, C.LEVEL_WARN: 1, C.LEVEL_OK: 2}


def render_rule_gauge(state: E.RuleState, account: E.Account, base_balance: float,
                      dim: bool = False) -> None:
    """Affiche une jauge pour une règle. Les règles COUNT montrent n/N ;
    les règles monétaires montrent le % consommé. `dim` estompe la jauge."""
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
    st.markdown(_bar_html(label, detail, ratio, color, dim=dim), unsafe_allow_html=True)


_BAND_BG = {
    C.LEVEL_OK: "rgba(53,208,127,0.12)",
    C.LEVEL_WARN: "rgba(245,178,61,0.13)",
    C.LEVEL_BLOCK: "rgba(255,93,98,0.14)",
}
_BAND_WORD = {C.LEVEL_OK: "Sous contrôle", C.LEVEL_WARN: "Vigilance",
              C.LEVEL_BLOCK: "Limite atteinte"}
_BAND_CHIP = {C.LEVEL_OK: "OK", C.LEVEL_WARN: "VIGILANCE", C.LEVEL_BLOCK: "LIMITE"}
_BAND_SUB = {
    C.LEVEL_OK: "Tu es loin de tes limites. Continue de loguer chaque trade.",
    C.LEVEL_WARN: "Tu approches une de tes limites. Ralentis, respecte ton plan.",
    C.LEVEL_BLOCK: "Une ou plusieurs de tes limites sont franchies.",
}


def render_status_band(risk_state: E.RiskState, account: E.Account,
                       base_balance: float, currency: str) -> None:
    """Bandeau de statut : le signal à lire en un coup d'œil (niveau + chiffre du jour)."""
    if risk_state.locked:
        level, word, chip = C.LEVEL_BLOCK, "STOP — mode strict", "STOP"
        sub = "Aucune nouvelle position autorisée jusqu'au prochain reset."
    else:
        level = risk_state.global_level
        word, chip, sub = _BAND_WORD[level], _BAND_CHIP[level], _BAND_SUB[level]
    color = LEVEL_COLORS[level]
    p = TH.pal()

    # Chiffre du jour : perte potentielle vs limite journalière (si la règle est active).
    dl = next((s for s in risk_state.rule_states
               if s.rule_type == C.RULE_DAILY_LOSS and s.is_money and s.limit), None)
    fig = ""
    if dl is not None:
        perte = max(dl.consumed, 0.0)
        pct = int(min(max(dl.ratio or 0.0, 0.0), 1.0) * 100)
        fig = f"""
          <div style="flex:1;min-width:190px;">
            <div style="display:flex;justify-content:space-between;align-items:baseline;
                        font-size:0.8rem;color:{p['muted']};margin-bottom:6px;">
              <span>Perte potentielle du jour</span>
              <span style="color:{p['text']};font-weight:600;">
                {format_money(perte, currency)} / {format_money(dl.limit, currency)}</span>
            </div>
            <div style="height:9px;border-radius:6px;background:rgba(128,128,128,0.18);overflow:hidden;">
              <div style="width:{pct}%;height:100%;border-radius:6px;background:{color};"></div>
            </div>
          </div>"""

    st.markdown(_flush(f"""
      <div style="display:flex;align-items:center;gap:22px;flex-wrap:wrap;background:{_BAND_BG[level]};
                  border:1px solid {color}55;border-left:5px solid {color};border-radius:12px;
                  padding:16px 20px;margin:6px 0 18px;">
        <div style="min-width:200px;">
          <div style="display:flex;align-items:center;gap:10px;">
            <span style="font-family:ui-monospace,monospace;font-size:0.62rem;font-weight:700;
                         letter-spacing:.05em;background:{color};color:#0E1330;padding:2px 9px;
                         border-radius:20px;">{chip}</span>
            <span style="font-size:1.35rem;font-weight:800;color:{color};">{word}</span>
          </div>
          <div style="font-size:0.82rem;color:{p['muted']};margin-top:5px;max-width:260px;">{sub}</div>
        </div>
        {fig}
      </div>
    """), unsafe_allow_html=True)


def render_position(trade, currency: str) -> None:
    """Ligne de position compacte avec badge BUY/SELL (theme-aware)."""
    p = TH.pal()
    side = C.DIRECTION_LABELS.get(trade.direction, trade.direction)
    is_buy = trade.direction == "LONG"
    badge_bg = "rgba(91,124,250,0.16)" if is_buy else "rgba(255,93,98,0.15)"
    badge_fg = "#7C93FF" if is_buy else "#FF7A7E"
    tag = f" · 🏷️ {trade.emotion_tag}" if trade.emotion_tag else ""
    st.markdown(_flush(f"""
      <div style="display:flex;align-items:center;gap:12px;background:{p['card']};
                  border:1px solid {p['border']};border-radius:10px;padding:9px 14px;margin-bottom:8px;">
        <span style="font-family:ui-monospace,monospace;font-size:0.72rem;color:{p['muted']};">#{trade.id}</span>
        <span style="font-weight:700;">{trade.instrument}</span>
        <span style="font-family:ui-monospace,monospace;font-size:0.66rem;font-weight:700;background:{badge_bg};
                     color:{badge_fg};padding:1px 8px;border-radius:5px;">{side}</span>
        <span style="margin-left:auto;color:{p['muted']};font-size:0.85rem;">
          {format_money(trade.planned_risk_amount, currency)} · {trade.planned_risk_pct*100:.2f}% · {trade.planned_risk_R:.2f}R{tag}</span>
      </div>
    """), unsafe_allow_html=True)
