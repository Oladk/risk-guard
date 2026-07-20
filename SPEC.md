# SPEC — Outil de gestion de capital & de risque pour traders (MVP V1)

## 0. Contexte

Un trader particulier discipliné a deux ennemis symétriques :
- **Après une série de gains** : l'euphorie pousse à sur-risquer et à rendre les profits.
- **Pendant une série de pertes** : le tilt / le revenge trading pousse à dépasser ses propres limites.

Aucun outil grand public ne fait *respecter* les règles de risque que le trader s'est lui-même fixées. Le but du V1 : un **garde-fou personnel**, en saisie manuelle (pas d'intégration broker), qui calcule le **risque consommé en temps réel** et **bloque durement** (pas une alerte discrète) quand une limite est atteinte. Cible : forex + BRVM, particuliers.

Livrable par un data analyst à l'aise en Python/pandas, SQL, Streamlit.

---

## 1. Décisions verrouillées (issues de l'interview)

| Sujet | Décision |
|---|---|
| **Cycle de vie du trade** | Deux étapes : **ouverture** (risque planifié via distance au stop) → **clôture** (P&L réel). |
| **Unité de risque** | Le trader choisit **% du capital** *ou* **R-multiple** (les deux, interchangeables). |
| **Définition de 1R** | `1R = un % fixe du capital` (ex. 1% du solde de début de journée). |
| **« Risque consommé »** | **Pertes réalisées + risque ouvert** (worst-case). Un trade ouvert compte son **risque planifié plein**. |
| **Base de calcul du %** | **Solde de début de journée**, figé au reset. |
| **Reset journalier** | **Configurable** (heure + fuseau). Défaut : **minuit, fuseau local**. |
| **Semaine** | **Lundi 00:00 → dimanche 23:59** (calendaire). |
| **Multi-positions** | **Somme simple** des risques planifiés des positions ouvertes. |
| **Mode par défaut** | **Conseil** : l'outil **alerte** fortement (orange à 80 %, rouge à 100 %) mais **ne bloque pas** — le trader décide. *(Recentrage V2.)* |
| **Blocage** | **Mode strict optionnel, par règle** : si le trader passe une règle en « Blocage », STOP plein écran + refus d'enregistrement d'un nouveau trade jusqu'au reset. |
| **Positions ouvertes en STOP** | **Clôturer = OUI, ouvrir = NON.** |
| **Alerte** | **Overlay rouge plein écran + son** navigateur. |
| **Seuils** | **Avertissement à ~80%** (orange) *puis* blocage à 100% (rouge). |
| **Tag émotionnel** | **Chips prédéfinis, 1 clic, à l'ouverture**, optionnel. |
| **Instruments** | **Hybride** : risque saisi directement, champs entrée/stop/taille optionnels. |
| **Comptes** | **Un seul compte** en V1. |
| **Utilisateurs / déploiement** | **Mono-utilisateur, local, SQLite.** Pas de login. |
| **Règles V1 (7)** | daily_loss, weekly_loss, per_trade_risk, max_consecutive_losses, max_trades_day, max_open_exposure, daily_profit_target. |
| **Extensions V1** | Position sizing auto, notifications externes, dashboard analytics léger. |

---

## 2. Périmètre

### Dans le V1
- Moteur de risque temps réel (les 7 règles).
- Journal des trades (ouvrir / clôturer), tag émotionnel à l'ouverture.
- Cockpit : jauges de risque consommé, statut STOP/OK.
- Alerte forte (overlay rouge + son) + blocage dur + refus d'enregistrement.
- Configuration des règles + du compte (capital, fuseau, reset, seuils, unité préférée).
- Position sizing auto (lots forex / actions BRVM).
- Notifications externes (email + push ntfy) au moment de l'alerte/blocage, + digest quotidien optionnel.
- Dashboard analytics léger : courbe d'équité, win rate, R moyen, espérance, P&L par émotion, taux de respect.
- Export CSV du journal.

