"""Configuration : comptes · règles de risque · ajustements · taux FX · audit."""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import streamlit as st

from src import behavior as B
from src import constants as C
from src import correlation as CO
from src import db as DB
from src import fx
from src import repository as R
from src import risk_engine as E
from src import service
from components import risk_meters as RM

conn = st.session_state.get("_conn") or service.connect()
current_user_id = st.session_state.get("user_id")
account_id = st.session_state.get("account_id", 1)
account, rules, trades, adjustments, rs, now = service.evaluate_now(conn, account_id=account_id)
cur = account.base_currency

st.title("⚙️ Règles & compte")

TIMEZONES = ["UTC", "Africa/Porto-Novo", "Africa/Abidjan", "Africa/Lagos",
             "Africa/Dakar", "Europe/Paris", "Europe/London", "America/New_York"]
if account.timezone not in TIMEZONES:
    TIMEZONES.insert(0, account.timezone)
WEEK_STARTS = ["MONDAY", "SUNDAY"]

# ============================================================================
# 0. Comptes (création)
# ============================================================================
with st.expander("➕ Créer un nouveau compte"):
    with st.form("create_account_form", clear_on_submit=True):
        n1, n2, n3 = st.columns(3)
        new_name = n1.text_input("Nom", value="Nouveau compte")
        new_ccy = n2.text_input("Devise", value="XOF")
        new_balance = n3.number_input("Solde initial", min_value=0.0, value=1_000_000.0,
                                      step=10_000.0)
        n4, n5 = st.columns(2)
        new_tz = n4.selectbox("Fuseau", TIMEZONES, index=TIMEZONES.index("Africa/Porto-Novo")
                              if "Africa/Porto-Novo" in TIMEZONES else 0, key="new_tz")
        new_reset = n5.number_input("Reset (0–23)", min_value=0, max_value=23, value=0)
        if st.form_submit_button("Créer le compte", type="primary"):
            new_id = R.create_account(conn, name=new_name.strip() or "Compte",
                                      base_currency=new_ccy.strip() or "XOF",
                                      initial_balance=new_balance, timezone=new_tz,
                                      reset_hour=int(new_reset),
                                      user_id=current_user_id or 1)
            st.session_state["account_id"] = new_id
            st.session_state.pop("account_selector_box", None)  # force le sélecteur
            st.success(f"Compte « {new_name} » créé et sélectionné.")
            st.rerun()

