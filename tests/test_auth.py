"""Tests d'authentification multi-utilisateur (chantier cloud)."""

from src import auth
from src import db as DB
from src import repository as R


def fresh():
    conn = DB.get_conn(":memory:")
    DB.init_db(conn)
    return conn


def test_hash_and_verify():
    h = auth.hash_password("secret123")
    assert "$" in h
    assert auth.verify_password("secret123", h) is True
    assert auth.verify_password("mauvais", h) is False


def test_hash_uses_random_salt():
    assert auth.hash_password("x") != auth.hash_password("x")


def test_create_and_verify_user_is_case_insensitive():
    conn = fresh()
    uid = auth.create_user(conn, "Alice", "monpass")
    assert auth.user_exists(conn, "alice")
    assert auth.verify_credentials(conn, "ALICE", "monpass") == uid
    assert auth.verify_credentials(conn, "alice", "faux") is None
    assert auth.verify_credentials(conn, "inconnu", "x") is None


def test_user_account_isolation():
    conn = fresh()
    u1 = auth.create_user(conn, "alice", "p1")
    u2 = auth.create_user(conn, "bob", "p2")
    a1 = R.create_account(conn, "A", "USD", 1000, "UTC", user_id=u1)
    a2 = R.create_account(conn, "B", "XOF", 2000, "UTC", user_id=u2)

    u1_ids = {a.id for a in R.list_accounts(conn, user_id=u1)}
    u2_ids = {a.id for a in R.list_accounts(conn, user_id=u2)}
    assert a1 in u1_ids and a2 not in u1_ids
    assert a2 in u2_ids and a1 not in u2_ids

    # Sans filtre (mode local) : tout est visible.
    all_ids = {a.id for a in R.list_accounts(conn)}
    assert {a1, a2} <= all_ids


def test_auth_not_required_by_default():
    assert auth.is_auth_required() is False


def test_is_admin_true_in_local_mode(monkeypatch):
    """En local (pas d'auth), le propriétaire est admin -> la page Admin apparaît.

    Court-circuite avant tout accès à st.session_state : testable hors contexte
    Streamlit. C'est ce que teste le routeur pour afficher/masquer l'onglet Admin.
    """
    monkeypatch.delenv("RISK_REQUIRE_AUTH", raising=False)
    conn = fresh()
    assert auth.is_admin(conn) is True
