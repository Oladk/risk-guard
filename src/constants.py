"""Constantes partagées : types de règles, tags émotion, valeurs par défaut."""

# --- Tags émotionnels (chips 1 clic à l'ouverture) ---------------------------
EMOTION_TAGS = [
    "Calme",
    "Confiant",
    "Discipliné",
    "Hésitant",
    "Impatient",
    "FOMO",
    "Revenge",
    "Fatigué",
]

# --- Marchés et directions ---------------------------------------------------
MARKETS = ["FOREX", "BRVM", "OTHER"]
DIRECTIONS = ["LONG", "SHORT"]

# --- Statuts de trade --------------------------------------------------------
STATUS_OPEN = "OPEN"
STATUS_CLOSED = "CLOSED"
STATUS_CANCELLED = "CANCELLED"

# --- Types de règles ---------------------------------------------------------
RULE_DAILY_LOSS = "daily_loss"
RULE_WEEKLY_LOSS = "weekly_loss"
RULE_PER_TRADE_RISK = "per_trade_risk"
RULE_MAX_CONSECUTIVE_LOSSES = "max_consecutive_losses"
RULE_MAX_TRADES_DAY = "max_trades_day"
RULE_MAX_OPEN_EXPOSURE = "max_open_exposure"
RULE_DAILY_PROFIT_TARGET = "daily_profit_target"

RULE_TYPES = [
    RULE_DAILY_LOSS,
    RULE_WEEKLY_LOSS,
    RULE_PER_TRADE_RISK,
    RULE_MAX_CONSECUTIVE_LOSSES,
    RULE_MAX_TRADES_DAY,
    RULE_MAX_OPEN_EXPOSURE,
    RULE_DAILY_PROFIT_TARGET,
]

RULE_LABELS = {
    RULE_DAILY_LOSS: "Perte max journalière",
    RULE_WEEKLY_LOSS: "Perte max hebdomadaire",
    RULE_PER_TRADE_RISK: "Risque max par trade",
    RULE_MAX_CONSECUTIVE_LOSSES: "Pertes consécutives max",
    RULE_MAX_TRADES_DAY: "Trades max / jour",
    RULE_MAX_OPEN_EXPOSURE: "Exposition ouverte max",
    RULE_DAILY_PROFIT_TARGET: "Objectif de gain (stop-win)",
}

RULE_HELP = {
    RULE_DAILY_LOSS: "Bloque quand la perte potentielle du jour (pertes réalisées + risque ouvert) atteint le seuil.",
    RULE_WEEKLY_LOSS: "Bloque quand la perte potentielle de la semaine (lun→dim) atteint le seuil.",
    RULE_PER_TRADE_RISK: "Refuse un trade dont le risque planifié dépasse le seuil.",
    RULE_MAX_CONSECUTIVE_LOSSES: "Bloque après N trades perdants d'affilée (anti-tilt).",
    RULE_MAX_TRADES_DAY: "Bloque quand le nombre de trades ouverts aujourd'hui atteint la limite.",
    RULE_MAX_OPEN_EXPOSURE: "Refuse un trade qui ferait dépasser le risque ouvert total.",
    RULE_DAILY_PROFIT_TARGET: "Arrête la journée quand l'objectif de gain réalisé est atteint (empêche de rendre les gains).",
}

# Unités : PCT (fraction du capital, ex 0.03), R (multiple de 1R), COUNT (entier)
UNIT_PCT = "PCT"
UNIT_R = "R"
UNIT_COUNT = "COUNT"

# Unité par défaut / autorisée pour chaque règle
RULE_DEFAULT_UNIT = {
    RULE_DAILY_LOSS: UNIT_PCT,
    RULE_WEEKLY_LOSS: UNIT_PCT,
    RULE_PER_TRADE_RISK: UNIT_PCT,
    RULE_MAX_CONSECUTIVE_LOSSES: UNIT_COUNT,
    RULE_MAX_TRADES_DAY: UNIT_COUNT,
    RULE_MAX_OPEN_EXPOSURE: UNIT_PCT,
    RULE_DAILY_PROFIT_TARGET: UNIT_PCT,
}

# Règles à seuil monétaire continu (jauge + avertissement à 80%).
# Les règles COUNT et per_trade sont "tout ou rien" (pas de jauge d'approche).
CONTINUOUS_MONEY_RULES = {
    RULE_DAILY_LOSS,
    RULE_WEEKLY_LOSS,
    RULE_MAX_OPEN_EXPOSURE,
    RULE_DAILY_PROFIT_TARGET,
}

