"""Palette pour notre HTML custom (bannières, logo, jauges).

Les widgets natifs Streamlit basculent clair/sombre via `config.toml`
(`[theme.light]`/`[theme.dark]`). Notre HTML injecté, lui, ne connaît pas le
thème actif : ce module lit `st.context.theme.type` (runtime, respecte le
réglage système ET le toggle Settings) et renvoie les couleurs adaptées.

Hors contexte Streamlit (tests headless), on retombe sur le mode sombre.
"""

from __future__ import annotations

# Accents de marque / statut — lisibles sur clair ET sombre, identiques aux deux.
ACCENT = "#5B7CFA"
OK = "#2ecc71"
WARN = "#f39c12"
DANGER = "#e63946"

_PALETTES = {
    "dark": {
        "text": "#E7E9F5",
        "muted": "#9fb0b8",
        "muted_soft": "#c8d2d8",
        "track": "#2b2f3a",       # fond de barre de jauge
        "logo_ring": "#33407e",   # anneaux/croix du radar
        "logo_text": "#E7E9F5",
        "logo_sub": "#8AA1A9",
        "btn_bg": "#1a1d29",
        "btn_border": "#3a3f4b",
        "btn_text": "#c8cdd8",
        "warn_list": "#e8c98a",
        "danger_list": "#f3d5d8",
    },
    "light": {
        "text": "#1A1E3C",
        "muted": "#5b6472",
        "muted_soft": "#3a4250",
        "track": "#DDE1F0",
        "logo_ring": "#C3C9E8",
        "logo_text": "#1A1E3C",
        "logo_sub": "#6B7490",
        "btn_bg": "#EDEFF9",
        "btn_border": "#C7CCE6",
        "btn_text": "#3a4250",
        "warn_list": "#7a5b12",
        "danger_list": "#8a2b33",
    },
}


def active_mode() -> str:
    """Renvoie 'light' ou 'dark' selon le thème actif (défaut 'dark')."""
    try:
        import streamlit as st
        typ = getattr(getattr(st, "context", None), "theme", None)
        typ = getattr(typ, "type", None)
        return typ if typ in ("light", "dark") else "dark"
    except Exception:
        return "dark"


def pal() -> dict:
    """Palette de l'HTML custom pour le mode actif."""
    return _PALETTES[active_mode()]