# ============================================================================
# 1. Compte courant
# ============================================================================
st.subheader(f"Compte : {account.name}")
with st.form("account_form"):
    a0, a1, a2 = st.columns(3)
    name = a0.text_input("Nom du compte", value=account.name)
    base_currency = a1.text_input("Devise", value=account.base_currency)
    initial_balance = a2.number_input("Solde initial", min_value=0.0,
                                      value=float(account.initial_balance), step=10_000.0)

    a3, a4, a5 = st.columns(3)
    timezone = a3.selectbox("Fuseau horaire", TIMEZONES, index=TIMEZONES.index(account.timezone))
    reset_hour = a4.number_input("Heure de reset journalier (0–23)", min_value=0, max_value=23,
                                 value=int(account.reset_hour))
    week_start = a5.selectbox("Début de semaine", WEEK_STARTS,
                              index=WEEK_STARTS.index(account.week_start)
                              if account.week_start in WEEK_STARTS else 0)

    a6, a7, a8 = st.columns(3)
    warning_threshold = a6.slider("Seuil d'avertissement (% de la limite)",
                                  min_value=50, max_value=95,
                                  value=int(account.warning_threshold_pct * 100), step=5)
    preferred_unit = a7.radio("Unité préférée", [C.UNIT_PCT, C.UNIT_R],
                              index=0 if account.preferred_unit == C.UNIT_PCT else 1,
                              horizontal=True)
    one_R_pct = a8.number_input("1R vaut (% du capital)", min_value=0.01, max_value=100.0,
                                value=float(account.one_R_pct * 100), step=0.25) / 100.0

    a9, a10 = st.columns(2)
    sound_enabled = a9.checkbox("🔊 Son des alertes", value=account.sound_enabled)
    notify_enabled = a10.checkbox("📱 Notifications externes", value=account.notify_enabled)

    if DB.is_postgres():
        st.caption("🔒 **Synchronisation MT5 : à venir.** Elle nécessite un poste Windows avec le "
                   "terminal MetaTrader 5 ouvert — indisponible sur la version en ligne pour l'instant.")
        kind = account.kind
        enforce_enabled = account.enforce_enabled
        mt5_login, mt5_server, mt5_path = account.mt5_login, account.mt5_server, account.mt5_path
    else:
        st.markdown("**Connexion broker MT5 (optionnel)** — le terminal MT5 doit être ouvert "
                    "et connecté au compte.")
        k1, k2 = st.columns(2)
        kind = k1.selectbox("Type de compte", ["MANUAL", "MT5"],
                            index=0 if account.kind != "MT5" else 1)
        enforce_enabled = k2.checkbox("⚡ Enforcement : fermer les positions au blocage",
                                      value=account.enforce_enabled,
                                      help="Si activé, tu pourras fermer toutes les positions "
                                           "MT5 d'un clic quand une limite verrouillante est atteinte.")
        m1, m2, m3 = st.columns(3)
        mt5_login = m1.number_input("MT5 login (optionnel)", min_value=0,
                                    value=int(account.mt5_login or 0), step=1)
        mt5_server = m2.text_input("MT5 serveur (optionnel)", value=account.mt5_server)
        mt5_path = m3.text_input("Chemin terminal MT5 (optionnel)", value=account.mt5_path)

    if st.form_submit_button("💾 Enregistrer le compte", type="primary"):
        R.save_account(conn, E.Account(
            id=account.id, name=name.strip() or account.name, kind=kind,
            base_currency=base_currency.strip() or "XOF",
            initial_balance=initial_balance, timezone=timezone, reset_hour=int(reset_hour),
            week_start=week_start, warning_threshold_pct=warning_threshold / 100.0,
            preferred_unit=preferred_unit, one_R_pct=one_R_pct,
            sound_enabled=sound_enabled, notify_enabled=notify_enabled,
            mt5_login=int(mt5_login) or None, mt5_server=mt5_server.strip(),
            mt5_path=mt5_path.strip(), enforce_enabled=enforce_enabled,
        ))
        st.success("Compte enregistré.")
        st.rerun()

st.caption(f"Solde de début de journée courant : **{RM.format_money(rs.day_start_balance, cur)}**")

st.divider()

# ============================================================================
# 2. Règles de risque (clés namespacées par compte)
# ============================================================================
st.subheader("Règles de risque")
st.caption("Coche pour activer. Les règles de perte se règlent en % du capital ou en R ; "
           "les autres en nombre. Alerte orange à "
           f"{int(account.warning_threshold_pct*100)}% du seuil, alerte rouge à 100%.")
st.info("Par défaut, chaque règle est en **Alerte** : l'outil te **prévient** fortement mais te "
        "laisse décider. Passe une règle en **Blocage (strict)** seulement si tu veux qu'il "
        "**refuse** d'enregistrer un trade qui la viole.")

_closed = [t for t in trades if t.status == C.STATUS_CLOSED and t.outcome in ("WIN", "LOSS")]
_sugg = B.suggest_limits(_closed)
if _sugg:
    st.info(f"💡 **Suggestion data-driven** (sur {_sugg.n} trades) : risque/trade "
            f"≈ **{_sugg.per_trade_pct*100:.2f}%**, perte max/jour "
            f"≈ **{_sugg.daily_loss_pct*100:.2f}%**. {_sugg.rationale} "
            f"(À valider — l'outil suggère, tu décides.)")
else:
    st.caption("💡 Des suggestions de limites data-driven apparaîtront après ~20 trades clôturés.")

