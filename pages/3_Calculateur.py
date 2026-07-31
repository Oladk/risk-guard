"""Calculateur de taille de position → pré-remplit un nouveau trade."""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import streamlit as st

from src import constants as C
from src import service
from src import sizing as S
from components import risk_meters as RM

conn = st.session_state.get("_conn") or service.connect()
account_id = st.session_state.get("account_id", 1)
account, rules, trades, adjustments, rs, now = service.evaluate_now(conn, account_id=account_id)
cur = account.base_currency
dsb = rs.day_start_balance

st.title("🧮 Calculateur de taille de position")
st.caption(f"Solde de référence : **{RM.format_money(dsb, cur)}** · "
           f"1R = {account.one_R_pct*100:.2f}%")

c1, c2, c3 = st.columns(3)
market = c1.selectbox("Marché", C.MARKETS)
instrument = c2.text_input("Instrument", value="EURUSD" if market == "FOREX" else "SNTS")
unit = c3.radio("Unité de risque", [C.UNIT_PCT, C.UNIT_R],
                index=0 if account.preferred_unit == C.UNIT_PCT else 1, horizontal=True)

c4, c5, c6 = st.columns(3)
if unit == C.UNIT_PCT:
    risk_val = c4.number_input("Risque (%)", min_value=0.0, value=1.0, step=0.25)
    risk_pct = risk_val / 100.0
else:
    risk_val = c4.number_input("Risque (R)", min_value=0.0, value=1.0, step=0.25)
    risk_pct = risk_val * account.one_R_pct
entry = c5.number_input("Prix d'entrée", min_value=0.0, value=1.10000, format="%.5f")
stop = c6.number_input("Stop", min_value=0.0, value=1.09500, format="%.5f")

conversion_rate = 1.0
if market == "FOREX":
    conversion_rate = st.number_input(
        "Taux de conversion (1 unité devise de cotation = ? "
        f"{cur}) — laisse 1 si cotation = {cur}",
        min_value=0.0001, value=1.0, step=0.0001, format="%.4f")

risk_amount = dsb * risk_pct
st.caption(f"Risque en devise : **{RM.format_money(risk_amount, cur)}** "
           f"({risk_pct*100:.2f}% · {risk_pct/account.one_R_pct:.2f}R)")

if st.button("Calculer", type="primary"):
    try:
        res = S.size_position(market, risk_amount, entry, stop, pair=instrument,
                              conversion_rate=conversion_rate)
    except ValueError as e:
        st.error(str(e))
    else:
        st.session_state["last_sizing"] = {
            "instrument": instrument, "market": market, "risk_pct": risk_pct * 100}
        m1, m2, m3 = st.columns(3)
        m1.metric(f"Taille ({res.size_unit})", f"{res.size:,.4f}".replace(",", " "))
        m2.metric("Distance au stop",
                  f"{res.distance:.5f}" + (f" ({res.distance_pips:.1f} pips)"
                                           if res.distance_pips else ""))
        m3.metric("Risque", RM.format_money(res.risk_amount, cur))
        if res.pip_value_per_lot:
            st.caption(f"Valeur d'un pip pour 1 lot ≈ "
                       f"{RM.format_money(res.pip_value_per_lot, cur)}. {res.note}")
        else:
            st.caption(res.note)

# Bouton de pré-remplissage (hors du if pour survivre au rerun du bouton Calculer).
if "last_sizing" in st.session_state:
    st.divider()
    if st.button("➡️ Utiliser ces paramètres dans un nouveau trade"):
        st.session_state["prefill"] = st.session_state["last_sizing"]
        st.switch_page("pages/1_Journal.py")
