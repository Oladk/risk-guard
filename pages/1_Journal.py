"""Journal des trades : ouvrir (avec contrôle de risque) / clôturer / historique."""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import pandas as pd
import streamlit as st

from src import constants as C
from src import notify as N
from src import repository as R
from src import risk_engine as E
from src import service
from components import account_selector
from components import alert_overlay as AO
from components import risk_meters as RM
from components import shell


def _push_notification(kind: str, lines: list[str]) -> None:
    """Répercute une alerte vers email/ntfy si les notifications sont activées."""
    if not account.notify_enabled:
        return
    email_cfg, ntfy_cfg = N.read_secrets()
    if email_cfg is None and ntfy_cfg is None:
        return
    subject, body = N.build_message(kind, lines)
    N.notify(subject, body, email_cfg, ntfy_cfg)

st.set_page_config(page_title="Journal", page_icon="📓", layout="wide")

conn = service.connect()
shell.start(conn)
with st.sidebar:
    account_id = account_selector.render(conn)
    shell.sidebar_user_controls()
account, rules, trades, adjustments, rs, now = service.evaluate_now(conn, account_id=account_id)
cur = account.base_currency
dsb = rs.day_start_balance

st.title("📓 Journal des trades")

# ============================================================================
# 1. Ouvrir un trade
# ============================================================================
st.subheader("Ouvrir un trade")

if rs.locked:
    AO.render_stop(rs, account)
    st.error("🔒 Ouverture bloquée (mode strict) : une règle en blocage est atteinte. "
             "Clôture tes positions, puis attends le reset — ou repasse la règle en Alerte.")