with st.form("rules_form"):
    new_values = {}
    for rule in rules:
        rt = rule.rule_type
        kp = f"{account.id}_{rt}"  # namespace par compte
        st.markdown(f"**{C.RULE_LABELS[rt]}** — {C.RULE_HELP[rt]}")
        col_en, col_val, col_unit, col_act = st.columns([1, 1.4, 1.2, 1.2])
        enabled = col_en.checkbox("Activée", value=rule.enabled, key=f"en_{kp}")

        if rule.threshold_unit == C.UNIT_COUNT:
            value = col_val.number_input("Seuil (nombre)", min_value=1,
                                         value=int(rule.threshold_value), key=f"val_{kp}")
            unit = C.UNIT_COUNT
            col_unit.write("")
            col_unit.caption("nombre")
        else:
            unit = col_unit.radio("Unité", [C.UNIT_PCT, C.UNIT_R],
                                  index=0 if rule.threshold_unit == C.UNIT_PCT else 1,
                                  horizontal=True, key=f"unit_{kp}")
            if unit == C.UNIT_PCT:
                display = rule.threshold_value * 100 if rule.threshold_unit == C.UNIT_PCT \
                    else rule.threshold_value * account.one_R_pct * 100
                value = col_val.number_input("Seuil (%)", min_value=0.0,
                                             value=float(display), step=0.5, key=f"val_{kp}") / 100.0
            else:
                display = rule.threshold_value if rule.threshold_unit == C.UNIT_R \
                    else rule.threshold_value / account.one_R_pct
                value = col_val.number_input("Seuil (R)", min_value=0.0,
                                             value=float(display), step=0.25, key=f"val_{kp}")

        action = col_act.selectbox(
            "Action", ["WARN", "BLOCK"], index=1 if rule.action == "BLOCK" else 0,
            format_func=lambda x: "Alerte" if x == "WARN" else "Blocage (strict)",
            key=f"act_{kp}")
        new_values[rt] = (enabled, value, unit, action)
        st.markdown("<hr style='margin:6px 0;border:none;border-top:1px solid rgba(128,128,128,0.25);'>",
                    unsafe_allow_html=True)

    if st.form_submit_button("💾 Enregistrer les règles", type="primary"):
        for rule in rules:
            enabled, value, unit, action = new_values[rule.rule_type]
            R.save_rule(conn, E.Rule(rule_type=rule.rule_type, enabled=enabled,
                                     threshold_value=value, threshold_unit=unit, action=action),
                        account_id=account.id)
        st.success("Règles enregistrées.")
        st.rerun()

st.divider()

# ============================================================================
# 3. Ajustements de solde (dépôts / retraits)
# ============================================================================
st.subheader("Dépôts / retraits")
st.caption("Ajuste le solde de référence pour les dépôts et retraits (hors P&L de trading).")
with st.form("adj_form", clear_on_submit=True):
    j1, j2 = st.columns(2)
    amount = j1.number_input(f"Montant ({cur})", value=0.0, step=10_000.0, format="%.2f")
    kind = j2.selectbox("Type", ["DEPOSIT", "WITHDRAWAL"])
    if st.form_submit_button("Ajouter l'ajustement"):
        signed = abs(amount) if kind == "DEPOSIT" else -abs(amount)
        R.add_adjustment(conn, amount=signed, type_=kind, when=now, account_id=account.id)
        st.success("Ajustement enregistré.")
        st.rerun()

if adjustments:
    st.markdown("**Historique des ajustements :**")
    for a in adjustments:
        st.markdown(f"- {a.date.strftime('%Y-%m-%d')} · {a.type} · "
                    f"{RM.format_money(a.amount, cur)}")

st.divider()

# ============================================================================
# 4. Taux de change (A2 — multi-devises)
# ============================================================================
st.subheader("Taux de change")
st.caption("Pour convertir le risque/P&L quand la devise de cotation diffère de celle du compte "
           "(ex. compte XOF, paires en USD). Un taux sert aussi en sens inverse.")
with st.form("fx_form", clear_on_submit=True):
    x1, x2, x3 = st.columns(3)
    from_ccy = x1.text_input("De (devise)", value="USD")
    to_ccy = x2.text_input("Vers (devise)", value=cur)
    rate = x3.number_input("Taux (1 unité 'De' = ? 'Vers')", min_value=0.0,
                           value=600.0, step=1.0, format="%.4f")
    if st.form_submit_button("Enregistrer le taux"):
        fx.set_rate(conn, from_ccy.strip(), to_ccy.strip(), rate, when=now)
        st.success(f"Taux {from_ccy.upper()}→{to_ccy.upper()} = {rate} enregistré.")
        st.rerun()

rates = fx.load_rates(conn)
if rates:
    st.markdown("**Taux enregistrés :**")
    for (f, t), r in rates.items():
        st.markdown(f"- 1 {f} = {r} {t}")

st.divider()

# ============================================================================
# 5. Checklist pré-trade (A4)
# ============================================================================
st.subheader("Checklist pré-trade")
st.caption("Points à cocher avant chaque ouverture (compte courant). "
           "Ceux activés sont obligatoires pour valider un trade.")
