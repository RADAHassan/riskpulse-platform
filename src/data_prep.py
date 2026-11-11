import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import RobustScaler
from sklearn.compose import ColumnTransformer

from src.config import DATA_PATH, TEST_SIZE, CAL_SIZE, RANDOM_STATE

def load_and_split_data():
    df = pd.read_csv(DATA_PATH)
    
    # 1. Cyclical time encoding
    hour = (df["Time"] / 3600.0) % 24
    df["Hour_Sin"] = np.sin(2 * np.pi * hour / 24.0)
    df["Hour_Cos"] = np.cos(2 * np.pi * hour / 24.0)
    
    X = df.drop(columns=["Time", "Class"])
    y = df["Class"].astype(int).to_numpy()
    
    # 2. 70/15/15 Stratified Split
    X_train_val, X_test, y_train_val, y_test = train_test_split(
        X, y, test_size=TEST_SIZE, stratify=y, random_state=RANDOM_STATE
    )
    
    X_train, X_cal, y_train, y_cal = train_test_split(
        X_train_val, y_train_val, test_size=CAL_SIZE, stratify=y_train_val, random_state=RANDOM_STATE
    )
    
    # 3. Leakage-free preprocessing fitted strictly on Train
    preprocessor = ColumnTransformer(
        transformers=[
            ("scaler", RobustScaler(), ["Amount"]),
            ("pass", "passthrough", [c for c in X.columns if c != "Amount"])
        ]
    )
    
    X_train_scaled = preprocessor.fit_transform(X_train)
    X_cal_scaled = preprocessor.transform(X_cal)
    X_test_scaled = preprocessor.transform(X_test)
    
    return {
        "X_train": X_train_scaled,
        "y_train": y_train,
        "X_cal": X_cal_scaled,
        "y_cal": y_cal,
        "X_test": X_test_scaled,
        "y_test": y_test,
        "preprocessor": preprocessor,
        "feature_names": [c for c in X.columns]
    }
