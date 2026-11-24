import pytest
from app import model_store
from app.config import Settings
from app.decision import to_platform_decision


def res(decision, unc=0.0, cset=("FRAUD",), human=False, reason="none"):
    return {
        "decision": decision,
        "uncertainty_score": unc,
        "conformal_set": list(cset),
        "human_review": human,
        "review_reason": reason,
    }


def test_confident_fraud_is_declined():
    assert to_platform_decision(res("AUTO_DECLINE", 0.02))[0] == "DECLINE"


@pytest.mark.parametrize("unc,cset", [(0.4, ("FRAUD",)), (0.02, ("LEGIT", "FRAUD")), (0.02, ("LEGIT",)), (0.02, ())])
def test_uncertain_never_declined(unc, cset):
    decision, reason = to_platform_decision(res("AUTO_DECLINE", unc, cset))
    assert decision == "HUMAN_REVIEW"
    assert reason == "uncertain_prediction_not_auto_declined"


def test_manual_review_maps_to_human_review():
    assert to_platform_decision(res("MANUAL_REVIEW", 0.5, ("LEGIT", "FRAUD")))[0] == "HUMAN_REVIEW"


def test_router_flag_promotes_approve_to_review():
    assert to_platform_decision(res("APPROVE", 0.1, ("LEGIT",), human=True, reason="top_0.5pct_raw_score")) == (
        "HUMAN_REVIEW",
        "top_0.5pct_raw_score",
    )


def test_low_risk_is_approved():
    assert to_platform_decision(res("APPROVE", 0.0, ("LEGIT",)))[0] == "APPROVE"


def test_parse_model_uri():
    assert model_store._parse_model_uri("models:/riskpulse-fraud@champion") == ("riskpulse-fraud", "champion", None)
    assert model_store._parse_model_uri("models:/riskpulse-fraud/3") == ("riskpulse-fraud", None, "3")


def test_mlflow_failure_falls_back_to_local_bundle(monkeypatch):
    def boom(_settings):
        raise ConnectionError("registry down")

    monkeypatch.setattr(model_store, "_load_from_mlflow", boom)
    loaded = model_store.load_model(Settings(mlflow_tracking_uri="http://127.0.0.1:9", service_key="k"))
    assert loaded.source == "local-bundle"
    assert loaded.registry_version is None
