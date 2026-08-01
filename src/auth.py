"""Authentification multi-utilisateur (chantier cloud).

Mode **local** (défaut) : aucune auth, l'app utilise tous les comptes (propriétaire 1).
Mode **cloud** : activé par la variable d'env `RISK_REQUIRE_AUTH=1` ou par le secret
`[auth] require = true`. Chaque utilisateur ne voit que ses propres comptes.

Mots de passe : PBKDF2-HMAC-SHA256 avec sel (stdlib, aucun secret stocké en clair).
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets as _secrets
import sqlite3
from datetime import datetime
from typing import Optional

from . import db as DB
from .time_utils import UTC

_ITERATIONS = 200_000


# --- Hachage (pur, testable) -------------------------------------------------
def hash_password(password: str, salt: Optional[str] = None) -> str:
    salt = salt or _secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), _ITERATIONS)
    return f"{salt}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        salt, _ = stored.split("$", 1)
    except ValueError:
        return False
    return hmac.compare_digest(hash_password(password, salt), stored)


# --- Utilisateurs (DB) -------------------------------------------------------
def create_user(conn: sqlite3.Connection, username: str, password: str) -> int:
    cur = conn.execute(
        "INSERT INTO users (username, password_hash, created_at) VALUES (?, ?, ?)",
        (username.strip().lower(), hash_password(password),
         datetime.now(tz=UTC).isoformat()),
    )
    uid = DB.last_insert_id(conn, cur)
    conn.commit()
    return uid


def user_exists(conn: sqlite3.Connection, username: str) -> bool:
    return conn.execute("SELECT 1 FROM users WHERE username = ?",
                        (username.strip().lower(),)).fetchone() is not None


def verify_credentials(conn: sqlite3.Connection, username: str,
                       password: str) -> Optional[int]:
    r = conn.execute("SELECT id, password_hash FROM users WHERE username = ?",
                     (username.strip().lower(),)).fetchone()
    if r and verify_password(password, r["password_hash"]):
        return r["id"]
    return None


# --- Mode & gate -------------------------------------------------------------
def is_auth_required() -> bool:
    if os.environ.get("RISK_REQUIRE_AUTH", "").lower() in ("1", "true", "yes"):
        return True
    try:
        import streamlit as st
        return bool(st.secrets.get("auth", {}).get("require", False))
    except Exception:
        return False


def gate(conn: sqlite3.Connection) -> Optional[int]:
    """Renvoie l'user_id courant, ou None en mode local. Bloque la page si non connecté."""
    import streamlit as st
    if not is_auth_required():
        return None
    uid = st.session_state.get("user_id")
    if uid:
        return uid
    _render_login(conn)
    st.stop()


def logout() -> None:
    import streamlit as st
    st.session_state.pop("user_id", None)
    st.session_state.pop("account_id", None)


def is_admin(conn) -> bool:
    """Admin = propriétaire en local, OU 1er utilisateur (id 1), OU listé dans les secrets."""
    import streamlit as st
    if not is_auth_required():
        return True
    uid = st.session_state.get("user_id")
    if not uid:
        return False
    if uid == 1:
        return True
    try:
        admins = [u.lower() for u in st.secrets.get("admin", {}).get("usernames", [])]
        row = conn.execute("SELECT username FROM users WHERE id = ?", (uid,)).fetchone()
        return bool(row) and row["username"] in admins
    except Exception:
        return False


def _ensure_account(conn: sqlite3.Connection, user_id: int, username: str) -> None:
    from . import repository as R
    if not R.list_accounts(conn, user_id=user_id):
        R.create_account(conn, name=f"Compte de {username}", base_currency="XOF",
                         initial_balance=1_000_000, timezone="Africa/Porto-Novo",
                         user_id=user_id)


def _render_login(conn: sqlite3.Connection) -> None:
    import streamlit as st
    from . import theme as TH
    st.markdown(TH.brand_html(size=46, title_rem=2.0, subtitle=False),
                unsafe_allow_html=True)
    st.caption("L'œil sur ton risque — surveille tes limites, garde la main.")
    tab_login, tab_register = st.tabs(["Connexion", "Créer un compte"])

    with tab_login:
        with st.form("login_form"):
            u = st.text_input("Nom d'utilisateur")
            p = st.text_input("Mot de passe", type="password")
            if st.form_submit_button("Se connecter", type="primary"):
                uid = verify_credentials(conn, u, p)
                if uid:
                    st.session_state["user_id"] = uid
                    _ensure_account(conn, uid, u)
                    st.rerun()
                else:
                    st.error("Identifiants invalides.")

    with tab_register:
        with st.form("register_form"):
            u = st.text_input("Nom d'utilisateur", key="reg_u")
            p = st.text_input("Mot de passe (min. 6 caractères)", type="password", key="reg_p")
            if st.form_submit_button("Créer le compte"):
                if user_exists(conn, u):
                    st.error("Ce nom d'utilisateur existe déjà.")
                elif len(p) < 6:
                    st.error("Mot de passe trop court (minimum 6 caractères).")
                elif not u.strip():
                    st.error("Nom d'utilisateur requis.")
                else:
                    uid = create_user(conn, u, p)
                    st.session_state["user_id"] = uid
                    _ensure_account(conn, uid, u.strip())
                    st.rerun()
