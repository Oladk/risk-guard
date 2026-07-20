# Déploiement (cloud & mobile)

L'app fonctionne en **deux modes** :

- **Local** (défaut) : aucune authentification, données dans `data/risk.db`.
- **Cloud / multi-utilisateur** : authentification activée, chaque utilisateur ne voit
  que ses comptes. Activation via la variable d'env `RISK_REQUIRE_AUTH=1` **ou** le
  secret `[auth] require = true`.

---

## 🆓 Déploiement 100 % gratuit (recommandé)

Objectif : une URL accessible depuis ton téléphone, **sans carte bancaire**, avec des
données **qui persistent**. Combo : **Streamlit Community Cloud** (héberge l'app) +
**Neon** (Postgres gratuit).

### 1. Mettre le code sur GitHub (repo public)
```bash
git init
git add .
git commit -m "Risk Guard"
git branch -M main
git remote add origin https://github.com/<toi>/risk-guard.git
git push -u origin main
```
> Le `.gitignore` protège déjà `data/` et `.streamlit/secrets.toml` : rien de sensible n'est poussé.

### 2. Créer une base Neon gratuite (persistante)
1. Va sur **https://neon.tech** → *Sign up* (avec GitHub, sans carte).
2. *Create project* → copie la **connection string** (format `postgresql://…?sslmode=require`).

### 3. Déployer sur Streamlit Community Cloud
1. Va sur **https://share.streamlit.io** → *New app* → connecte ton GitHub.
2. Repo = ton dépôt, branche `main`, **Main file path = `app.py`**.
3. (Advanced) Python **3.12**. → *Deploy*.

### 4. Coller les secrets (Settings → Secrets)
```toml
DATABASE_URL = "postgresql://user:pass@ep-xxx.neon.tech/db?sslmode=require"

[auth]
require = true
```
- `DATABASE_URL` → tes données vivent dans Neon (persistant).
- `[auth] require = true` → écran de connexion (URL publique = protège-la).
- (Optionnel) ajoute `[email]` / `[ntfy]` pour les notifications.

### 5. Première utilisation
Ouvre l'URL sur ton téléphone → **crée ton compte** → l'assistant d'onboarding démarre →
« Ajouter à l'écran d'accueil » (PWA).

> ⚠️ **Sans `DATABASE_URL`**, Streamlit Cloud fonctionne quand même mais en **SQLite
> éphémère** : tes trades sont **effacés à chaque redéploiement**. Pour un journal
> sérieux, mets toujours Neon.

> 💡 Alternative d'hébergement gratuite : **Hugging Face Spaces** (type Streamlit) +
> Neon, même principe (secrets dans l'onglet *Settings* du Space).

---

## Option A — Docker (self-hébergement)

```bash
docker build -t risk-guard .
docker run -p 8501:8501 -v risk_data:/app/data risk-guard
```

- Le volume `risk_data` **persiste** la base SQLite (sinon elle est éphémère).
- `RISK_REQUIRE_AUTH=1` est activé par défaut dans l'image → écran de connexion.
- Notifications : monter aussi un `secrets.toml` (voir plus bas).

## Option B — Streamlit Community Cloud

1. Pousser le repo sur GitHub.
2. Créer une app sur https://share.streamlit.io en pointant sur `app.py`.
3. Dans **Settings → Secrets**, coller le contenu de `secrets.toml` (dont `[auth] require = true`).
4. ⚠️ Le stockage y est **éphémère** : la base SQLite est réinitialisée à chaque
   redéploiement. Pour un usage sérieux multi-utilisateur, prévoir une base persistante
   (volume, ou migration vers Postgres — voir Limites).

## Secrets (notifications + auth)

Copier `.streamlit/secrets.toml.example` → `.streamlit/secrets.toml` et remplir. En
conteneur : `-v $(pwd)/.streamlit/secrets.toml:/app/.streamlit/secrets.toml`.

---

## Mobile

L'interface est **responsive** (mise en page adaptée < 640 px, cibles tactiles ≥ 44 px).
Pour un accès type application : ouvrir l'URL dans le navigateur mobile puis
« Ajouter à l'écran d'accueil » (PWA légère). Une app native n'est pas nécessaire pour le V2.

---

## Base de données : SQLite ou Postgres

Par défaut, l'app utilise **SQLite** (`data/risk.db`). Pour une charge multi-utilisateur,
définis `DATABASE_URL` vers un **Postgres** :

```bash
pip install "psycopg[binary]"          # ou : pip install -e ".[postgres]"
export DATABASE_URL="postgresql://user:pass@host:5432/riskguard"
streamlit run app.py
```

La couche connexion est **backend-agnostique** : mêmes requêtes, le dialecte (SERIAL,
placeholders, récupération d'id, versioning du schéma) est adapté automatiquement. Un
Postgres neuf crée directement le schéma courant (les migrations SQLite historiques ne
s'appliquent pas). En conteneur, passe simplement `-e DATABASE_URL=...`.

> ⚠️ Le chemin Postgres est **code-complet et couvert par des tests unitaires**
> (adaptation DDL, placeholders), mais valide-le sur **une instance Postgres réelle**
> avant production (non exécuté dans l'environnement de build).

## Sécurité

- Mots de passe : **PBKDF2-HMAC-SHA256 salé** (aucun mot de passe en clair).
- Servir **en HTTPS** derrière un reverse proxy (Caddy/Nginx) ou via la plateforme cloud.
- Isolation des données : tout est rattaché à `accounts.user_id` ; un utilisateur ne
  liste que ses comptes.

## Limites connues

- **SQLite** convient à un usage mono-conteneur et faible concurrence ; pour une vraie
  charge multi-utilisateur, utilise **Postgres** (`DATABASE_URL`, voir plus haut).
- La **sync MT5** reste **locale** (terminal Windows) : non disponible sur un serveur
  cloud Linux. Le cloud sert le journal manuel + l'analytique + le coaching.
