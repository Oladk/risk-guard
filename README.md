# 🛡️ Risk Guard — Gestion de capital & de risque pour traders

Un **garde-fou personnel** pour traders particuliers (forex, BRVM, etc.). Tu définis
tes règles de risque, tu logues tes trades manuellement, et l'outil calcule ton
**risque consommé en temps réel**. Quand une limite est atteinte, il **bloque durement**
(overlay STOP plein écran + son) — pour t'empêcher de sur-risquer après une série de
gains, et de t'enfoncer après une série de pertes.

> MVP local, mono-utilisateur, saisie manuelle (pas d'intégration broker). Voir
> [`SPEC.md`](SPEC.md) pour toutes les décisions de conception.

---

## Fonctionnalités

- **Cycle de trade en 2 temps** : ouverture (risque planifié via distance au stop) → clôture (P&L réel).
- **Risque consommé = pertes réalisées + risque ouvert** (worst-case). Base : solde de **début de journée** (figé au reset).
- **7 règles configurables** : perte max journalière / hebdomadaire, risque max par trade, pertes consécutives, trades/jour, exposition ouverte max, objectif de gain (stop-win).
- **Unités interchangeables** : % du capital ou R-multiple (1R = un % fixe du capital).
- **Mode conseil par défaut** : l'outil **alerte** fortement (orange à 80 %, rouge à 100 %) mais **ne bloque pas** — le trader garde la main. Saisie éclair pour loguer un trade en quelques secondes.
- **Mode strict optionnel** (par règle) : si tu le choisis, une règle passe en **Blocage** — overlay STOP + refus d'enregistrement jusqu'au reset. La **clôture** de positions reste toujours possible.
- **Tag émotionnel** en 1 clic à l'ouverture (Calme, FOMO, Revenge…).
- **Calculateur de position** (lots forex / actions BRVM) qui pré-remplit un nouveau trade.
- **Analytics** : courbe d'équité, win rate, R moyen, espérance, P&L par émotion, respect des règles.
- **Notifications** email + push (ntfy) au moment de l'alerte, + digest quotidien optionnel.

---

## Installation

```bash
pip install -r requirements.txt
```

> Sous Windows, le paquet `tzdata` (inclus) est requis pour les fuseaux horaires.

## Lancer l'app

```bash
streamlit run app.py
```

Au premier lancement, la base SQLite (`data/risk.db`) et les valeurs par défaut sont
créées automatiquement. Va dans **⚙️ Règles & compte** pour régler ton capital, ton
fuseau, ton heure de reset et tes limites.

## Configuration des notifications (optionnel)

1. Copie `.streamlit/secrets.toml.example` en `.streamlit/secrets.toml`.
2. **Email** : renseigne un [mot de passe d'application Gmail](https://myaccount.google.com/apppasswords) et passe `enabled = true`.
3. **Push** : choisis un `topic` privé, abonne-toi dessus depuis l'app mobile [ntfy](https://ntfy.sh), et passe `enabled = true`.
4. Active « 📱 Notifications externes » dans **Règles & compte**.

## Digest quotidien (optionnel)

`scripts/daily_digest.py` envoie un récap de fin de journée. À planifier via le
Planificateur de tâches Windows (exemple dans l'en-tête du script).

## Multi-comptes, FX, checklist & corrélations (V2)

- **Multi-comptes** : gère plusieurs comptes (ex. forex + BRVM), chacun avec son
  capital, ses règles, son journal. Sélecteur en haut de la barre latérale.
- **Multi-devises** : renseigne des taux de change (**Règles & compte → Taux de change**)
  quand la cotation diffère de la devise du compte.
- **Checklist pré-trade** : points obligatoires à cocher avant chaque ouverture
  (configurable par compte). Capture aussi le *setup* et la *thèse* du trade.
- **Exposition corrélée** : renseigne des corrélations entre instruments ; le cockpit
  affiche un *risque ouvert effectif* (la somme simple reste le garde-fou dur).
- **Journal d'audit** : chaque ouverture/clôture est tracée dans un log append-only.

## Intelligence comportementale (V2)

- **Détection de tilt** (cockpit) : l'app repère en temps réel les patterns dangereux
  — ré-entrées rapprochées, ré-entrée juste après une perte, montée de taille après
  une perte, trades Revenge/FOMO, sur-trading — et affiche une alerte **avant** que tu
  ne dépasses tes limites.
- **Coach** (page dédiée) : win rate après une perte, coût réel de chaque émotion,
  performance par heure/jour/setup, espérance — pour savoir *quoi changer*.
- **Limites suggérées** : à partir de ton historique, l'app propose un risque/trade et
  une perte max journalière (demi-Kelly plafonné). Elle suggère, tu décides.

## Synchronisation MT5 (V2, optionnel)

Pour un compte **forex MT5** : passe le compte en type `MT5` (**Règles & compte**),
garde ton terminal MetaTrader 5 ouvert et connecté, installe le paquet
(`pip install MetaTrader5`), puis clique **🔄 Synchroniser MT5** au cockpit. L'outil
importe tes positions ouvertes et tes trades clôturés (risque calculé depuis le stop),
le broker faisant foi. Si l'**enforcement** est activé, tu peux fermer toutes tes
positions d'un clic quand une limite verrouillante est atteinte. Sans le paquet/terminal,
la synchro échoue proprement avec un message clair (le reste de l'app fonctionne).

---

## Tests

```bash
pytest -q
```

Le moteur de risque (`src/risk_engine.py`) et la gestion du temps
(`src/time_utils.py`) sont couverts par des tests unitaires exhaustifs — un bug ici
= un faux sentiment de sécurité. Les pages Streamlit sont couvertes par des smoke
tests (`streamlit.testing`).

---

## Structure

```
app.py                    Cockpit (accueil) : statut live + overlay STOP
pages/                    Journal · Règles & compte · Calculateur · Analytics
components/               Jauges de risque · overlay d'alerte
src/
  risk_engine.py          Cœur : risque consommé + évaluation des règles (pur, testé)
  time_utils.py           Frontières journée de trading / semaine (fuseaux)
  repository.py           CRUD SQLite <-> dataclasses
  db.py                   Connexion + schéma + seed
  sizing.py               Calculateur de taille de position
  notify.py               Email + ntfy
  service.py              Façade : connexion + évaluation
  constants.py            Règles, tags émotion, valeurs par défaut
scripts/daily_digest.py   Digest quotidien (hors app)
tests/                    Tests moteur, temps, données, sizing, notify, smoke UI
```

---

## Limites connues (V1)

- Pas d'intégration broker : saisie 100 % manuelle.
- Le risque des positions ouvertes est le **risque planifié plein** (pas de mark-to-market — aucun flux de prix).
- Pas d'ajustement de corrélation entre positions (somme simple).
- Position sizing forex : suppose devise de cotation = devise du compte, sauf taux de conversion fourni.
- Le son des alertes peut être bloqué par le navigateur tant qu'aucune interaction n'a eu lieu → bouton « Activer le son » dans la barre latérale.
