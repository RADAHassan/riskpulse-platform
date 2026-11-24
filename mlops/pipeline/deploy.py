"""Stage 5 — Deployment: ask ml-serving to reload the ``champion`` alias and verify it serves that version.

Set ``SERVING_URL`` (e.g. http://localhost:8000) and ``SERVICE_KEY``. Without ``SERVING_URL`` the stage is
recorded as skipped (the serving pods pick the alias up at their next start / ``POST /model/reload``).
"""

from __future__ import annotations

import json
import os
import urllib.request

import mlflow
from common import CHAMPION_ALIAS, Context, start_stage


def _call(method: str, url: str, key: str) -> dict:
    req = urllib.request.Request(url, method=method, headers={"X-Service-Key": key})  # noqa: S310
    with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310 - internal service URL
        return json.loads(resp.read())


def run(ctx: Context) -> Context:
    url = os.environ.get("SERVING_URL", "").rstrip("/")
    key = os.environ.get("SERVICE_KEY", "")
    with start_stage("deployment", ctx):
        if ctx.alias != CHAMPION_ALIAS:
            mlflow.set_tag("deployment", "skipped: candidate is not champion (validation gates failed)")
            print("Deployment skipped: candidate is not champion")
            return ctx
        if not url:
            mlflow.set_tag("deployment", "skipped: SERVING_URL not set")
            print("Deployment skipped: SERVING_URL not set")
            return ctx
        info = _call("POST", f"{url}/model/reload", key)
        served = info.get("registry_version")
        ok = served == ctx.model_version and info.get("model_source") == "mlflow"
        mlflow.set_tag("deployment", "ok" if ok else "mismatch")
        mlflow.log_param("served_registry_version", served)
        mlflow.log_param("served_model_version", info.get("model_version"))
        if not ok:
            raise SystemExit(f"ml-serving serves registry version {served!r}, expected {ctx.model_version!r}")
        ctx.deployed = True
        print(f"ml-serving now serves {info['model_version']} (registry v{served})")
    return ctx


if __name__ == "__main__":
    c = Context.load()
    run(c)
    c.save()
