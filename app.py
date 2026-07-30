"""Cockpit de risque — page d'accueil.

Vue temps réel : solde de référence, P&L du jour, risque ouvert, jauges par règle,
overlay STOP si une limite verrouillante est franchie, et clôture des positions
(toujours autorisée, même en mode STOP).
"""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import streamlit as st

from src import constants as C
from src import repository as R
from src import risk_engine as E
from src import behavior as B
from src import correlation as CO
from src import risk_engine as E
from src import service
from src import time_utils as T
from src.brokers import sync as SY
from src.brokers.mt5 import MT5Connector
from components import account_selector
from components import alert_overlay as AO
from components import onboarding
from components import risk_meters as RM
from components import shell


def _mt5_connector(acc):
    return MT5Connector(login=acc.mt5_login, server=acc.mt5_server, path=acc.mt5_path)

st.set_page_config(page_title="Vigie — Cockpit", page_icon="🔭", layout="wide")

conn = service.connect()
shell.start(conn)

with st.sidebar:
    st.markdown("## 🔭 Vigie")
    st.caption("L'œil sur ton risque.")
    account_id = account_selector.render(conn)
    shell.sidebar_user_controls()

account, rules, trades, adjustments, rs, now = service.evaluate_now(conn, account_id=account_id)

if account_id and not R.is_onboarded(conn, account.id):
    onboarding.render(conn, account)
    st.stop()

cur = account.base_currency
dsb = rs.day_start_balance

# --- Barre latérale (suite) --------------------------------------------------
with st.sidebar:
    st.caption(f"Fuseau **{account.timezone}** · reset **{account.reset_hour:02d}h** · "
               f"unité **{account.preferred_unit}**")
    if account.sound_enabled:
        AO.enable_sound_button()
    if account.kind == "MT5":
        if st.button("🔄 Synchroniser MT5", use_container_width=True):
            try:
                res = SY.sync_account(conn, account, _mt5_connector(account), now)
                st.session_state["last_sync"] = "✅ " + res.summary()
            except Exception as e:  # terminal absent, non installé, etc.
                st.session_state["last_sync"] = f"❌ {e}"
            st.rerun()
        if st.session_state.get("last_sync"):
            st.caption(st.session_state["last_sync"])
    st.divider()
    st.page_link("pages/1_Journal.py", label="📓 Journal des trades", icon=None)
    st.page_link("pages/2_Regles_et_compte.py", label="⚙️ Règles & compte")

# --- En-tête / statut global -------------------------------------------------
if rs.locked:
    status_txt = "🔴 STOP (mode strict)"
else:
    status_txt = {
        C.LEVEL_OK: "🟢 Sous contrôle",
        C.LEVEL_WARN: "🟠 Vigilance",
        C.LEVEL_BLOCK: "🔴 Limite atteinte",
    }[rs.global_level]

top_l, top_r = st.columns([3, 1])
top_l.title("Cockpit de risque")
top_r.markdown(
    f"<div style='text-align:right;font-size:1.4rem;font-weight:700;margin-top:18px;'>"
    f"{status_txt}</div>", unsafe_allow_html=True)

st.caption("🔭 **Vigie** surveille ton risque et t'alerte quand tu approches tes limites — "
           "tu gardes toujours la main.")

with st.expander("❓ Comment ça marche (à lire une fois)", expanded=(len(trades) == 0)):
    st.markdown(
        "**Le principe, en 3 étapes :**\n\n"
        "1. **Tes limites sont déjà réglées** selon le profil choisi à l'inscription "
        "(ex. ne pas risquer de perdre plus de 3 % de ton capital dans la journée). "
        "Tu les ajustes quand tu veux dans **⚙️ Règles & compte**.\n"
        "2. **Note chaque trade ici.** Dès que tu **ouvres** une position chez ton broker, "
        "saisis-la dans **⚡ Saisie éclair** (instrument, sens, risque). Quand tu la **fermes**, "
        "indique ton résultat dans le **📓 Journal**.\n"
        "3. **L'outil t'alerte** quand tu approches (orange) ou atteins (rouge) une limite. "
        "**Il ne bloque pas et ne trade pas à ta place** — c'est toi qui décides quoi faire.\n\n"
        "> ℹ️ L'outil **ne se connecte pas à ton broker** : c'est toi qui notes tes trades, lui "
        "il surveille et te prévient. C'est ton **garde-fou personnel**."
    )

