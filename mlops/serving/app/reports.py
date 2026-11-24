"""Read-only views over the ML artifacts (ml/artifacts, ml/figures) for the dashboard."""

from __future__ import annotations

import csv
import json
from functools import lru_cache
from pathlib import Path

FIGURES = {
    "reliability": ("figures_dir", "fig_reliability.png"),
    "pr_curves": ("figures_dir", "fig_pr_curves.png"),
    "latent": ("artifacts_dir", "figures/pca_tsne_umap.png"),
}


def _read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as fh:
        rows = []
        for row in csv.DictReader(fh):
            parsed = {}
            for key, value in row.items():
                try:
                    parsed[key] = float(value)
                except (TypeError, ValueError):
                    parsed[key] = value
            rows.append(parsed)
        return rows


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def figures_dir(artifacts_dir: Path) -> Path:
    return artifacts_dir.parent / "figures"


@lru_cache(maxsize=4)
def build_report(artifacts_dir: Path) -> dict:
    conformal = _read_json(artifacts_dir / "conformal.json")
    benchmark = _read_csv(artifacts_dir / "benchmark_results.csv")
    calibration = [
        {
            "model": row.get("Model"),
            "brier_raw": row.get("Brier_Raw"),
            "brier_calibrated": row.get("Brier_Calibrated"),
        }
        for row in benchmark
    ]
    return {
        "benchmark": benchmark,
        "statistical_tests": _read_csv(artifacts_dir / "statistical_tests.csv"),
        "friedman": _read_json(artifacts_dir / "friedman_summary.json"),
        "statistical_summary": _read_json(artifacts_dir / "statistical_summary.json"),
        "calibration": calibration,
        "conformal": {k: v for k, v in conformal.items() if k != "windows"},
        "conformal_windows": conformal.get("windows", []),
        "figures": sorted(FIGURES),
    }


@lru_cache(maxsize=2)
def projections(artifacts_dir: Path) -> dict:
    return _read_json(artifacts_dir / "latent_projections.json")


def figure_path(name: str, artifacts_dir: Path) -> Path | None:
    entry = FIGURES.get(name)
    if entry is None:
        return None
    base = figures_dir(artifacts_dir) if entry[0] == "figures_dir" else artifacts_dir
    path = base / entry[1]
    return path if path.exists() else None
