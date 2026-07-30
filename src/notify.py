"""Notifications externes : email (SMTP) + push (ntfy.sh).

Découplé de Streamlit pour rester testable : les fonctions prennent des dicts de
config. `read_secrets()` lit `.streamlit/secrets.toml` quand l'app tourne.
"""

from __future__ import annotations

import smtplib
from email.message import EmailMessage
from typing import Optional

import requests


def send_email(cfg: dict, subject: str, body: str) -> bool:
    """Envoie un email si `cfg['enabled']`. Renvoie True si tenté avec succès."""
    if not cfg or not cfg.get("enabled"):
        return False
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = cfg["sender"]
    msg["To"] = cfg.get("recipient", cfg["sender"])
    msg.set_content(body)
    with smtplib.SMTP(cfg["smtp_host"], int(cfg["smtp_port"]), timeout=15) as s:
        s.starttls()
        s.login(cfg["sender"], cfg["app_password"])
        s.send_message(msg)
    return True


def send_ntfy(cfg: dict, subject: str, body: str) -> bool:
    """Envoie un push ntfy si `cfg['enabled']`."""
    if not cfg or not cfg.get("enabled"):
        return False
    server = str(cfg.get("server", "https://ntfy.sh")).rstrip("/")
    url = f"{server}/{cfg['topic']}"
    requests.post(
        url, data=body.encode("utf-8"),
        headers={"Title": subject, "Priority": "urgent", "Tags": "rotating_light"},
        timeout=10,
    )
    return True


def notify(subject: str, body: str,
           email_cfg: Optional[dict] = None, ntfy_cfg: Optional[dict] = None) -> dict:
    """Tente email + ntfy ; ne lève jamais (les erreurs sont capturées et renvoyées)."""
    results: dict = {}
    if email_cfg is not None:
        try:
            results["email"] = send_email(email_cfg, subject, body)
        except Exception as e:  # réseau/SMTP : on n'interrompt pas le trader
            results["email"] = f"error: {e}"
    if ntfy_cfg is not None:
        try:
            results["ntfy"] = send_ntfy(ntfy_cfg, subject, body)
        except Exception as e:
            results["ntfy"] = f"error: {e}"
    return results


def read_secrets() -> tuple[Optional[dict], Optional[dict]]:
    """Lit les sections [email] et [ntfy] de secrets.toml (via st.secrets)."""
    try:
        import streamlit as st
        email_cfg = dict(st.secrets["email"]) if "email" in st.secrets else None
        ntfy_cfg = dict(st.secrets["ntfy"]) if "ntfy" in st.secrets else None
        return email_cfg, ntfy_cfg
    except Exception:
        return None, None


def build_message(kind: str, lines: list[str], when_local: str = "") -> tuple[str, str]:
    """Construit (sujet, corps) pour une alerte de risque."""
    icon = "🛑" if kind == "BLOCK" else "⚠️"
    subject = f"{icon} Vigie — {'Blocage' if kind == 'BLOCK' else 'Alerte risque'}"
    body = "\n".join([subject, ""] + [f"• {l}" for l in lines])
    if when_local:
        body += f"\n\nProchain reset : {when_local}"
    return subject, body