# --- Alerte forte ------------------------------------------------------------
if rs.locked:
    # Mode strict (le trader a passé une règle en BLOCK) : refus + STOP.
    AO.render_stop(rs, account)
    if account.kind == "MT5" and account.enforce_enabled:
        st.error("⚡ **Enforcement disponible** — tu peux fermer toutes tes positions MT5 maintenant.")
        confirm = st.checkbox("Je confirme vouloir fermer TOUTES mes positions MT5")
        if confirm and st.button("⚡ Fermer toutes les positions MT5", type="primary"):
            try:
                closed = SY.close_all_positions(_mt5_connector(account))
                st.success(f"{len(closed)} position(s) fermée(s) côté broker.")
            except Exception as e:
                st.error(f"Erreur enforcement : {e}")
else:
    # Mode conseil (défaut) : alertes fortes, aucune action imposée.
    AO.render_alerts(rs, sound=account.sound_enabled)

# --- Alerte comportementale (tilt) ------------------------------------------
_day_start, _day_end = T.trading_day_bounds(now, account.timezone, account.reset_hour)
tilt = B.assess_tilt(trades, now, _day_start, _day_end, cfg=R.load_tilt_config(conn, account.id))
if tilt.level != "CALME":
    _color = "#e63946" if tilt.level == "TILT" else "#f39c12"
    _icon = "🔴" if tilt.level == "TILT" else "🟠"
    _items = "".join(f"<li style='margin:2px 0;'>{s.label} — {s.detail}</li>"
                     for s in tilt.signals)
    st.markdown(
        f"""
        <div style="background:rgba(230,57,70,0.10);border-left:5px solid {_color};
                    border-radius:8px;padding:14px 18px;margin-bottom:16px;">
          <div style="color:{_color};font-weight:700;font-size:1.05rem;">
            {_icon} Alerte comportementale — {tilt.level} (score {tilt.score}/100)
          </div>
          <div style="color:#c8cdd8;font-size:0.9rem;margin-top:4px;">
            Tes patterns ressemblent à du tilt. Respire, respecte ton plan.
          </div>
          <ul style="color:#e0e0e0;margin:8px 0 0 0;">{_items}</ul>
        </div>
        """, unsafe_allow_html=True)

# --- Métriques clés ----------------------------------------------------------
m1, m2, m3, m4 = st.columns(4)
m1.metric("Solde début de journée", RM.format_money(dsb, cur))
m2.metric("P&L réalisé (jour)", RM.format_money(rs.realized_pnl_today, cur))
m3.metric("Risque ouvert", RM.format_money(rs.open_risk, cur))
m4.metric("Perte potentielle (jour)",
          RM.format_money(max(rs.worst_case_drawdown_today, 0.0), cur),
          help="Pertes réalisées + risque des positions ouvertes (worst-case).")

# Risque ouvert effectif (ajusté par corrélation) — informatif, la somme reste le garde-fou.
if rs.open_risk > 0:
    eff = CO.effective_open_risk(trades, CO.load_correlations(conn))
    ratio = eff / rs.open_risk if rs.open_risk else 1.0
    st.caption(
        f"🔗 Risque ouvert **effectif** (corrélation) : **{RM.format_money(eff, cur)}** "
        f"vs somme simple {RM.format_money(rs.open_risk, cur)} "
        f"({ratio*100:.0f}% — {'diversifié' if ratio < 0.98 else 'concentré/corrélé'})."
    )

