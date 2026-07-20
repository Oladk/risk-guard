"""Sélecteur de compte partagé (persisté dans st.session_state entre les pages)."""

from __future__ import annotations

import streamlit as st

from src import repository as R


def render(conn) -> int:
    """Affiche le sélecteur de compte et renvoie l'account_id courant.

    En mode multi-utilisateur, ne liste que les comptes de l'utilisateur connecté."""
    user_id = st.session_state.get("user_id")
    accounts = R.list_accounts(conn, user_id=user_id)
    labels = {f"{a.name} · {a.base_currency}": a.id for a in accounts}
    ids = list(labels.values())
    if not ids:
        st.warning("Aucun compte. Crée-en un dans « Règles & compte ».")
        return 0

    if st.session_state.get("account_id") not in ids:
        st.session_state["account_id"] = ids[0]

    keys = list(labels.keys())
    current_index = ids.index(st.session_state["account_id"])
    choice = st.selectbox("Compte actif", keys, index=current_index,
                          key="account_selector_box")
    st.session_state["account_id"] = labels[choice]
    return st.session_state["account_id"]
