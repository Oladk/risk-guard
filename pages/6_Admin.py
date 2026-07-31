"""Tableau de bord admin — usage du pilote (réservé à l'administrateur)."""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from datetime import timedelta

import pandas as pd
import streamlit as st

from src import auth
from src import service
from src import time_utils as T

conn = st.session_state.get("_conn") or service.connect()

if not auth.is_admin(conn):
    st.error("🔒 Page réservée à l'administrateur.")
    st.stop()

st.title("🛠️ Admin — usage")
st.caption("Le tableau de bord du pilote : est-ce que les gens **utilisent** Vigie et "
           "**loguent** leurs trades ? C'est le seul chiffre qui décide de la suite.")

now = T.now_utc()
cutoff = (now - timedelta(days=7)).isoformat()


def _scalar(sql, params=()):
    return conn.execute(sql, params).fetchone()["n"]


n_users = _scalar("SELECT COUNT(*) AS n FROM users")
n_accounts = _scalar("SELECT COUNT(*) AS n FROM accounts")
n_trades = _scalar("SELECT COUNT(*) AS n FROM trades")
n_activated = _scalar("""SELECT COUNT(DISTINCT a.user_id) AS n FROM accounts a
                         JOIN trades t ON t.account_id = a.id""")
n_trades_7d = _scalar("SELECT COUNT(*) AS n FROM trades WHERE opened_at >= ?", (cutoff,))
n_active_7d = _scalar("""SELECT COUNT(DISTINCT a.user_id) AS n FROM accounts a
                         JOIN trades t ON t.account_id = a.id WHERE t.opened_at >= ?""",
                      (cutoff,))
n_alerts = _scalar("SELECT COUNT(*) AS n FROM alerts_log")

activation = (n_activated / n_users * 100) if n_users else 0.0

k1, k2, k3, k4 = st.columns(4)
k1.metric("Inscrits", n_users)
k2.metric("Ont logué ≥1 trade", n_activated, f"{activation:.0f}% d'activation")
k3.metric("Actifs (7 jours)", n_active_7d)
k4.metric("Trades (7 jours)", n_trades_7d)

k5, k6, k7 = st.columns(3)
k5.metric("Comptes créés", n_accounts)
k6.metric("Trades logués (total)", n_trades)
k7.metric("Alertes déclenchées", n_alerts)

if n_users == 0:
    st.info("Aucun utilisateur enregistré (probablement en mode local sans authentification). "
            "Ces chiffres deviennent parlants sur le déploiement cloud, avec de vrais comptes.")

st.divider()
st.subheader("Activité par utilisateur")

rows = conn.execute(
    """SELECT u.username AS utilisateur,
              COUNT(t.id) AS trades,
              MAX(t.opened_at) AS dernier_trade,
              u.created_at AS inscrit_le
       FROM users u
       LEFT JOIN accounts a ON a.user_id = u.id
       LEFT JOIN trades t ON t.account_id = a.id
       GROUP BY u.id, u.username, u.created_at
       ORDER BY trades DESC, u.id"""
).fetchall()

if not rows:
    st.caption("Rien à afficher pour l'instant.")
else:
    df = pd.DataFrame([{
        "utilisateur": r["utilisateur"],
        "trades logués": r["trades"],
        "dernier trade": (r["dernier_trade"] or "")[:10],
        "inscrit le": (r["inscrit_le"] or "")[:10],
    } for r in rows])
    st.dataframe(df, use_container_width=True, hide_index=True)
    st.caption("💡 Le chiffre à surveiller : le **taux d'activation** (combien loguent vraiment). "
               "S'il est bas, le problème est la friction de saisie, pas les fonctionnalités.")