for it in R.load_checklist(conn, account.id):
    col_c, col_d = st.columns([6, 1])
    new_enabled = col_c.checkbox(it["label"], value=bool(it["enabled"]),
                                 key=f"cli_{account.id}_{it['id']}")
    if new_enabled != bool(it["enabled"]):
        R.set_checklist_item(conn, it["id"], enabled=new_enabled)
        st.rerun()
    if col_d.button("🗑️", key=f"cldel_{account.id}_{it['id']}"):
        R.delete_checklist_item(conn, it["id"])
        st.rerun()

with st.form("add_checklist", clear_on_submit=True):
    new_label = st.text_input("Ajouter un point de checklist")
    if st.form_submit_button("Ajouter") and new_label.strip():
        R.add_checklist_item(conn, account.id, new_label.strip())
        st.rerun()

st.divider()

# ============================================================================
# 6. Corrélations entre instruments (A3)
# ============================================================================
st.subheader("Corrélations entre instruments")
st.caption("Sert au calcul du risque ouvert *effectif* dans le cockpit. Le garde-fou dur "
           "(exposition ouverte max) reste basé sur la somme simple.")
with st.form("add_corr", clear_on_submit=True):
    p1, p2, p3 = st.columns(3)
    ia = p1.text_input("Instrument A", value="EURUSD")
    ib = p2.text_input("Instrument B", value="GBPUSD")
    cval = p3.slider("Corrélation", min_value=-1.0, max_value=1.0, value=0.80, step=0.05)
    if st.form_submit_button("Enregistrer la corrélation"):
        CO.set_correlation(conn, ia.strip(), ib.strip(), cval, when=now)
        st.success(f"Corrélation {ia.upper()} ↔ {ib.upper()} = {cval:+.2f} enregistrée.")
        st.rerun()

corrs = CO.load_correlations(conn)
if corrs:
    st.markdown("**Corrélations enregistrées :**")
    for (a, b), c in corrs.items():
        st.markdown(f"- {a} ↔ {b} : {c:+.2f}")

st.divider()

# ============================================================================
# 7. Détection de tilt (C1)
# ============================================================================
st.subheader("Détection de tilt (comportement)")
st.caption("Seuils de l'alerte comportementale affichée au cockpit (compte courant).")
tcfg = R.load_tilt_config(conn, account.id)
with st.form("tilt_form"):
    t1, t2, t3 = st.columns(3)
    min_gap = t1.number_input("Ré-entrée rapprochée (< minutes)", min_value=0.0,
                              value=float(tcfg.min_gap_minutes), step=1.0)
    reentry = t2.number_input("Ré-entrée après perte (< minutes)", min_value=0.0,
                              value=float(tcfg.reentry_window_minutes), step=1.0)
    escal = t3.number_input("Montée de taille (× le risque)", min_value=1.0,
                            value=float(tcfg.escalation_ratio), step=0.1)
    t4, t5 = st.columns(2)
    emo_thr = t4.number_input("Nb de trades Revenge/FOMO", min_value=1,
                              value=int(tcfg.emotion_threshold))
    overtr = t5.number_input("Sur-trading (trades/jour)", min_value=1,
                             value=int(tcfg.overtrade_count))
    t6, t7 = st.columns(2)
    vig = t6.number_input("Seuil VIGILANCE (score /100)", min_value=1, max_value=100,
                          value=int(tcfg.vigilance_threshold))
    tilt_thr = t7.number_input("Seuil TILT (score /100)", min_value=1, max_value=100,
                               value=int(tcfg.tilt_threshold))
    if st.form_submit_button("💾 Enregistrer la détection de tilt", type="primary"):
        R.save_tilt_config(conn, account.id, B.TiltConfig(
            min_gap_minutes=min_gap, reentry_window_minutes=reentry,
            escalation_ratio=escal, emotion_threshold=int(emo_thr),
            overtrade_count=int(overtr), vigilance_threshold=int(vig),
            tilt_threshold=int(tilt_thr)))
        st.success("Détection de tilt enregistrée.")
        st.rerun()

st.divider()

# ============================================================================
# 8. Audit (log inviolable — A5)
# ============================================================================
with st.expander("🔒 Journal d'audit (événements append-only)"):
    events = R.load_trade_events(conn, account_id=account.id)
    if not events:
        st.caption("Aucun événement pour ce compte.")
    else:
        for e in events[:100]:
            st.markdown(f"- `{e['timestamp']}` · **{e['event_type']}** · "
                        f"trade #{e['trade_id']} · {e['payload'] or ''}")
