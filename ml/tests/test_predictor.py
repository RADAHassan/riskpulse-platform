"""Regression tests for the production predictor and its pickled bundle.

The 29D bundle pickles ``src.models.autoencoder`` objects and needs ``torch``; these tests make sure a
fresh clone (``pip install -r requirements.txt``) can load and score.
"""

from __future__ import annotations

import math

import pytest

from src.ml.predictor import RiskPulseMLPredictor

DECISIONS = {"APPROVE", "MANUAL_REVIEW", "AUTO_DECLINE"}


@pytest.fixture(scope="module")
def predictor() -> RiskPulseMLPredictor:
    return RiskPulseMLPredictor()


def test_bundle_loads_and_exposes_version(predictor):
    assert predictor.version == "riskpulse-29d-v2.0-canonical"


def test_autoencoder_module_is_importable():
    from src.models.autoencoder import AutoencoderFeatureExtractor, TabularAutoencoder

    assert TabularAutoencoder and AutoencoderFeatureExtractor


def test_score_transaction_contract(predictor):
    out = predictor.score_transaction(149.99, [0.0] * 28)
    assert out["model_version"] == predictor.version
    assert out["decision"] in DECISIONS
    assert 0.0 <= out["calibrated_probability"] <= 1.0
    assert 0.0 <= out["uncertainty_score"] <= 1.0
    assert set(out["conformal_set"]) <= {"LEGIT", "FRAUD"}
    assert math.isfinite(out["ae_recon_mse"])
    assert isinstance(out["human_review"], bool)


def test_uncertainty_is_derived_from_probability(predictor):
    out = predictor.score_transaction(10.0, [0.1] * 28)
    p = out["calibrated_probability"]
    assert out["uncertainty_score"] == pytest.approx(round(2 * min(p, 1 - p), 6))


def test_uncertain_prediction_is_never_auto_declined(predictor):
    """Core platform invariant: high uncertainty must not trigger an automatic decline."""
    fraud_like = [-3.0, 2.5, -4.0, 3.5, -2.0, -1.0, -3.0, 0.5, -2.0, -5.0, 3.0, -6.0, 0.0, -7.0,
                  0.0, -4.0, -6.0, -2.0, 1.0, 0.5, 0.5, 0.0, 0.0, 0.0, 0.0, 0.0, 0.5, 0.2]
    for amount in (1.0, 99.0, 1200.0):
        out = predictor.score_transaction(amount, fraud_like)
        if out["uncertainty_score"] >= predictor.uncertainty_review_threshold:
            assert out["decision"] != "AUTO_DECLINE"


def test_conformal_quantiles_loaded_from_artifact(predictor):
    assert predictor.q_legit == pytest.approx(0.23462)
    assert predictor.q_fraud == pytest.approx(0.95251)
