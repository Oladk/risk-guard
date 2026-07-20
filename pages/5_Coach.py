"""Coach hebdomadaire (C2) : ce que tu dois changer, pas seulement ce qui s'est passé."""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from zoneinfo import ZoneInfo

import altair as alt
import pandas as pd
import streamlit as st

from src import behavior as B
from src import constants as C
from src import service
from components import account_selector
from components import shell

st.set_page_config(page_title="Coach", page_icon="🧠", layout="wide")

conn = service.connect()
shell.start(conn)
with st.sidebar:
    account_id = account_selector.render(conn)
    shell.sidebar_user_controls()
account, rules, trades, adjustments, rs, now = service.evaluate_now(conn, account_id=account_id)

st.title("🧠 Coach")
st.caption("Analyse comportementale prescriptive : quoi changer pour la semaine prochaine.")

closed = [t for t in trades if t.status == C.STATUS_CLOSED
          and t.outcome in ("WIN", "LOSS") and t.realized_R is not None]
if len(closed) < 3:
    st.info("Pas assez de trades clôturés pour un coaching pertinent. Reviens après "
            "quelques trades.")
    st.stop()

tz = ZoneInfo(account.timezone)
df = pd.DataFrame([{
    "R": t.realized_R,
    "gagnant": t.outcome == "WIN",
    "émotion": t.emotion_tag or "(aucun)",
    "setup": t.setup or "(non renseigné)",
    "instrument": t.instrument,
    "heure": t.closed_at.astimezone(tz).hour,
    "jour": t.closed_at.astimezone(tz).strftime("%A"),
} for t in closed])

# --- KPIs prescriptifs -------------------------------------------------------
wr_after, wr_overall, n_after = B.conditional_winrate_after_loss(closed)
k1, k2, k3 = st.columns(3)
k1.metric("Win rate global", f"{wr_overall*100:.0f}%")
k2.metric("Espérance", f"{B.expectancy_R(closed):+.2f}R")
if wr_after is not None:
    delta = (wr_after - wr_overall) * 100
    k3.metric("Win rate APRÈS une perte", f"{wr_after*100:.0f}%",
              f"{delta:+.0f} pts vs global", delta_color="normal")
    if delta <= -10:
        st.warning(f"⚠️ Ton win rate chute de {abs(delta):.0f} points après une perte "
                   f"({n_after} cas). Signe classique de tilt — fais une pause après un stop.")

st.divider()

# --- Coût des émotions -------------------------------------------------------
st.subheader("Coût des émotions")
emo = (df.groupby("émotion").agg(R_moyen=("R", "mean"), trades=("R", "count"),
                                 total_R=("R", "sum")).reset_index())
emo_chart = (
    alt.Chart(emo).mark_bar()
    .encode(x=alt.X("émotion:N", sort="-y"), y=alt.Y("R_moyen:Q", title="R moyen"),
            color=alt.condition(alt.datum.R_moyen >= 0, alt.value("#2ecc71"),
                                alt.value("#e63946")),
            tooltip=["émotion", "R_moyen", "trades", "total_R"])
    .properties(height=260))
st.altair_chart(emo_chart, use_container_width=True)
worst = emo.sort_values("total_R").iloc[0]
if worst["total_R"] < 0 and worst["émotion"] != "(aucun)":
    st.markdown(f"👉 **{worst['émotion']}** te coûte **{worst['total_R']:+.1f}R** au total "
                f"sur {int(worst['trades'])} trade(s). À surveiller.")

st.divider()

# --- Quand tradés-tu le mieux ? ---------------------------------------------
c1, c2 = st.columns(2)
with c1:
    st.subheader("Performance par heure")
    by_hour = df.groupby("heure").agg(R_moyen=("R", "mean"), trades=("R", "count")).reset_index()
    st.altair_chart(
        alt.Chart(by_hour).mark_bar(color="#4c9be8")
        .encode(x=alt.X("heure:O", title="Heure (locale)"), y="R_moyen:Q",
                tooltip=["heure", "R_moyen", "trades"]).properties(height=240),
        use_container_width=True)
with c2:
    st.subheader("Performance par jour")
    by_day = df.groupby("jour").agg(R_moyen=("R", "mean"), trades=("R", "count")).reset_index()
    st.altair_chart(
        alt.Chart(by_day).mark_bar(color="#9b6ce8")
        .encode(x=alt.X("jour:N", sort=None), y="R_moyen:Q",
                tooltip=["jour", "R_moyen", "trades"]).properties(height=240),
        use_container_width=True)

st.divider()

# --- Par setup & instrument --------------------------------------------------
st.subheader("Espérance par setup")
by_setup = (df.groupby("setup").agg(R_moyen=("R", "mean"), trades=("R", "count"),
                                    win_rate=("gagnant", "mean")).reset_index())
by_setup["win_rate"] = (by_setup["win_rate"] * 100).round(0)
by_setup["R_moyen"] = by_setup["R_moyen"].round(2)
st.dataframe(by_setup.sort_values("R_moyen", ascending=False),
             use_container_width=True, hide_index=True)