# Règles dont le déclenchement engage le verrou STOP global jusqu'au reset.
# per_trade_risk et max_open_exposure ne verrouillent pas : ils refusent juste
# le trade concerné (l'un est trop gros, l'autre se libère à la clôture).
GLOBAL_LOCK_RULES = {
    RULE_DAILY_LOSS,
    RULE_WEEKLY_LOSS,
    RULE_MAX_CONSECUTIVE_LOSSES,
    RULE_MAX_TRADES_DAY,
    RULE_DAILY_PROFIT_TARGET,
}

# --- Valeurs par défaut du compte -------------------------------------------
DEFAULT_ACCOUNT = {
    "base_currency": "XOF",
    "initial_balance": 1_000_000.0,
    "timezone": "Africa/Porto-Novo",  # UTC+1, sans heure d'été
    "reset_hour": 0,
    "week_start": "MONDAY",
    "warning_threshold_pct": 0.80,
    "preferred_unit": UNIT_PCT,
    "one_R_pct": 0.01,  # 1R = 1% du solde de début de journée
    "sound_enabled": 1,
    "notify_enabled": 0,
}

# --- Règles par défaut (seed) ------------------------------------------------
# (rule_type, enabled, threshold_value, threshold_unit, action)
# Par défaut : mode ALERTE (WARN). L'outil prévient, il ne bloque pas.
# Le trader peut passer une règle en BLOCK (mode strict) s'il veut un refus dur.
DEFAULT_RULES = [
    (RULE_DAILY_LOSS, 1, 0.03, UNIT_PCT, "WARN"),
    (RULE_WEEKLY_LOSS, 1, 0.06, UNIT_PCT, "WARN"),
    (RULE_PER_TRADE_RISK, 1, 0.01, UNIT_PCT, "WARN"),
    (RULE_MAX_CONSECUTIVE_LOSSES, 1, 3, UNIT_COUNT, "WARN"),
    (RULE_MAX_TRADES_DAY, 1, 5, UNIT_COUNT, "WARN"),
    (RULE_MAX_OPEN_EXPOSURE, 1, 0.02, UNIT_PCT, "WARN"),
    (RULE_DAILY_PROFIT_TARGET, 0, 0.05, UNIT_PCT, "WARN"),
]

# --- Niveaux d'état de risque ------------------------------------------------
LEVEL_OK = "OK"
LEVEL_WARN = "WARN"
LEVEL_BLOCK = "BLOCK"

# --- Checklist pré-trade par défaut (A4) -------------------------------------
DEFAULT_CHECKLIST = [
    "Mon stop-loss est défini",
    "Le setup correspond à mon plan de trading",
    "Je ne cherche pas à récupérer une perte (pas de revenge)",
]

# --- Profils de risque (onboarding) ------------------------------------------
# Valeurs en fraction (PCT) ou nombre (COUNT) selon l'unité par défaut de la règle.
RISK_PROFILES = {
    "Prudent": {
        RULE_DAILY_LOSS: 0.02, RULE_WEEKLY_LOSS: 0.04, RULE_PER_TRADE_RISK: 0.005,
        RULE_MAX_CONSECUTIVE_LOSSES: 2, RULE_MAX_TRADES_DAY: 3, RULE_MAX_OPEN_EXPOSURE: 0.01,
    },
    "Équilibré": {
        RULE_DAILY_LOSS: 0.03, RULE_WEEKLY_LOSS: 0.06, RULE_PER_TRADE_RISK: 0.01,
        RULE_MAX_CONSECUTIVE_LOSSES: 3, RULE_MAX_TRADES_DAY: 5, RULE_MAX_OPEN_EXPOSURE: 0.02,
    },
    "Agressif": {
        RULE_DAILY_LOSS: 0.05, RULE_WEEKLY_LOSS: 0.10, RULE_PER_TRADE_RISK: 0.02,
        RULE_MAX_CONSECUTIVE_LOSSES: 4, RULE_MAX_TRADES_DAY: 8, RULE_MAX_OPEN_EXPOSURE: 0.04,
    },
}

# --- Détection de tilt : seuils par défaut (C1, configurables par compte) -----
DEFAULT_TILT = {
    "min_gap_minutes": 5.0,
    "reentry_window_minutes": 15.0,
    "escalation_ratio": 1.5,
    "emotion_threshold": 2,
    "overtrade_count": 6,
    "vigilance_threshold": 25,
    "tilt_threshold": 50,
}
