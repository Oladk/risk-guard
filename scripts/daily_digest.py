"""Digest quotidien (optionnel) — à lancer via le Planificateur de tâches Windows.

Lit la base, construit un récap de la journée de trading et l'envoie par email/ntfy.
C'est le seul composant « hors session Streamlit ». Les secrets sont lus directement
depuis `.streamlit/secrets.toml` avec `tomllib` (pas besoin d'un serveur Streamlit).

Exemple de tâche planifiée (tous les jours à 22h00) :
    schtasks /Create /SC DAILY /TN "RiskGuardDigest" /TR ^
      "\"C:\\Python314\\python.exe\" \"<chemin>\\scripts\\daily_digest.py\"" /ST 22:00
"""

from __future__ import annotations

import pathlib
import sys
import tomllib
from datetime import datetime

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src import notify as N  # noqa: E402

_NO_DECIMALS = {"XOF", "XAF", "JPY", "KRW", "CLP"}


def _money(amount: float, currency: str) -> str:
    fmt = f"{amount:,.0f}" if currency in _NO_DECIMALS else f"{amount:,.2f}"
    return f"{fmt} {currency}".replace(",", " ")


def _load_secrets() -> tuple[dict | None, dict | None]:
    path = ROOT / ".streamlit" / "secrets.toml"
    if not path.exists():
        return None, None
    with open(path, "rb") as f:
        data = tomllib.load(f)
    return data.get("email"), data.get("ntfy")


def build_digest(account, rs, now: datetime) -> tuple[str, str]:
    cur = account.base_currency
    lines = [
        f"Solde de début de journée : {_money(rs.day_start_balance, cur)}",
        f"P&L réalisé du jour : {_money(rs.realized_pnl_today, cur)}",
        f"Risque encore ouvert : {_money(rs.open_risk, cur)}",
        f"Statut : {rs.global_level}" + (" — STOP actif" if rs.locked else ""),
    ]
    subject = "📊 Risk Guard — récap du jour"
    body = "\n".join([subject, ""] + [f"• {l}" for l in lines])
    return subject, body


def main() -> int:
    from src import service
    from src import time_utils as T

    conn = service.connect()
    account, rules, trades, adjustments, rs, now = service.evaluate_now(conn, T.now_utc())
    subject, body = build_digest(account, rs, now)

    email_cfg, ntfy_cfg = _load_secrets()
    results = N.notify(subject, body, email_cfg, ntfy_cfg)
    print(body)
    print("Envois :", results)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
