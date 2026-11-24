"""Generate ``ml/artifacts/demo_transactions.csv`` for the simulator and the k6 load tests.

If ``ml/data/creditcard.csv`` (ULB dataset) is present, ~2000 rows of the chronological test tail (with all
frauds it contains) are extracted. Otherwise **synthetic** payloads are generated (documented in
CLAUDE.md "À faire par Hassan"): legit rows ~ N(0, sigma_i); fraud-like rows are blended between the
legit and the (approximate, literature) fraud class means with a random difficulty so that the model
produces a realistic mix of APPROVE / HUMAN_REVIEW / DECLINE.

Usage: python scripts/generate_demo_transactions.py [--rows 2000] [--seed 42]
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "ml" / "data" / "creditcard.csv"
OUT = ROOT / "ml" / "artifacts" / "demo_transactions.csv"
COLS = ["amount"] + [f"v{i}" for i in range(1, 29)] + ["is_fraud"]

SIGMA = np.array([1.96, 1.65, 1.52, 1.42, 1.38, 1.33, 1.24, 1.19, 1.10, 1.09, 1.02, 1.00, 1.00, 0.96,
                  0.92, 0.88, 0.85, 0.84, 0.81, 0.77, 0.73, 0.73, 0.62, 0.61, 0.52, 0.48, 0.40, 0.33])
FRAUD_MEAN = np.array([-4.77, 3.62, -7.03, 4.54, -3.15, -1.40, -5.57, 0.57, -2.58, -5.68, 3.80, -6.26, -0.11,
                       -6.97, -0.09, -4.14, -6.67, -2.24, 0.68, 0.37, 0.71, 0.01, -0.04, -0.10, 0.04, 0.05,
                       0.17, 0.08])


def from_dataset(rows: int, seed: int) -> pd.DataFrame:
    df = pd.read_csv(DATA)
    df = df.drop_duplicates().reset_index(drop=True)
    tail = df.iloc[int(len(df) * 0.9):]
    frauds = tail[tail["Class"] == 1]
    legit = tail[tail["Class"] == 0].sample(n=max(rows - len(frauds), 0), random_state=seed)
    sel = pd.concat([frauds, legit]).sample(frac=1.0, random_state=seed)
    out = pd.DataFrame({"amount": sel["Amount"].round(2)})
    for i in range(1, 29):
        out[f"v{i}"] = sel[f"V{i}"].round(6).values
    out["is_fraud"] = sel["Class"].astype(int).values
    return out[COLS]


def synthetic(rows: int, seed: int, fraud_ratio: float = 0.08) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    n_fraud = int(rows * fraud_ratio)
    n_legit = rows - n_fraud

    legit = rng.normal(0.0, SIGMA, size=(n_legit, 28))
    legit_amt = np.clip(rng.lognormal(mean=3.4, sigma=1.3, size=n_legit), 0.5, 5000)

    # difficulty alpha in [0.15, 1]: 1 = typical fraud, lower = ambiguous (-> uncertain predictions)
    alpha = rng.uniform(0.15, 1.0, size=(n_fraud, 1))
    fraud = rng.normal(0.0, SIGMA * 0.9, size=(n_fraud, 28)) + alpha * FRAUD_MEAN
    fraud_amt = np.clip(rng.lognormal(mean=3.9, sigma=1.5, size=n_fraud), 1.0, 5000)

    x = np.vstack([legit, fraud])
    amt = np.concatenate([legit_amt, fraud_amt])
    label = np.concatenate([np.zeros(n_legit, int), np.ones(n_fraud, int)])
    idx = rng.permutation(len(label))
    out = pd.DataFrame(np.round(x[idx], 6), columns=[f"v{i}" for i in range(1, 29)])
    out.insert(0, "amount", np.round(amt[idx], 2))
    out["is_fraud"] = label[idx]
    return out[COLS]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows", type=int, default=2000)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()
    if DATA.exists():
        df, kind = from_dataset(args.rows, args.seed), "ULB test tail"
    else:
        df, kind = synthetic(args.rows, args.seed), "SYNTHETIC (ml/data/creditcard.csv absent)"
    OUT.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT, index=False)
    print(f"wrote {OUT} rows={len(df)} fraud_rows={int(df.is_fraud.sum())} source={kind}")


if __name__ == "__main__":
    main()