### Hors scope V1
- Intégration broker / import CSV broker / sync automatique.
- Multi-utilisateur, authentification, multi-comptes.
- Backtesting, analyse statistique avancée.
- Ajustement de corrélation entre positions.
- Application mobile native.
- Mark-to-market des positions ouvertes (le risque ouvert = risque planifié plein).

> ⚠️ **Timeline.** Cœur seul ≈ 2 semaines. Avec les 3 extensions, ≈ 3 à 3,5 semaines. Build **phasé** : produit utilisable et sûr dès la fin de la Phase 2.

> 💡 **Notifications.** La saisie étant 100% manuelle, l'état de risque ne change que lorsque le trader agit dans l'app. Les notifications externes répercutent l'alerte en session vers téléphone/email + digest programmé optionnel.

---

## 3. Architecture technique

- **App** : Streamlit multipage (`pages/`).
- **Stockage** : SQLite (`data/risk.db`), `sqlite3` stdlib + requêtes paramétrées ; lectures analytiques via pandas.
- **Temps/fuseaux** : `zoneinfo` (+ `tzdata` sous Windows). Timestamps stockés en **UTC** ; conversion vers le fuseau configuré pour les frontières jour/semaine.
- **Graphiques** : Altair.
- **Overlay + son** : `st.markdown(unsafe_allow_html=True)` + `components.v1.html`. Autoplay bloqué par le navigateur → bouton « activer le son ».
- **Notifications** : `smtplib` (Gmail app password) + `requests` vers `ntfy.sh`. Secrets dans `.streamlit/secrets.toml`.
- **Tests** : `pytest` sur `risk_engine` et `time_utils` (fonctions pures).

### Structure
```
├─ app.py                     # Cockpit (accueil)
├─ requirements.txt / README.md / SPEC.md / .gitignore
├─ .streamlit/config.toml + secrets.toml (gitignored)
├─ data/risk.db               (gitignored)
├─ src/  db.py constants.py time_utils.py repository.py risk_engine.py sizing.py notify.py
├─ pages/  1_Journal.py 2_Regles_et_compte.py 3_Calculateur.py 4_Analytics.py
├─ components/  alert_overlay.py risk_meters.py
└─ tests/  test_risk_engine.py test_time_utils.py
```

---

## 4. Modèle de données (SQLite)

- **`account`** (ligne unique) : base_currency, initial_balance, timezone, reset_hour, week_start, warning_threshold_pct, preferred_unit, one_R_pct, sound_enabled, notify_enabled.
- **`balance_adjustments`** : date(UTC), amount(signé), type(DEPOSIT|WITHDRAWAL), note.
- **`risk_rules`** (une ligne/type) : rule_type, enabled, threshold_value, threshold_unit(PCT|R|COUNT), action(BLOCK|WARN).
- **`trades`** : instrument, market, direction, status(OPEN|CLOSED|CANCELLED), opened_at, closed_at, trading_day, planned_risk_pct, planned_risk_amount, planned_risk_R, entry_price?, stop_price?, take_profit?, size?, realized_pnl_amount?, realized_R?, outcome?, emotion_tag?, note?.
- **`alerts_log`** : timestamp(UTC), rule_type, level(WARN|BLOCK), context.

---

## 5. Moteur de risque (`risk_engine.py`) — le cœur

Fonctions **pures** (snapshot → état de risque), testables sans DB.

- `day_start_balance(now)` = initial_balance + Σ ajustements avant le début du jour + Σ P&L réalisé des trades clôturés avant le début du jour.
- `realized_pnl_today` = Σ P&L des trades clôturés dans `[début_jour, prochain_reset)`.
- `open_risk_now` = Σ `planned_risk_amount` des trades OPEN.
- `worst_case_drawdown_today` = `open_risk_now − realized_pnl_today`.

**Limite de perte L** : consommé = worst_case_drawdown ; OK `<80%` · WARN `[80%,100%)` · BLOCK `≥100%`.

**Contrôle à l'ouverture (risque `r`)** — refus si :
- daily_loss : `(open_risk + r) − realized_today ≥ L_jour`
- weekly_loss : idem sur la semaine
- per_trade_risk : `r > max_par_trade`
- max_open_exposure : `open_risk + r > expo_max`
- max_trades_day : `count(ouverts aujourd'hui) ≥ max`
- max_consecutive_losses : `streak_pertes ≥ N`
- daily_profit_target : `realized_today ≥ objectif` → STOP

