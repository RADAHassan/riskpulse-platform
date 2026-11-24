import joblib
import numpy as np
import pytest
import xgboost as xgb

from src.ml import bundle_io


@pytest.fixture(scope="module")
def tiny_model():
    rng = np.random.default_rng(0)
    x = rng.random((300, 6))
    y = (x[:, 0] + 0.1 * rng.random(300) > 0.6).astype(int)
    return xgb.XGBClassifier(n_estimators=8, max_depth=3).fit(x, y), x


def test_extract_model_section_roundtrip(tiny_model):
    model, x = tiny_model
    raw = bytes(model.get_booster().__getstate__()["handle"])
    section = bundle_io.extract_model_section(raw)
    booster = xgb.Booster()
    booster.load_model(bytearray(section))
    assert booster.num_boosted_rounds() == 8
    expected = model.get_booster().predict(xgb.DMatrix(x))
    np.testing.assert_allclose(booster.predict(xgb.DMatrix(x)), expected, rtol=0, atol=0)


def test_extract_rejects_garbage():
    with pytest.raises(ValueError):
        bundle_io.extract_model_section(b"not-ubjson")


def test_load_bundle_falls_back_when_config_is_unreadable(tiny_model, tmp_path, monkeypatch):
    model, x = tiny_model
    path = tmp_path / "m.joblib"
    joblib.dump({"clf": model}, path)

    real_load = joblib.load
    calls = {"n": 0}

    def flaky(p):
        calls["n"] += 1
        if calls["n"] == 1:
            raise xgb.core.XGBoostError("input stream corrupted")
        return real_load(p)

    monkeypatch.setattr(bundle_io.joblib, "load", flaky)
    loaded = bundle_io.load_bundle(path)
    assert calls["n"] == 2
    np.testing.assert_allclose(loaded["clf"].predict_proba(x), model.predict_proba(x))


def test_unrelated_errors_are_not_swallowed(monkeypatch, tmp_path):
    monkeypatch.setattr(bundle_io.joblib, "load", lambda p: (_ for _ in ()).throw(FileNotFoundError("nope")))
    with pytest.raises(FileNotFoundError):
        bundle_io.load_bundle(tmp_path / "missing.joblib")
