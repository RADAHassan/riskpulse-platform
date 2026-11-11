from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_PATH = BASE_DIR / "data" / "creditcard.csv"
ARTIFACTS_DIR = BASE_DIR / "artifacts"
FIGS_DIR = ARTIFACTS_DIR / "figures"

TEST_SIZE = 0.15
CAL_SIZE = 0.15 / 0.85
RANDOM_STATE = 42

ALPHA = 0.05
REVIEW_LOWER_BOUND = 0.0100
REVIEW_UPPER_BOUND = 0.7000

# Tuned Champion Parameters via Optuna Bayesian Optimization (PR-AUC: 0.8559)
XGB_PARAMS = {
    "n_estimators": 213,
    "max_depth": 5,
    "learning_rate": 0.0955,
    "min_child_weight": 4,
    "subsample": 0.7496,
    "colsample_bytree": 0.7272,
    "gamma": 0.3104,
    "eval_metric": "logloss",
    "tree_method": "hist",
    "random_state": RANDOM_STATE,
    "n_jobs": -1
}
