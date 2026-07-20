# ROADMAP V2 — De « journal discipliné » à « risk desk personnel intelligent »

Objectif : dépasser le MVP en attaquant les deux failles qui plafonnent tout journal —
**(1) les données ne rentrent pas** (friction de saisie), **(2) les analyses ne
changent pas le comportement**. Trois chantiers retenus, séquencés par dépendances.

## Pourquoi cet ordre (dépendances)

```
A. Quick wins (fondations data-model)  ─┬─►  B. Sync MT5 (données réelles)  ─►  C. Intelligence comportementale
   multi-comptes, FX, corrélation,      │        (un compte synchronisé EST         (a besoin de données fiables
   checklist, log inviolable            │         un compte ; trades en USD ;         et abondantes pour être utile)
                                         │         source de vérité = broker)
                                         └─►  C peut démarrer en partie sur données manuelles
```

A débloque B **et** C (le modèle de données actuel est mono-compte, mono-devise, log
éditable — trois hypothèses que B et C cassent). On fait donc **A d'abord**, puis B,
puis C. Estimation solo réaliste : **A ≈ 2–3 sem · B ≈ 2 sem · C ≈ 2–3 sem** (~6–8 sem).

---

## TRACK A — Quick wins & fondations (à faire en premier)

### A1. Multi-comptes *(le refactor structurant)*
- **Quoi** : forex et BRVM séparés, chacun son capital, ses règles, son journal, son fuseau. Sélecteur de compte global.
- **Data model** : nouvelle table `accounts` (l'actuelle `account` mono-ligne devient multi-lignes) ; ajouter `account_id` (FK) à `trades`, `risk_rules`, `balance_adjustments`, `alerts_log`. **Migration** dans [`src/db.py`](src/db.py) (versionnage `PRAGMA user_version`, backfill `account_id=1`).
- **Code** : [`src/service.py`](src/service.py) prend un `account_id` ; [`src/repository.py`](src/repository.py) filtre par compte ; sélecteur dans la sidebar de [`app.py`](app.py) (via `st.session_state`).
- **Réutilise** : tout `risk_engine` reste inchangé (il opère déjà sur un instantané) — on lui passe juste les trades du compte courant.

### A2. FX multi-devises correct
- **Quoi** : compte en XOF tradant des paires en USD → convertir risque et P&L dans la devise du compte.
- **Code** : nouveau [`src/fx.py`](src/fx.py) — table de taux (manuels + fetch optionnel via `exchangerate.host` / MT5), `convert(amount, from_ccy, to_ccy)`. Brancher dans [`src/sizing.py`](src/sizing.py) (retire l'hypothèse « cotation = compte ») et dans la conversion du P&L à la clôture.
- **Tests** : conversions croisées, override manuel prioritaire, cache.

### A3. Exposition avec corrélation
- **Quoi** : remplacer la somme simple par un **risque effectif** (EUR/USD + GBP/USD long ≈ pas 2× le risque).
- **Code** : [`src/correlation.py`](src/correlation.py) — matrice de corrélation depuis les rendements (données via MT5 `copy_rates` ou `yfinance`, cache quotidien). `effective_open_risk(trades, corr) = sqrt(wᵀ Σ w)` (risque « portefeuille »). Ajouter à `risk_engine.evaluate` une exposition effective **à côté** de la somme simple (garder les deux, la simple reste le garde-fou dur).
- **Réutilise** : `open_risk_amount` de [`src/risk_engine.py`](src/risk_engine.py) comme fallback.

### A4. Checklist / plan pré-trade *(quick win comportemental + capture de données)*
- **Quoi** : avant chaque ouverture, un mini-plan obligatoire configurable (setup, biais, « pourquoi maintenant ? », capture d'écran optionnelle). Gate dans le flux d'ouverture.
- **Code** : table `checklist_items` (config) + champs `setup`, `thesis`, `screenshot_path` sur `trades` ; gate dans [`pages/1_Journal.py`](pages/1_Journal.py). Bonus : ces champs nourrissent l'analytics par setup (Track C).

### A5. Journal inviolable + correction propre
- **Quoi** : empêcher la ré-édition rétroactive « pour se mentir ». Corrections tracées, jamais silencieuses.
- **Code** : table `trade_events` append-only (OPEN/CLOSE/EDIT/CANCEL avec timestamp serveur) ; l'état du trade est **dérivé** des events. `alerts_log` déjà append-only sert de modèle. Export audit.

**Livrable A** : app multi-comptes, devises justes, exposition corrélée, discipline pré-trade, log fiable — la fondation propre pour B et C.

---

## TRACK B — Sync broker MT5 (lecture) *(le grand pari)*

### B1. Connexion & import (lecture seule)
- **Quoi** : import automatique des **positions ouvertes** et **deals clôturés** MT5 → le moteur devient *live*, plus de saisie manuelle (forex).
- **Techno — deux options, on commence local** :
  - **`MetaTrader5` (pip)** — Windows, se connecte au **terminal MT5 local** (`positions_get()`, `history_deals_get()`, `copy_rates()`). Zéro cloud, idéal pour ta machine. **→ choix de départ.**
  - **MetaApi (cloud)** — multiplateforme, pas besoin de terminal, prêt pour un futur déploiement cloud. **→ V2.5.**
- **Code** : [`src/brokers/mt5.py`](src/brokers/mt5.py) (adapter derrière une interface `BrokerConnector`), [`src/brokers/sync.py`](src/brokers/sync.py) (upsert + réconciliation).
- **Mapping** : deal MT5 → notre `Trade` ; `planned_risk_amount` dérivé de la **distance au SL** × volume × valeur du point (via `symbol_info`) ; `emotion_tag`/`setup` restent saisis à la main (l'humain, pas le broker).

### B2. Réconciliation & source de vérité
- Compte marqué `MT5` : le broker est **source de vérité** (les positions/deals écrasent). Compte `MANUAL` : inchangé.
- Un poller léger (bouton « Synchroniser » + option d'auto-refresh) ; idempotent via l'ID de deal MT5 (`external_id` unique sur `trades`).
- **Cas durs à tester** : partial fills, hedging (plusieurs positions même symbole), SL modifié en cours, position sans SL (→ risque « inconnu », alerte).

### B3. Enforcement réel *(sous-phase, avec garde-fous honnêtes)*
- **Quoi** : à la limite atteinte, **fermer** les positions / refuser le sizing. Passage de « conseil » à « risk desk ».
- **Réalité** : « fermer au dépassement » est faisable (envoi d'ordre via MT5/MetaApi) ; « empêcher un ordre » est limité (latence, T&C broker). **La BRVM reste advisory** (pas d'API retail). À livrer derrière un flag explicite + double confirmation.

**Livrable B** : pour le forex, l'outil reflète le compte réel et peut agir dessus. La BRVM reste manuelle (fluidifiée par A).

---

## TRACK C — Intelligence comportementale *(le différenciateur, ton terrain d'analyste)*

### C1. Détection de tilt en temps réel
- **Signaux** (heuristiques explicables, pas de boîte noire) : ré-entrées rapprochées (temps entre trades qui s'effondre), **taille qui augmente après une perte**, fréquence des tags `Revenge`/`FOMO`, trades/heure au-dessus de ta normale.
- **Code** : [`src/behavior.py`](src/behavior.py) — fonctions pures sur le flux de trades → `TiltScore` + raisons. Surfacé dans le cockpit ([`app.py`](app.py)) **avant** le mur, et poussé en notification ([`src/notify.py`](src/notify.py)).

### C2. Coach hebdomadaire (prescriptif, pas descriptif)
- **Quoi** : rapport qui dit quoi **changer**. Win rate conditionnel (« après 2 pertes, ton WR chute de X% »), perf par heure/jour/émotion/setup/instrument, espérance par setup, coût réel des trades émotionnels (« Revenge = −2.3R, 4 cette semaine »).
- **Code** : [`pages/5_Coach.py`](pages/5_Coach.py) (pandas + Altair, tu es à l'aise) ; s'appuie sur les tags émotion (déjà là) + setup (A4) + données MT5 (B).

### C3. Taille & limites recommandées, data-driven
- **Quoi** : suggérer le risque/trade et la perte max journalière à partir de **ta** volatilité de rendements et de **tes** drawdowns réels (pas une formule générique). Kelly *fractionné et plafonné*, ou simple ciblage de volatilité — explicable.
- **Code** : [`src/behavior.py`](src/behavior.py) `suggest_limits(history)` → valeurs proposées dans [`pages/2_Regles_et_compte.py`](pages/2_Regles_et_compte.py) (« suggéré : 0.8% » à côté du champ). L'humain valide, l'outil n'impose pas.

**Livrable C** : l'outil ne se contente plus de montrer le passé, il **anticipe le tilt** et **recommande** — c'est ce qui le rend « utile » au sens fort.

---

## Transverses

- **Migrations** : versionner le schéma (`PRAGMA user_version`) dans [`src/db.py`](src/db.py) ; chaque montée de version = fonction de migration idempotente + test de migration.
- **Tests** : garder la discipline actuelle (moteur pur = tests exhaustifs). Nouveaux modules purs (`fx`, `correlation`, `behavior`) = tests unitaires ; MT5 = tests avec un connecteur mocké (jamais de terminal réel en CI) ; migrations = test « ancien schéma → nouveau ».
- **Compat** : `risk_engine` reste le cœur inchangé — tout le reste l'alimente ou l'exploite.

## Risques & vérités

- **A2/A3 dépendent de données de prix** → prévoir un fallback manuel propre (l'outil doit marcher hors-ligne).
- **B (MT5 local)** est **Windows + terminal ouvert** ; le cloud (MetaApi) viendra avec le multi-device.
- **Enforcement** : promets « fermeture au dépassement », pas « empêcher tout ordre » — sois honnête dans l'UX.
- **BRVM** : aucune automatisation broker réaliste ; sa valeur passe par A (fluidité) + C (coaching).

## Sprint 1 proposé (2 semaines)

Fondation **A1 + A2 + A5** (multi-comptes + FX + log inviolable) avec migration versionnée et tests — parce que **tout** le reste (B et C) s'appuie dessus. A3 et A4 suivent dans la foulée.

---

## ✅ Sprint 1 — LIVRÉ

- **A1 multi-comptes** : table `accounts`, `account_id` sur toutes les tables, `list/create/save_account`, sélecteur de compte partagé ([`components/account_selector.py`](components/account_selector.py)), câblé sur les 5 pages. Clés de widgets namespacées par compte (pas de fuite entre comptes).
- **A2 FX** : [`src/fx.py`](src/fx.py) (convert pur + inverse), table `fx_rates`, section « Taux de change » dans la config.
- **A5 log inviolable** : table append-only `trade_events` (OPEN/CLOSE/CANCEL), écrite à chaque mutation, vue d'audit dans la config.
- **Migration versionnée** (`PRAGMA user_version`, v0→v1) idempotente — **vérifiée en réel** : la base existante a été migrée au lancement (7 règles préservées, ancienne table `account` supprimée).
- **Tests : 58/58** (dont migration v0→v1, FX, isolation multi-comptes, événements append-only).

**Reste sur Track A** : A3 (exposition corrélée) + A4 (checklist pré-trade). Puis Track B (sync MT5), puis Track C (comportemental).

---

## ✅ Sprint 2 — Track A terminé (A3 + A4)

- **A3 exposition corrélée** : [`src/correlation.py`](src/correlation.py) (risque effectif de portefeuille, pur + testé), table `correlations`, affichage « risque ouvert effectif » au cockpit, gestion des corrélations en config. La somme simple reste le garde-fou dur.
- **A4 checklist pré-trade** : table `checklist_items`, checklist **bloquante** à l'ouverture (tout cocher pour valider) + champs `setup`/`thesis` sur le trade, gestion de la checklist en config.
- **Migration v1→v2** vérifiée en réel.
- **Tests : 67/67**.

## ✅ Sprint 3 — Track B complet (sync MT5)

- **Interface broker** : [`src/brokers/base.py`](src/brokers/base.py) (`BrokerConnector`, `BrokerPosition`, `BrokerDeal`), [`mock.py`](src/brokers/mock.py) (tests), [`mt5.py`](src/brokers/mt5.py) (adaptateur MetaTrader5 réel, import différé).
- **Réconciliation** : [`src/brokers/sync.py`](src/brokers/sync.py) — import positions/deals, risque calculé depuis le SL (`position_risk_amount`), MT5 = source de vérité, trades manuels intouchés, idempotent, positions sans stop signalées.
- **Enforcement** : `close_all_positions` (fermeture de toutes les positions au blocage), opt-in par compte + confirmation dans le cockpit.
- **Schéma v3** : colonnes MT5 sur `accounts` (`mt5_login/server/path/enforce_enabled`), index unique partiel `external_id`. Migration v2→v3.
- **UI** : type de compte MANUAL/MT5 + connexion dans la config, bouton « 🔄 Synchroniser MT5 » au cockpit (dégradation gracieuse si paquet/terminal absent).
- **Tests : 75/75** (sync via mock : ouverture, idempotence, clôture sur disparition, SL resserré, sans stop, trades manuels préservés, enforcement).

## ✅ Sprint 4 — Track C complet (intelligence comportementale)

- **C1 — Détection de tilt temps réel** : [`src/behavior.py`](src/behavior.py) `assess_tilt` (signaux explicables : ré-entrées rapprochées, ré-entrée après perte, montée de taille après perte, émotions Revenge/FOMO, sur-trading → score 0–100 + niveau CALME/VIGILANCE/TILT). Bannière au cockpit **avant** le mur.
- **C2 — Coach prescriptif** : [`pages/5_Coach.py`](pages/5_Coach.py) — win rate conditionnel après une perte, coût des émotions, performance par heure/jour/setup, espérance. Fonctions pures `conditional_winrate_after_loss`, `expectancy_R`, `winrate`.
- **C3 — Tailles recommandées data-driven** : `suggest_limits` (demi-Kelly plafonné/planché, explicable) affiché en config à côté des règles. L'outil suggère, le trader décide.
- **Tests : 89/89**. Vérifié live : bannière TILT (score 100) déclenchée par un scénario réaliste sans faux-positif de blocage dur ; page Coach complète.

---

## 🎯 Bilan V2 (Tracks A + B + C)

Tout le périmètre V2 de la roadmap est livré : fondations multi-comptes/FX/audit (A1/A2/A5), exposition corrélée (A3), checklist pré-trade (A4), sync broker MT5 + enforcement (B), et intelligence comportementale (C). **89 tests, 4 versions de schéma migrées proprement.**

---

## ✅ Sprint 5 — Consolidation

- **Config de tilt par compte** : table `tilt_config` (migration v4), réglable dans « Règles & compte », utilisée par le cockpit.
- **Packaging** : [`pyproject.toml`](pyproject.toml) (installable, extra `mt5`/`dev`, script `risk-guard`), lanceur [`run.py`](run.py), `__version__`.
- **Doc utilisateur** : [`GUIDE_UTILISATEUR.md`](GUIDE_UTILISATEUR.md) (non-technique, pas-à-pas pour le trader).

## ✅ Sprint 6 — Chantier cloud / mobile

- **Auth multi-utilisateur** : [`src/auth.py`](src/auth.py) (PBKDF2 salé), table `users` + `user_id` sur `accounts` (migration v5). Isolation par utilisateur ; gate de connexion opt-in (`RISK_REQUIRE_AUTH=1` ou secret `[auth] require`). Mode local inchangé (aucun login).
- **Mobile** : CSS responsive ([`components/shell.py`](components/shell.py)) — mise en page < 640 px, cibles tactiles ≥ 44 px. Vérifié en viewport 375 px.
- **Déploiement** : [`Dockerfile`](Dockerfile) + `.dockerignore` + [`DEPLOIEMENT.md`](DEPLOIEMENT.md) (Docker, Streamlit Cloud, secrets, sécurité, limites).
- **Tests : 97/97** (auth : hachage, isolation, mode requis ; migration v0→v5).

## ✅ Sprint 7 — Backend Postgres

- Couche connexion **backend-agnostique** dans [`src/db.py`](src/db.py) : SQLite par défaut, **Postgres** si `DATABASE_URL`. Adaptation automatique du DDL (SERIAL), des placeholders (`?`→`%s`), de la récupération d'id (`lastval()`), et du versioning (table `schema_meta`).
- Dépendance optionnelle `psycopg` (extra `postgres`), doc dans [`DEPLOIEMENT.md`](DEPLOIEMENT.md).
- **Honnêteté** : parties pures testées (adaptation DDL, placeholders) ; SQLite reste 100 % vert. À **valider sur une vraie instance PG** (non exécutable dans le build).

## ✅ Sprint 8 — Onboarding + PWA (adoption)

- **Onboarding** : flag `onboarded` (migration v6) + assistant premier lancement ([`components/onboarding.py`](components/onboarding.py)) — capital, devise, fuseau, **profil de risque** (Prudent/Équilibré/Agressif) qui applique des règles préréglées. Les comptes existants sont marqués configurés à la migration.
- **PWA** : manifest + service worker + icône ([`static/`](static/)), injection dans le document parent ([`components/pwa.py`](components/pwa.py)), fichiers statiques servis par Streamlit. **Vérifié en live** : manifest lié, SW enregistré, installable « à l'écran d'accueil ».
- **Tests : 105/105**. Migration v0→**v6** vérifiée en réel.

### Reste (honnête)
- **Validation Postgres** sur instance réelle + éventuel pool de connexions.
- Icônes PWA **PNG maskables** (192/512) pour un prompt d'installation optimal (SVG en place).
- **Sync MT5 en cloud** : reste locale (terminal Windows).
