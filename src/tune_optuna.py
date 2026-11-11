import optuna
import joblib
import json
import numpy as np
import pandas as pd
from sklearn.model_selection import StratifiedKFold
from sklearn.preprocessing import RobustScaler
from sklearn.compose import ColumnTransformer
from sklearn.metrics import average_precision_score
from xgboost import XGBClassifier

from src.config import DATA_PATH, ARTIFACTS_DIR, RANDOM_STATE
from src.features import engineer_temporal_features

optuna.logging.set_verbosity(optuna.logging.WARNING)

def load_processed_data():
    print("[1/3] Loading data & calculating rolling velocity features...")
    df = pd.read_csv(DATA_PATH)
    y = df["Class"].astype(int).to_numpy()
    df_features = engineer_temporal_features(df.drop(columns=["Class"]))
    
    scale_cols = [c for c in df_features.columns if "Amount" in c or "Rolling" in c or "Delta" in c]
    pass_cols = [c for c in df_features.columns if c not in scale_cols]
    
    preprocessor = ColumnTransformer([
        ("scaler", RobustScaler(), scale_cols),
        ("pass", "passthrough", pass_cols)
    ])
    
    X_proc = preprocessor.fit_transform(df_features)
    return X_proc, y, preprocessor, df_features.columns.tolist()

def run_optimization(n_trials=20):
    X, y, preprocessor, feature_names = load_processed_data()
    scale_pos_weight = float((y == 0).sum() / (y == 1).sum())
    
    print(f"[2/3] Running Bayesian Optimization ({n_trials} trials, optimizing PR-AUC)...")
    cv = StratifiedKFold(n_splits=4, shuffle=True, random_state=RANDOM_STATE)

    def objective(trial):
        params = {
            "n_estimators": trial.suggest_int("n_estimators", 80, 220),
            "max_depth": trial.suggest_int("max_depth", 3, 7),
            "learning_rate": trial.suggest_float("learning_rate", 0.02, 0.15, log=True),
            "min_child_weight": trial.suggest_int("min_child_weight", 1, 8),
            "subsample": trial.suggest_float("subsample", 0.6, 0.95),
            "colsample_bytree": trial.suggest_float("colsample_bytree", 0.6, 0.95),
            "gamma": trial.suggest_float("gamma", 0.0, 3.0),
            "scale_pos_weight": scale_pos_weight,
            "tree_method": "hist",
            "eval_metric": "logloss",
            "random_state": RANDOM_STATE,
            "n_jobs": -1
        }
        
        pr_aucs = []
        for train_idx, val_idx in cv.split(X, y):
            X_tr, y_tr = X[train_idx], y[train_idx]
            X_va, y_va = X[val_idx], y[val_idx]
            
            clf = XGBClassifier(**params)
            clf.fit(X_tr, y_tr)
            preds = clf.predict_proba(X_va)[:, 1]
            pr_aucs.append(average_precision_score(y_va, preds))
            
        return float(np.mean(pr_aucs))

    study = optuna.create_study(direction="maximize", sampler=optuna.samplers.TPESampler(seed=RANDOM_STATE))
    study.optimize(objective, n_trials=n_trials, show_progress_bar=True)

    print("\n[3/3] Optuna Optimization Complete!")
    print(f"      Best Cross-Validated PR-AUC: {study.best_value:.4f}")
    print("      Best Hyperparameters:")
    for k, v in study.best_params.items():
        print(f"        {k}: {v}")

    best_config = study.best_params
    best_config["scale_pos_weight"] = scale_pos_weight
    best_config["eval_metric"] = "logloss"
    best_config["tree_method"] = "hist"
    best_config["random_state"] = RANDOM_STATE
    best_config["n_jobs"] = -1

    with open(ARTIFACTS_DIR / "best_xgb_params.json", "w") as f:
        json.dump(best_config, f, indent=2)
        
    print(f"\nSaved optimal parameters to {ARTIFACTS_DIR / 'best_xgb_params.json'}")

if __name__ == "__main__":
    run_optimization(n_trials=20)
