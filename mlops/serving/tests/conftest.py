import os

os.environ.setdefault("SERVICE_KEY", "test-service-key-0123456789")
os.environ.setdefault("MLFLOW_TRACKING_URI", "")

import pytest
from app.config import get_settings
from fastapi.testclient import TestClient

KEY = {"X-Service-Key": os.environ["SERVICE_KEY"]}


@pytest.fixture(scope="session")
def client():
    from app.main import app

    get_settings.cache_clear()
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def headers():
    return dict(KEY)


@pytest.fixture()
def legit_payload():
    return {"transaction_id": "t-1", "amount": 42.5, "features": [0.0] * 28}


@pytest.fixture()
def fraud_like_payload():
    feats = [-3.0, 2.5, -4.0, 3.5, -2.0, -1.0, -3.0, 0.5, -2.0, -5.0, 3.0, -6.0, 0.0, -7.0,
             0.0, -4.0, -6.0, -2.0, 1.0, 0.5, 0.5, 0.0, 0.0, 0.0, 0.0, 0.0, 0.5, 0.2]
    return {"transaction_id": "t-fraud", "amount": 310.0, "features": feats}
