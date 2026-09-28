"""
Regression tests for truthful failed-run state and approval gating.

Covers: pipeline_status "failed" on create_run failure, approval gate
rejections, canonical run_id preservation, and unchanged healthy behavior.
Temp databases + mocks only — no live market data, no NVIDIA, no network.
"""
import os
import sys
import sqlite3
import tempfile
import uuid

sys.path.insert(0, str(__file__).rsplit("\\", 2)[0])

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    db = tempfile.mktemp(suffix=".db")
    os.environ["AUDIT_DB_PATH"] = db
    from api.main import app
    c = TestClient(app)
    yield c
    try:
        os.remove(db)
    except Exception:
        pass
    os.environ.pop("AUDIT_DB_PATH", None)


@pytest.fixture
def failed_run(client, monkeypatch):
    import api.main as api_main

    def boom(*args, **kwargs):
        raise RuntimeError("simulated stage failure")

    monkeypatch.setattr(api_main, "_run_until_risk", boom)
    r = client.post("/runs", json={"ticker": "RELIANCE"})
    assert r.status_code == 500
    assert "pipeline error" in r.json()["detail"]
    runs = client.get("/runs").json()
    assert len(runs) == 1
    return runs[0]["run_id"]


def test_failed_pipeline_reports_failed_status(client, failed_run):
    runs = client.get("/runs").json()
    assert runs[0]["run_id"] == failed_run
    assert runs[0]["pipeline_status"] == "failed"
    assert runs[0]["pipeline_status"] != "awaiting_approval"

    detail = client.get(f"/runs/{failed_run}")
    assert detail.status_code == 200
    j = detail.json()
    assert j["run_id"] == failed_run
    assert j["pipeline_status"] == "failed"
    assert j["approval_status"] != "approved"


def test_failed_run_cannot_be_approved(client, failed_run):
    r = client.post(f"/runs/{failed_run}/approve")
    assert r.status_code == 400
    assert "pipeline failed" in r.json()["detail"]


def test_failed_run_preserves_run_id_and_audit(client, failed_run):
    audit = client.get(f"/runs/{failed_run}/audit")
    assert audit.status_code == 200
    records = audit.json()
    names = [a["agent_name"] for a in records]
    assert "pipeline_initialization" in names
    assert "pipeline_error" in names
    for agent in ("research", "debate", "backtest", "risk"):
        assert agent not in names

    err = next(a for a in records if a["agent_name"] == "pipeline_error")
    assert err["run_id"] == failed_run
    assert "simulated stage failure" in err["output_json"]["error"]
    assert err["human_approval_status"] is None

    assert client.get(f"/runs/{failed_run}").json()["run_id"] == failed_run


def test_healthy_run_still_awaiting_approval(client):
    r = client.post("/runs", json={"ticker": "RELIANCE"})
    assert r.status_code == 200
    assert r.json()["status"] == "awaiting_approval"
    rid = r.json()["run_id"]

    detail = client.get(f"/runs/{rid}").json()
    assert detail["pipeline_status"] == "awaiting_approval"
    assert detail["approval_status"] == "pending"

    listing = client.get("/runs").json()
    entry = next(x for x in listing if x["run_id"] == rid)
    assert entry["pipeline_status"] == "awaiting_approval"


def test_run_without_risk_output_cannot_be_approved(client):
    from api.main import get_db_path, _ensure_table

    db_path = get_db_path()
    _ensure_table(db_path)
    rid = str(uuid.uuid4())
    ts = "2026-09-29T00:00:00+00:00"
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO audit_log (run_id, agent_name, timestamp, human_approval_status, approved_by, approved_at) VALUES (?,?,?,?,?,?)",
        (rid, "pipeline_initialization", ts, "pending", "system", None),
    )
    cur.execute(
        "INSERT INTO audit_log (run_id, agent_name, timestamp, input_json, output_json, human_approval_status, approved_by, approved_at) VALUES (?,?,?,?,?,?,?,?)",
        (rid, "human_approval", ts, None, '{"approval_status": "pending"}', "pending", None, None),
    )
    conn.commit()
    conn.close()

    r = client.post(f"/runs/{rid}/approve")
    assert r.status_code == 400
    assert "risk output missing" in r.json()["detail"]


def test_successful_approval_and_rejection_unchanged(client):
    rid_a = client.post("/runs", json={"ticker": "RELIANCE"}).json()["run_id"]
    ok = client.post(f"/runs/{rid_a}/approve")
    assert ok.status_code == 200
    assert ok.json()["approval_status"] == "approved"
    assert ok.json()["pipeline_status"] == "completed"
    assert client.post(f"/runs/{rid_a}/approve").status_code == 409
    assert client.post(f"/runs/{rid_a}/reject").status_code == 409

    rid_b = client.post("/runs", json={"ticker": "RELIANCE"}).json()["run_id"]
    rj = client.post(f"/runs/{rid_b}/reject")
    assert rj.status_code == 200
    assert rj.json()["approval_status"] == "rejected"
    assert client.post(f"/runs/{rid_b}/approve").status_code == 409
