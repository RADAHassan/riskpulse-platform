#!/usr/bin/env bash
set -e

# Ensure current working directory is included in Python module search path
export PYTHONPATH=.

echo "=== [1/4] Running Master Training & Isotonic Calibration Pipeline ==="
python src/run_pipeline.py

echo "=== [2/4] Running Operational Routing Parameter Sweep ==="
python src/models/run_uncertainty_sweep.py

echo "=== [3/4] Running Bootstrap Statistical Validation ==="
python src/stats/statistical_validation.py

echo "=== [4/4] Generating Latent Visualizations & Cluster Diagnostics ==="
python src/visualization.py
python src/stats/cluster_diagnostics.py

echo "=========================================================="
echo " All tasks executed successfully. Deliverables are ready! "
echo "=========================================================="