else:
    AO.render_alerts(rs, sound=account.sound_enabled)

    default_unit = account.preferred_unit
    prefill = st.session_state.get("prefill", {})
    checklist_items = R.load_checklist(conn, account.id, only_enabled=True)

    with st.form("open_form", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        instrument = c1.text_input("Instrument", value=prefill.get("instrument", "EURUSD"))
        market = c2.selectbox("Marché", C.MARKETS,
                              index=C.MARKETS.index(prefill.get("market", "FOREX")))
        direction = c3.selectbox("Sens", C.DIRECTIONS,
                                 format_func=lambda d: C.DIRECTION_LABELS[d], help=C.HELP_SENS)

        c4, c5 = st.columns(2)
        unit = c4.radio("Unité de risque", [C.UNIT_PCT, C.UNIT_R],
                        index=0 if default_unit == C.UNIT_PCT else 1, horizontal=True)
        if unit == C.UNIT_PCT:
            risk_val = c5.number_input("Risque (% du capital)", min_value=0.0,
                                       value=float(prefill.get("risk_pct", 1.0)),
                                       step=0.25, format="%.2f", help=C.HELP_RISQUE)
            risk_pct = risk_val / 100.0
        else:
            risk_val = c5.number_input("Risque (en R)", min_value=0.0,
                                       value=float(prefill.get("risk_r", 1.0)),
                                       step=0.25, format="%.2f", help=C.HELP_RISQUE)
            risk_pct = risk_val * account.one_R_pct

        with st.expander("Détails optionnels (entrée / stop / taille) — pour le R réel"):
            d1, d2, d3, d4 = st.columns(4)
            entry_price = d1.number_input("Prix d'entrée", min_value=0.0, value=0.0, format="%.5f")
            stop_price = d2.number_input("Stop", min_value=0.0, value=0.0, format="%.5f")
            take_profit = d3.number_input("Take-profit", min_value=0.0, value=0.0, format="%.5f")
            size = d4.number_input("Taille (lots/actions)", min_value=0.0, value=0.0, format="%.4f")

        s1, s2 = st.columns(2)
        setup = s1.text_input("Setup", value=prefill.get("setup", ""),
                              placeholder="ex: Breakout H4, pullback MM50…")
        thesis = s2.text_input("Thèse — pourquoi maintenant ?", value="")

        emotion = st.radio("État émotionnel (optionnel, 1 clic)",
                           ["(aucun)"] + C.EMOTION_TAGS, horizontal=True)
        note = st.text_input("Note (optionnel)", value="")

        checklist_checked = {}
        if checklist_items:
            st.markdown("**✅ Checklist pré-trade** (rappel — recommandé, non obligatoire) :")
            for it in checklist_items:
                checklist_checked[it["id"]] = st.checkbox(
                    it["label"], key=f"chk_{account.id}_{it['id']}")

        risk_amount = dsb * risk_pct
        st.caption(f"➡️ Risque de ce trade : **{RM.format_money(risk_amount, cur)}** "
                   f"({risk_pct*100:.2f}% · {risk_pct/account.one_R_pct:.2f}R)")

        submitted = st.form_submit_button("Ouvrir le trade", type="primary")

    if submitted:
        checklist_ok = (all(checklist_checked.get(it["id"], False) for it in checklist_items)
                        if checklist_items else True)
        check = E.check_new_trade(account, rules, trades, adjustments, now, risk_amount)
        if check.blocking:
            # Mode strict : une règle passée en Blocage refuse le trade.
            st.error("⛔ Trade refusé (mode strict) — il viole une règle en blocage :")
            lines = []
            for rule_type, msg in check.blocking:
                label = C.RULE_LABELS.get(rule_type, rule_type)
                st.markdown(f"- **{label}** : {msg}")
                R.log_alert(conn, rule_type, C.LEVEL_BLOCK, now, context=msg,
                            account_id=account.id)
                lines.append(f"{label} : {msg}")
            AO.play_alert_sound("BLOCK")
            _push_notification("BLOCK", lines)
        else:
            # Mode conseil (défaut) : on logue toujours, on alerte fort si dépassement.
            tid = R.open_trade(
                conn, account, instrument.strip() or "?", market, direction,
                risk_pct=risk_pct, now=now,
                entry_price=entry_price or None, stop_price=stop_price or None,
                take_profit=take_profit or None, size=size or None,
                emotion_tag=None if emotion == "(aucun)" else emotion,
                note=note.strip() or None,
                setup=setup.strip() or None, thesis=thesis.strip() or None,
            )
            adv_lines = []
            for rule_type, msg in check.advisories:
                label = C.RULE_LABELS.get(rule_type, rule_type)
                R.log_alert(conn, rule_type, C.LEVEL_WARN, now, context=msg,
                            account_id=account.id)
                adv_lines.append(f"{label} : {msg}")
            st.session_state.pop("prefill", None)
            st.success(f"✅ Trade #{tid} logué ({RM.format_money(risk_amount, cur)}).")
            if adv_lines:
                st.warning("🔴 Ce trade franchit une limite : " + " ; ".join(adv_lines))
                AO.play_alert_sound("BLOCK")
                _push_notification("WARN", adv_lines)
            if not checklist_ok:
                st.info("Rappel : ta checklist n'était pas complète.")
            st.rerun()
            st.rerun()

st.divider()

# ============================================================================
# 2. Clôturer un trade
# ============================================================================
st.subheader("Clôturer un trade")
open_positions = [t for t in trades if t.status == C.STATUS_OPEN]
if not open_positions:
    st.info("Aucune position ouverte à clôturer.")
else:
    with st.form("close_form_journal", clear_on_submit=True):
        labels = {f"#{t.id} · {t.instrument} "
                  f"({C.DIRECTION_LABELS.get(t.direction, t.direction)}) — risque "
                  f"{RM.format_money(t.planned_risk_amount, cur)}": t.id
                  for t in open_positions}
        choice = st.selectbox("Position à clôturer", list(labels.keys()))
        pnl = st.number_input(f"P&L réalisé ({cur}) — négatif si perte",
                              value=0.0, step=100.0, format="%.2f")
        if st.form_submit_button("Clôturer", type="primary"):
            R.close_trade(conn, labels[choice], realized_pnl_amount=pnl, now=now)
            st.success(f"Position clôturée ({RM.format_money(pnl, cur)}).")
            st.rerun()

st.divider()

# ============================================================================
# 3. Historique + export CSV
# ============================================================================
st.subheader("Historique")
if not trades:
    st.info("Aucun trade enregistré pour l'instant.")
else:
    rows = []
    for t in trades:
        rows.append({
            "id": t.id, "instrument": t.instrument, "marché": t.market,
            "sens": C.DIRECTION_LABELS.get(t.direction, t.direction), "statut": t.status,
            "ouvert": t.opened_at.strftime("%Y-%m-%d %H:%M") if t.opened_at else "",
            "clôturé": t.closed_at.strftime("%Y-%m-%d %H:%M") if t.closed_at else "",
            "risque_%": round(t.planned_risk_pct * 100, 2),
            "risque_R": round(t.planned_risk_R, 2),
            "risque_montant": round(t.planned_risk_amount, 2),
            "pnl": round(t.realized_pnl_amount, 2) if t.realized_pnl_amount is not None else None,
            "R_réalisé": round(t.realized_R, 2) if t.realized_R is not None else None,
            "résultat": t.outcome or "",
            "émotion": t.emotion_tag or "",
            "note": t.note or "",
        })
    df = pd.DataFrame(rows)

    f1, f2 = st.columns(2)
    market_filter = f1.multiselect("Filtrer par marché", C.MARKETS)
    status_filter = f2.multiselect("Filtrer par statut",
                                   [C.STATUS_OPEN, C.STATUS_CLOSED, C.STATUS_CANCELLED])
    view = df.copy()
    if market_filter:
        view = view[view["marché"].isin(market_filter)]
    if status_filter:
        view = view[view["statut"].isin(status_filter)]

    st.dataframe(view, use_container_width=True, hide_index=True)
    st.download_button("⬇️ Exporter en CSV", data=df.to_csv(index=False).encode("utf-8"),
                       file_name="journal_trades.csv", mime="text/csv")
