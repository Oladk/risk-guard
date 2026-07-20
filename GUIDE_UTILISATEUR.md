# Guide utilisateur — Risk Guard 🛡️

Ce guide s'adresse au **trader** (pas au développeur). Il explique comment utiliser
l'outil au quotidien pour tenir tes règles de risque.

---

## 1. Démarrer

1. Installe les dépendances (une seule fois) :
   ```bash
   pip install -r requirements.txt
   ```
2. Lance l'application :
   ```bash
   streamlit run app.py      # ou : python run.py
   ```
3. Ton navigateur s'ouvre sur le **Cockpit**. Une base de données locale est créée
   automatiquement (tes données restent sur ta machine).

---

## 2. Régler ton compte (à faire en premier)

Va dans **⚙️ Règles & compte** (barre latérale) :

- **Solde initial**, **devise** (ex. XOF, USD).
- **Fuseau horaire** et **heure de reset journalier** : c'est l'heure à laquelle tes
  compteurs du jour repartent à zéro (par défaut minuit, ton fuseau).
- **Unité préférée** : `%` du capital ou `R` (1R = un % fixe que tu définis).
- **Règles de risque** : active celles que tu veux et fixe les seuils :
  - Perte max journalière / hebdomadaire
  - Risque max par trade
  - Pertes consécutives max (anti-tilt)
  - Trades max par jour
  - Exposition ouverte max
  - Objectif de gain (stop-win)

> 💡 Après ~20 trades, l'outil te **suggère** un risque/trade et une perte max
> journalière calculés sur ton historique. Il suggère, tu décides.

---

## 3. Loguer un trade

Va dans **📓 Journal**.

### Ouvrir
1. Renseigne instrument, marché, direction, et ton **risque** (% ou R).
2. (Optionnel) prix d'entrée / stop / taille pour le R réel.
3. (Optionnel) **Setup** et **Thèse** (« pourquoi maintenant ? »).
4. (Optionnel) ton **émotion** du moment, en 1 clic.
5. **Coche toute la checklist pré-trade** — sinon l'ouverture est refusée.
6. Clique **Ouvrir le trade**.

Si le trade violerait une de tes règles, il est **refusé** avec l'explication précise
(quelle règle, de combien tu dépasses).

### Clôturer
Sélectionne une position ouverte, saisis le **P&L réalisé** (négatif si perte),
clique **Clôturer**. La clôture reste **toujours possible**, même en mode strict.

---

## 4. Lire le Cockpit

- **En-tête** : solde de début de journée, P&L du jour, risque ouvert, statut global
  (🟢 / 🟠 / 🔴).
- **Jauges** : où tu en es sur chaque limite (vert < 80 %, orange ≥ 80 %, rouge = 100 %).
- **Risque ouvert effectif** : ton exposition ajustée par les corrélations (indicatif).
- **Alerte comportementale (tilt)** : si tes gestes ressemblent à du tilt (ré-entrées
  rapides, montée de taille après une perte, émotions…), une bannière t'avertit
  **avant** que tu ne dépasses tes limites.

### Quand une limite est atteinte
Par défaut, l'outil est en **mode conseil** : tu vois une **alerte rouge + son**
(« Limite atteinte — à toi de décider »). L'outil **ne bloque pas** ; c'est à toi de
reprendre la main. Tu peux loguer un trade en quelques secondes via la **Saisie éclair**.

> 🔒 **Mode strict (optionnel)** : dans *Règles & compte*, tu peux passer une règle en
> **Blocage**. Elle affichera alors un écran STOP et **refusera** d'enregistrer un trade
> qui la viole jusqu'au reset (la clôture reste toujours possible).

> 🔊 Si tu n'entends pas le son, clique **« Activer le son des alertes »** dans la
> barre latérale (le navigateur bloque l'audio tant que tu n'as pas interagi).

---

## 5. Les autres pages

- **🧮 Calculateur** : calcule ta taille de position (lots forex / actions BRVM) à
  partir de ton risque et de la distance au stop, puis pré-remplit un nouveau trade.
- **📊 Analytics** : courbe d'équité, win rate, R moyen, P&L par émotion, respect des règles.
- **🧠 Coach** : ce que tu dois **changer** — ton win rate après une perte, le coût de
  chaque émotion, tes meilleures heures/jours, ton espérance par setup.

---

## 6. Réglages avancés (⚙️ Règles & compte)

- **Plusieurs comptes** : crée un compte par marché (ex. forex + BRVM), chacun avec son
  capital et ses règles. Change de compte via le sélecteur en haut de la barre latérale.
- **Taux de change** : renseigne-les si tu trades dans une devise ≠ celle du compte.
- **Checklist pré-trade** : personnalise les points obligatoires.
- **Corrélations** : renseigne-les pour affiner le « risque ouvert effectif ».
- **Détection de tilt** : ajuste les seuils (ré-entrées, montée de taille, sur-trading…).

---

## 7. Synchronisation MT5 (optionnel, forex)

Pour un compte MetaTrader 5 :
1. Installe le paquet : `pip install MetaTrader5` (Windows).
2. Garde ton terminal MT5 **ouvert et connecté**.
3. Dans **⚙️ Règles & compte**, passe le type de compte à **MT5**.
4. Au cockpit, clique **🔄 Synchroniser MT5** : tes positions et trades clôturés sont
   importés (le risque est calculé depuis ton stop).
5. (Optionnel) active l'**enforcement** pour fermer toutes tes positions d'un clic quand
   une limite est atteinte.

---

## 8. Notifications (optionnel)

Reçois les alertes sur ton téléphone/email : copie `.streamlit/secrets.toml.example`
en `.streamlit/secrets.toml`, remplis les identifiants (email Gmail / topic ntfy), et
active **📱 Notifications externes** dans les réglages du compte.

---

## 9. Bonnes pratiques

- **Logue chaque trade** — un journal incomplet rend l'outil aveugle.
- **Respecte la checklist** : c'est ta discipline avant l'émotion.
- Quand l'**alerte tilt** s'affiche, fais une pause. C'est là que se perdent les comptes.
- Quand l'alerte **« Limite atteinte »** s'affiche, tu as fait ton travail de la journée. Reviens demain.