# --- Saisie éclair (log rapide, sans friction) ------------------------------
with st.expander("⚡ Saisie éclair — loguer un trade en quelques secondes"):
    st.caption("À chaque position que tu ouvres chez ton broker, note-la ici. "
               "L'outil calcule ton risque et te prévient si tu approches une limite.")
    with st.form("quick_open", clear_on_submit=True):
        q1, q2, q3, q4 = st.columns([2.2, 1.2, 1.2, 1.2])
        q_instr = q1.text_input("Instrument", value="EURUSD")
        q_dir = q2.selectbox("Sens", C.DIRECTIONS,
                             format_func=lambda d: C.DIRECTION_LABELS[d], help=C.HELP_SENS)
        q_risk = q3.number_input("Risque %", min_value=0.0, value=1.0, step=0.25,
                                 help=C.HELP_RISQUE)
        q3.caption(f"≈ {RM.format_money(dsb * q_risk / 100, cur)}")
        q4.write("")
        q_go = q4.form_submit_button("Ouvrir", type="primary", use_container_width=True)
    if q_go:
        q_pct = q_risk / 100.0
        chk = E.check_new_trade(account, rules, trades, adjustments, now, dsb * q_pct)
        if chk.blocking:  # une règle en mode strict refuse
            st.error("⛔ Refusé (mode strict) : " + " ; ".join(m for _, m in chk.blocking))
        else:
            tid = R.open_trade(conn, account, q_instr.strip() or "?", "FOREX", q_dir,
                               risk_pct=q_pct, now=now)
            for rt, msg in chk.advisories:
                R.log_alert(conn, rt, C.LEVEL_WARN, now, context=msg, account_id=account.id)
            if chk.advisories:
                st.warning("🔴 Trade logué — mais il franchit une limite : "
                           + " ; ".join(m for _, m in chk.advisories))
            else:
                st.success(f"Trade #{tid} logué.")
            st.rerun()

st.divider()

# --- Jauges par règle --------------------------------------------------------
st.subheader("Limites de risque")
if not rs.rule_states:
    st.info("Aucune règle active. Configure tes limites dans **Règles & compte**.")
for s in rs.rule_states:
    if s.rule_type == C.RULE_PER_TRADE_RISK:
        st.caption(f"ℹ️ {s.message}")
    else:
        RM.render_rule_gauge(s, account, dsb)

st.divider()

# --- Positions ouvertes + clôture -------------------------------------------
st.subheader("Positions ouvertes")
open_positions = [t for t in trades if t.status == C.STATUS_OPEN]

if not open_positions:
    st.info("Aucune position ouverte.")
else:
    for t in open_positions:
        risk_disp = RM.format_money(t.planned_risk_amount, cur)
        st.markdown(
            f"**#{t.id} · {t.instrument}** ({t.market}, {C.DIRECTION_LABELS.get(t.direction, t.direction)}) — "
            f"risque {risk_disp} · {t.planned_risk_pct*100:.2f}% · {t.planned_risk_R:.2f}R"
            + (f" · 🏷️ {t.emotion_tag}" if t.emotion_tag else "")
        )

    st.markdown("##### Clôturer une position")
    st.caption("La clôture reste possible même en mode STOP — le journal doit rester juste.")
    with st.form("close_form", clear_on_submit=True):
        labels = {f"#{t.id} · {t.instrument} ({C.DIRECTION_LABELS.get(t.direction, t.direction)})": t.id
                  for t in open_positions}
        choice = st.selectbox("Position", list(labels.keys()))
        pnl = st.number_input(
            f"P&L réalisé ({cur}) — négatif si perte", value=0.0, step=100.0, format="%.2f")
        if st.form_submit_button("Clôturer la position", type="primary"):
            R.close_trade(conn, labels[choice], realized_pnl_amount=pnl, now=now)
            st.success(f"Position {choice} clôturée ({RM.format_money(pnl, cur)}).")
            st.rerun()
