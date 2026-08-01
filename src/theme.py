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
        "card": "#151B40",        # fond de carte / ligne de position
        "border": "#2A3566",      # filet
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
        "card": "#FFFFFF",
        "border": "#D5DAF0",
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


def brand_html(size: int = 34, title_rem: float = 1.5, subtitle: bool = True) -> str:
    """Logo radar + wordmark « Vigie » (theme-aware). Réutilisé par la barre
    latérale ET l'écran de connexion pour éviter toute divergence. Lignes sans
    indentation : un HTML indenté de 4+ espaces serait échappé par Streamlit."""
    p = pal()
    sub = ""
    if subtitle:
        sub = (f'<div style="font-family:ui-monospace,monospace;font-size:10.5px;'
               f'letter-spacing:.16em;text-transform:uppercase;color:{p["logo_sub"]};'
               f'margin:0 0 8px 2px;">L\'œil sur ton risque</div>')
    return (
        f'<div style="display:flex;align-items:center;gap:11px;margin:2px 0 2px;">'
        f'<svg width="{size}" height="{size}" viewBox="0 0 48 48" aria-hidden="true">'
        f'<circle cx="22" cy="24" r="18" fill="none" stroke="{p["logo_ring"]}" stroke-width="2"/>'
        f'<circle cx="22" cy="24" r="10" fill="none" stroke="{ACCENT}" stroke-width="2"/>'
        f'<line x1="4" y1="24" x2="40" y2="24" stroke="{p["logo_ring"]}" stroke-width="1.4" opacity="0.6"/>'
        f'<line x1="22" y1="6" x2="22" y2="42" stroke="{p["logo_ring"]}" stroke-width="1.4" opacity="0.6"/>'
        f'<circle cx="22" cy="24" r="2.6" fill="{ACCENT}"/>'
        f'<circle cx="31" cy="16" r="3.4" fill="#FF5D62"/>'
        f'</svg>'
        f'<span style="font-size:{title_rem}rem;font-weight:800;letter-spacing:-.01em;'
        f'color:{p["logo_text"]};">Vigie</span>'
        f'</div>{sub}'
    )
