import numpy as np
import pandas as pd

def engineer_temporal_features(df: pd.DataFrame) -> pd.DataFrame:
    df_out = df.copy()
    
    if "Time" in df_out.columns:
        df_out = df_out.sort_values("Time").reset_index(drop=True)
        time_series = df_out["Time"]
        
        # 1. Inter-transaction time delta (seconds)
        df_out["Delta_Time"] = time_series.diff().fillna(0.0)
        
        # 2. Cyclical daily hour encoding
        hour = (time_series / 3600.0) % 24
        df_out["Hour_Sin"] = np.sin(2 * np.pi * hour / 24.0)
        df_out["Hour_Cos"] = np.cos(2 * np.pi * hour / 24.0)
        
        # 3. Rolling window aggregations using datetime indexing
        temp_dt = pd.to_datetime(time_series, unit='s', origin='2020-01-01')
        df_temp = pd.DataFrame({
            "Amount": df_out["Amount"],
            "dt": temp_dt
        }).set_index("dt")
        
        roll_15m = df_temp["Amount"].rolling("900s")
        roll_1h = df_temp["Amount"].rolling("3600s")
        roll_24h = df_temp["Amount"].rolling("86400s")
        
        df_out["Rolling_Count_15m"] = roll_15m.count().values
        df_out["Rolling_Count_1h"] = roll_1h.count().values
        df_out["Rolling_Count_24h"] = roll_24h.count().values
        
        df_out["Rolling_Sum_15m"] = roll_15m.sum().values
        df_out["Rolling_Mean_1h"] = roll_1h.mean().values
        df_out["Rolling_Std_1h"] = roll_1h.std().fillna(0.0).values
        
        # 4. Amount anomaly ratio relative to rolling mean
        df_out["Amount_Ratio_1h"] = df_out["Amount"] / (df_out["Rolling_Mean_1h"] + 1.0)
        
        df_out = df_out.drop(columns=["Time"])
        
    return df_out
