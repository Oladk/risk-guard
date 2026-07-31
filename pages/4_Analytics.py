"""Dashboard analytics : équité, win rate, R moyen, P&L par émotion, respect des règles."""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import altair as alt
import pandas as pd
import streamlit as st

from src import constants as C
from src import repository as R
from src import service
from components import risk_meters as RM

conn = st.session_state.get("_conn") or service.connect()
account_id = st.session_state.get("account_id", 1)
account, rules, trades, adjustments, rs, now = service.evaluate_now(conn, account_id=account_id)
cur = account.base_currency

st.title("📊 Analytics")

closed = [t for t in trades if t.status == C.STATUS_CLOSED and t.closed_at is not None]
if not closed:
    st.info("Pas encore de trades clôturés à analyser. Reviens après quelques clôtures.")
    st.stop()

df = pd.DataFrame([{
    "id": t.id,
    "instrument": t.instrument,
    "marché": t.market,
    "sens": C.DIRECTION_LABELS.get(t.direction, t.direction),
    "closed_at": t.closed_at,
    "jour": t.closed_at.strftime("%A"),
    "pnl": t.realized_pnl_amount or 0.0,
    "R": t.realized_R or 0.0,
    "résultat": t.outcome or "",
    "émotion": t.emotion_tag or "(aucun)",
} for t in closed])
df["closed_at"] = pd.to_datetime(df["closed_at"], utc=True)

# --- Filtres -----------------------------------------------------------------
f1, f2, f3 = st.columns(3)
markets = f1.multiselect("Marché", sorted(df["marché"].unique()))
emotions = f2.multiselect("Émotion", sorted(df["émotion"].unique()))
min_d, max_d = df["closed_at"].min().date(), df["closed_at"].max().date()
date_range = f3.date_input("Période", value=(min_d, max_d))

view = df.copy()
if markets:
    view = view[view["marché"].isin(markets)]
if emotions:
    view = view[view["émotion"].isin(emotions)]
if isinstance(date_range, (list, tuple)) and len(date_range) == 2:
    d0, d1 = date_range
    view = view[(view["closed_at"].dt.date >= d0) & (view["closed_at"].dt.date <= d1)]

if view.empty:
    st.warning("Aucun trade ne correspond aux filtres.")
    st.stop()

# --- KPIs --------------------------------------------------------------------
n = len(view)
win_rate = (view["résultat"] == "WIN").mean() * 100
avg_R = view["R"].mean()
wins = view[view["résultat"] == "WIN"]["R"]
losses = view[view["résultat"] == "LOSS"]["R"]
total_pnl = view["pnl"].sum()

k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Trades clôturés", n)
k2.metric("Win rate", f"{win_rate:.0f}%")
k3.metric("R moyen (espérance)", f"{avg_R:+.2f}R")
k4.metric("Gain moy. / Perte moy.",
          f"{wins.mean():+.2f}R" if not wins.empty else "—",
          f"{losses.mean():+.2f}R" if not losses.empty else "—",
          delta_color="off")
k5.metric("P&L total", RM.format_money(total_pnl, cur))

st.divider()

# --- Courbe d'équité ---------------------------------------------------------
st.subheader("Courbe d'équité (P&L cumulé réalisé)")
eq = view.sort_values("closed_at").copy()
eq["équité"] = eq["pnl"].cumsum()
equity_chart = (
    alt.Chart(eq)
    .mark_line(point=True, color="#2ecc71")
    .encode(x=alt.X("closed_at:T", title="Date de clôture"),
            y=alt.Y("équité:Q", title=f"P&L cumulé ({cur})"),
            tooltip=["id", "instrument", "pnl", "R", "équité"])
    .properties(height=280)
)
st.altair_chart(equity_chart, use_container_width=True)

# --- P&L par émotion (le différenciateur) -----------------------------------
c_left, c_right = st.columns(2)
with c_left:
    st.subheader("Performance par émotion")
    emo = (view.groupby("émotion")
           .agg(pnl=("pnl", "sum"), R_moyen=("R", "mean"), trades=("id", "count"))
           .reset_index())
    emo_chart = (
        alt.Chart(emo)
        .mark_bar()
        .encode(x=alt.X("émotion:N", sort="-y"),
                y=alt.Y("R_moyen:Q", title="R moyen"),
                color=alt.condition(alt.datum.R_moyen >= 0,
                                    alt.value("#2ecc71"), alt.value("#e63946")),
                tooltip=["émotion", "R_moyen", "pnl", "trades"])
        .properties(height=260)
    )
    st.altair_chart(emo_chart, use_container_width=True)

with c_right:
    st.subheader("Répartition par marché")
    mk = (view.groupby("marché")
          .agg(pnl=("pnl", "sum"), trades=("id", "count")).reset_index())
    mk_chart = (
        alt.Chart(mk)
        .mark_bar(color="#4c9be8")
        .encode(x=alt.X("marché:N"), y=alt.Y("pnl:Q", title=f"P&L ({cur})"),
                tooltip=["marché", "pnl", "trades"])
        .properties(height=260)
    )
    st.altair_chart(mk_chart, use_container_width=True)

st.divider()

# --- Respect des règles ------------------------------------------------------
st.subheader("Respect des règles")
alerts = R.load_alerts(conn, account_id=account.id)
if not alerts:
    st.success("Aucun dépassement enregistré — discipline parfaite. 🟢")
else:
    adf = pd.DataFrame([{"rule": a["rule_type"], "level": a["level"]} for a in alerts])
    adf["règle"] = adf["rule"].map(C.RULE_LABELS).fillna(adf["rule"])
    summary = (adf.groupby(["règle", "level"]).size()
               .reset_index(name="occurrences"))
    b1, b2 = st.columns([1, 2])
    b1.metric("Alertes BLOCK", int((adf["level"] == "BLOCK").sum()))
    b1.metric("Alertes WARN", int((adf["level"] == "WARN").sum()))
    respect_chart = (
        alt.Chart(summary)
        .mark_bar()
        .encode(x=alt.X("occurrences:Q"), y=alt.Y("règle:N", sort="-x"),
                color=alt.Color("level:N",
                                scale=alt.Scale(domain=["WARN", "BLOCK"],
                                                range=["#f39c12", "#e63946"])),
                tooltip=["règle", "level", "occurrences"])
        .properties(height=240)
    )
    b2.altair_chart(respect_chart, use_container_width=True)
