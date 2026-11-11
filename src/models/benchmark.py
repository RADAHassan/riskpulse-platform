import time
import joblib
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier
from sklearn.svm import SVC
from sklearn.neural_network import MLPClassifier
from xgboost import XGBClassifier

from sklearn.metrics import (
    accuracy_score, precision_score, recall_score,
    f1_score, roc_auc_score, average_precision_score,
    matthews_corrcoef, brier_score_loss
)

def run_benchmark():
    print("[1/3] Chargement intégral des données en mémoire vive (RAM)...")
    data = np.load("artifacts/data_splits.npz")
    X_train, y_train = data["X_train"], data["y_train"]
    X_test, y_test = data["X_test"], data["y_test"]
    scale_pos_weight = float(data["scale_pos_weight"])

    print(f"      Taille mémoire du Train Set: {X_train.nbytes / (1024**2):.2f} Mo")
    print(f"      Nombre total d'exemples d'entraînement: {len(X_train)}")

    # Configuration exploitant le CPU multi-cœur et la RAM disponible
    models = {
        "Logistic Regression": LogisticRegression(
            class_weight="balanced", 
            max_iter=1000, 
            n_jobs=-1,
            random_state=42
        ),
        "Random Forest": RandomForestClassifier(
            n_estimators=100, 
            class_weight="balanced", 
            n_jobs=-1, 
            random_state=42
        ),
        "XGBoost": XGBClassifier(
            n_estimators=150, 
            scale_pos_weight=scale_pos_weight, 
            eval_metric="logloss", 
            n_jobs=-1, 
            tree_method="hist",  # Utilise la construction d'histogrammes en RAM pour une vitesse maximale
            random_state=42
        ),
        "SVM (RBF)": SVC(
            kernel="rbf", 
            class_weight="balanced", 
            probability=True, 
            cache_size=8000,     # Alloue 8 Go de cache RAM dédié au calcul du noyau RBF
            random_state=42
        ),
        "MLP": MLPClassifier(
            hidden_layer_sizes=(64, 32), 
            max_iter=200, 
            early_stopping=True, 
            random_state=42
        )
    }

    results = []

    print("\n[2/3] Démarrage du benchmarking sur 100% des données...")
    for name, model in models.items():
        print(f"\n--> Entraînement : {name} sur les {len(X_train)} transactions...")
        t_start = time.time()
        
        # Entraînement complet sans sous-échantillonnage
        model.fit(X_train, y_train)
            
        train_time = time.time() - t_start
        print(f"    Terminé avec succès en {train_time:.1f} s")

        # Mesure de la latence d'inférence unitaire sur 500 requêtes
        subset = X_test[:500]
        t0 = time.perf_counter()
        for i in range(len(subset)):
            _ = model.predict(subset[i:i+1])
        avg_latency_ms = ((time.perf_counter() - t0) / len(subset)) * 1000.0

        # Prédictions sur le test set complet
        y_pred = model.predict(X_test)
        y_proba = model.predict_proba(X_test)[:, 1]

        # Calcul complet des métriques
        metrics = {
            "Model": name,
            "Accuracy": accuracy_score(y_test, y_pred),
            "Precision": precision_score(y_test, y_pred, zero_division=0),
            "Recall": recall_score(y_test, y_pred),
            "F1": f1_score(y_test, y_pred),
            "ROC-AUC": roc_auc_score(y_test, y_proba),
            "PR-AUC": average_precision_score(y_test, y_proba),
            "MCC": matthews_corrcoef(y_test, y_pred),
            "Brier Score": brier_score_loss(y_test, y_proba),
            "Latency (ms)": avg_latency_ms
        }
        results.append(metrics)

        # Sérialisation de l'artefact
        clean_name = name.lower().replace(" ", "_").replace("(", "").replace(")", "")
        joblib.dump(model, f"artifacts/model_{clean_name}.joblib")

    # Exportation finale
    df = pd.DataFrame(results)
    df.to_csv("artifacts/benchmark_results.csv", index=False)
    
    print("\n[3/3] Tableau comparatif complet (généré sur 100% du jeu de données) :")
    pd.set_option("display.precision", 4)
    pd.set_option("display.max_columns", None)
    pd.set_option("display.width", 1000)
    print(df.to_string(index=False))

if __name__ == "__main__":
    run_benchmark()