**Mode STOP** : engagé dès qu'une règle BLOCK est franchie → refus des nouvelles ouvertures + overlay. La **clôture reste autorisée**. Verrou levé au prochain reset (jour/semaine).

Stockage interne en montant (devise) ; affichage en % ou R via `one_R_pct`.

---

## 6. Temps (`time_utils.py`)

- `trading_day_bounds(now, tz, reset_hour)` → `(start_utc, end_utc)`.
- `week_bounds(now, tz)` → lundi 00:00 → lundi suivant (local).
- `trading_day_of(ts, tz, reset_hour)` → date de trading d'un timestamp.

---

## 7. Les 7 règles

| rule_type | Unité | Déclencheur | Action | Reset du verrou |
|---|---|---|---|---|
| daily_loss | PCT/R | drawdown worst-case jour ≥ seuil | BLOCK | journalier |
| weekly_loss | PCT/R | drawdown worst-case semaine ≥ seuil | BLOCK | hebdo (lundi) |
| per_trade_risk | PCT/R | risque d'un trade > seuil | BLOCK (ce trade) | immédiat |
| max_consecutive_losses | COUNT | pertes consécutives ≥ N | BLOCK | journalier |
| max_trades_day | COUNT | trades ouverts aujourd'hui ≥ N | BLOCK | journalier |
| max_open_exposure | PCT/R | risque ouvert total > seuil | BLOCK | à la clôture d'une position |
| daily_profit_target | PCT/R | P&L réalisé jour ≥ objectif | BLOCK (stop-win) | journalier |

---

## 8. UX

- **Cockpit** (`app.py`) : en-tête (solde jour, P&L jour, risque ouvert, statut), jauges par règle, overlay STOP rouge + son si BLOCK, liste des positions ouvertes (clôture toujours possible).
- **Journal** (`pages/1`) : ouvrir (instrument, marché, direction, risque %/R, entrée/stop/taille optionnels, chips émotion) avec refus + message si violation ; clôturer (P&L montant ou R auto) ; historique + export CSV.
- **Overlay** : rouge plein écran + `<audio>` (fallback bouton son), bannière orange en approche.

---

## 9. Position sizing (`sizing.py` + `pages/3`)

- **BRVM** : `nb_actions = risk_amount / |entrée − stop|`.
- **Forex** : `lots = risk_amount / (valeur_pip_par_lot × distance_pips)`. Table de specs par paire. Conversion FX complète hors scope (demander valeur du pip/taux si devise ≠ compte).
- Résultat pré-remplit le formulaire du journal.

---

## 10. Notifications (`notify.py`)

- Déclenchées au moment d'un WARN/BLOCK en session : email (smtplib/Gmail app password) + push (`ntfy.sh/<topic>`).
- Optionnel : `scripts/daily_digest.py` via Planificateur Windows (récap fin de journée).

---

## 11. Analytics (`pages/4`)

Sur trades clôturés (pandas + Altair) : courbe d'équité, win rate, R moyen, espérance, P&L par émotion, taux de respect des règles, répartition par marché/jour. Filtres période/marché/émotion.

---

## 12. Build phasé

- **Phase 0** — scaffolding, db, constants, SPEC, README.
- **Phase 1** — time_utils + tests, repository, risk_engine + tests exhaustifs.
- **Phase 2** — pages config + journal, cockpit + jauges, overlay STOP + son. → Livrable sûr.
- **Phase 3** — sizing + calculateur, analytics.
- **Phase 4** — notifications, digest optionnel, polish, README, export CSV.

---

## 13. Vérification

- `pytest tests/` : scénarios chiffrés (série de gains → refus sur-risque, 3 pertes consécutives → STOP, expo max, trade autour du reset, passage de semaine).
- Manuel : config → ouvrir positions → 80% orange → 100% STOP+son+refus → clôturer en STOP → reset → déverrouillage.
