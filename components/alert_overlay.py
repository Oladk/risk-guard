"""Alerte forte : hero STOP rouge, bordure pulsante plein écran, bannière orange, son."""

from __future__ import annotations

import streamlit as st
import streamlit.components.v1 as components

from src import risk_engine as E
from .risk_meters import format_local_time

# Bordure rouge pulsante autour de tout l'écran (pointer-events:none pour ne PAS
# bloquer les clics : la clôture d'une position doit rester possible en mode STOP).
_PULSE_CSS = """
<style>
@keyframes rg-pulse {
  0%   { box-shadow: inset 0 0 0px 0px rgba(230,57,70,0.0); }
  50%  { box-shadow: inset 0 0 60px 14px rgba(230,57,70,0.85); }
  100% { box-shadow: inset 0 0 0px 0px rgba(230,57,70,0.0); }
}
#rg-stop-border {
  position: fixed; inset: 0; z-index: 9998; pointer-events: none;
  animation: rg-pulse 1.1s ease-in-out infinite;
}
</style>
<div id="rg-stop-border"></div>
"""


def render_stop(risk_state: E.RiskState, account: E.Account) -> None:
    """Hero STOP rouge + bordure pulsante. Affiché quand une règle verrouillante bloque."""
    st.markdown(_PULSE_CSS, unsafe_allow_html=True)

    reasons = "".join(
        f"<li style='margin:4px 0;'>{s.label} — {s.message}</li>"
        for s in risk_state.blocking_rules()
    )
    unlock = format_local_time(risk_state.unlock_at, account.timezone)

    st.markdown(
        f"""
        <div style="background:linear-gradient(135deg,#7a1420,#e63946);
                    border-radius:14px;padding:26px 30px;margin-bottom:18px;
                    border:2px solid #ff5c6c;box-shadow:0 0 30px rgba(230,57,70,0.5);">
          <div style="font-size:2.1rem;font-weight:800;color:#fff;letter-spacing:1px;">
            🛑 STOP — limite de risque atteinte
          </div>
          <div style="color:#ffe3e6;margin-top:6px;font-size:1.02rem;">
            Aucune nouvelle position autorisée jusqu'au prochain reset
            (<b>{unlock}</b>). La clôture de tes positions ouvertes reste possible.
          </div>
          <ul style="color:#fff;margin-top:12px;font-size:0.98rem;">{reasons}</ul>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if account.sound_enabled:
        play_alert_sound("BLOCK")


def render_warning(risk_state: E.RiskState) -> None:
    """Bannière orange quand une ou plusieurs règles approchent la limite (≥80%)."""
    warns = risk_state.warning_rules()
    if not warns:
        return
    items = "".join(f"<li style='margin:2px 0;'>{s.label} — {s.message}</li>" for s in warns)
    st.markdown(
        f"""
        <div style="background:rgba(243,156,18,0.14);border-left:5px solid #f39c12;
                    border-radius:8px;padding:14px 18px;margin-bottom:16px;">
          <div style="color:#f39c12;font-weight:700;font-size:1.05rem;">
            ⚠️ Zone d'avertissement — tu approches une limite
          </div>
          <ul style="color:#e8c98a;margin:8px 0 0 0;">{items}</ul>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_alerts(risk_state: E.RiskState, sound: bool = True) -> None:
    """Alertes en mode CONSEIL (sans blocage) : rouge = limite atteinte, orange = approche.

    C'est la sortie par défaut de l'outil : il prévient fort, mais laisse le trader décider."""
    reached = risk_state.blocking_rules()   # level == BLOCK (limite atteinte à 100 %)
    if reached:
        items = "".join(f"<li style='margin:3px 0;'>{s.label} — {s.message}</li>"
                        for s in reached)
        st.markdown(
            f"""
            <div style="background:rgba(230,57,70,0.14);border-left:6px solid #e63946;
                        border-radius:8px;padding:16px 20px;margin-bottom:14px;">
              <div style="color:#e63946;font-weight:800;font-size:1.12rem;">
                🔴 Limite(s) atteinte(s) — à toi de décider
              </div>
              <div style="color:#f0c3c7;font-size:0.9rem;margin-top:2px;">
                L'outil t'alerte, il ne bloque pas. Reprends la main sur ton risque.
              </div>
              <ul style="color:#f3d5d8;margin:8px 0 0 0;">{items}</ul>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if sound:
            play_alert_sound("BLOCK")
    render_warning(risk_state)


def play_alert_sound(level: str) -> None:
    """Émet un bip via WebAudio. L'autoplay peut être bloqué tant qu'aucune
    interaction utilisateur n'a eu lieu → le bouton « activer le son » de la
    barre latérale débloque le contexte audio."""
    freq = 880 if level == "BLOCK" else 660
    beeps = 3 if level == "BLOCK" else 1
    components.html(
        f"""
        <script>
        (function() {{
          try {{
            const Ctx = window.AudioContext || window.webkitAudioContext;
            const ctx = new Ctx();
            for (let i = 0; i < {beeps}; i++) {{
              const o = ctx.createOscillator();
              const g = ctx.createGain();
              o.connect(g); g.connect(ctx.destination);
              o.type = 'square';
              o.frequency.value = {freq};
              const t = ctx.currentTime + i * 0.35;
              g.gain.setValueAtTime(0.001, t);
              g.gain.exponentialRampToValueAtTime(0.25, t + 0.02);
              g.gain.exponentialRampToValueAtTime(0.001, t + 0.30);
              o.start(t); o.stop(t + 0.32);
            }}
          }} catch (e) {{ /* audio bloqué par le navigateur */ }}
        }})();
        </script>
        """,
        height=0,
    )


def enable_sound_button() -> None:
    """Bouton discret qui « débloque » l'audio du navigateur via un geste utilisateur."""
    components.html(
        """
        <button onclick="(function(){try{const C=window.AudioContext||window.webkitAudioContext;
          const c=new C();const o=c.createOscillator();const g=c.createGain();
          o.connect(g);g.connect(c.destination);g.gain.value=0.0001;o.start();o.stop(c.currentTime+0.05);}catch(e){}})()"
          style="width:100%;padding:8px;border-radius:8px;border:1px solid #3a3f4b;
                 background:#1a1d29;color:#c8cdd8;cursor:pointer;font-size:0.85rem;">
          🔊 Activer le son des alertes
        </button>
        """,
        height=44,
    )
