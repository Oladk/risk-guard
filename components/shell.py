"""Amorçage commun des pages : CSS responsive (mobile) + gate d'authentification."""

from __future__ import annotations

import streamlit as st

from src import auth
from . import pwa

_MOBILE_CSS = """
<style>
@media (max-width: 640px) {
  .block-container { padding: 0.6rem 0.7rem !important; }
  h1 { font-size: 1.5rem !important; }
  h2 { font-size: 1.2rem !important; }
  [data-testid="stMetricValue"] { font-size: 1.05rem !important; }
  [data-testid="stMetricLabel"] { font-size: 0.75rem !important; }
  .stButton button, .stDownloadButton button, .stFormSubmitButton button {
    min-height: 44px;
  }
}
</style>
"""


def start(conn):
    """CSS mobile + PWA + gate d'auth. Renvoie l'user_id (ou None en mode local)."""
    st.markdown(_MOBILE_CSS, unsafe_allow_html=True)
    pwa.inject()
    return auth.gate(conn)


def sidebar_user_controls() -> None:
    """Bouton de déconnexion en mode multi-utilisateur."""
    if st.session_state.get("user_id"):
        if st.button("🚪 Se déconnecter", use_container_width=True):
            auth.logout()
            st.rerun()
