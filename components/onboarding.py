"""Assistant de premier lancement (onboarding) — configuration en 1 minute."""

from __future__ import annotations

import streamlit as st

from src import constants as C
from src import repository as R

_TIMEZONES = ["Africa/Porto-Novo", "Africa/Abidjan", "Africa/Lagos", "Africa/Dakar",
              "UTC", "Europe/Paris", "Europe/London", "America/New_York"]

_PROFILE_HELP = {
    "Prudent": "Perte max 2 %/jour · 0,5 %/trade · pause après 2 pertes.",
    "Équilibré": "Perte max 3 %/jour · 1 %/trade · pause après 3 pertes.",
    "Agressif": "Perte max 5 %/jour · 2 %/trade · pause après 4 pertes.",
}


def render(conn, account) -> None:
    """Affiche l'assistant. Enregistre et marque le compte comme configuré au submit."""
    st.title("👋 Bienvenue sur Vigie")
    st.caption("Configurons ton garde-fou en une minute. Tu pourras tout ajuster ensuite.")

    tz_index = _TIMEZONES.index(account.timezone) if account.timezone in _TIMEZONES else 0

    with st.form("onboarding_form"):
        c1, c2, c3 = st.columns(3)
        capital = c1.number_input("Ton capital", min_value=0.0,
                                  value=float(account.initial_balance), step=10_000.0)
        ccy = c2.text_input("Devise", value=account.base_currency)
        tz = c3.selectbox("Fuseau horaire", _TIMEZONES, index=tz_index)

        profile = st.radio("Choisis ton profil de risque",
                           list(C.RISK_PROFILES.keys()) + ["Personnalisé"],
                           index=1, horizontal=True)
        for name, desc in _PROFILE_HELP.items():
            st.caption(f"**{name}** — {desc}")
        st.caption("**Personnalisé** — fixe toi-même tes deux limites clés ci-dessous.")
        pc1, pc2 = st.columns(2)
        custom_daily = pc1.number_input("Perso · perte max / jour (%)", min_value=0.0,
                                        value=3.0, step=0.5)
        custom_trade = pc2.number_input("Perso · risque max / trade (%)", min_value=0.0,
                                        value=1.0, step=0.25)

        col_go, col_skip = st.columns([2, 1])
        go = col_go.form_submit_button("C'est parti 🚀", type="primary")
        skip = col_skip.form_submit_button("Passer")

    if go:
        account.initial_balance = capital
        account.base_currency = ccy.strip() or "XOF"
        account.timezone = tz
        R.save_account(conn, account)
        if profile == "Personnalisé":
            R.apply_custom_risk(conn, account.id, custom_daily / 100, custom_trade / 100)
        else:
            R.apply_risk_profile(conn, account.id, profile)
        R.mark_onboarded(conn, account.id)
        st.rerun()
    elif skip:
        R.mark_onboarded(conn, account.id)
        st.rerun()
