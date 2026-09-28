import os
import tempfile
import sqlite3

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


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    j = r.json()
    assert j["status"] == "ok"
    assert j["paper_trading_only"] is True
    assert j["service"] == "equity-research-sim-api"


def test_runs_empty(client):
    r = client.get("/runs")
    assert r.status_code == 200
    assert r.json() == []


def test_create_run(client):
    r = client.post("/runs", json={"ticker": "RELIANCE"})
    assert r.status_code == 200
    j = r.json()
    assert "run_id" in j
    assert j["approval_status"] == "pending"
    assert j["status"] == "awaiting_approval"


def test_create_run_invalid_ticker(client):
    r = client.post("/runs", json={"ticker": "BAD!!"})
    assert r.status_code in (400, 422)


def test_create_run_invalid_capital(client):
    r = client.post("/runs", json={"ticker": "RELIANCE", "initial_capital": -100})
    assert r.status_code in (400, 422)


def test_create_run_invalid_fast_slow(client):
    r = client.post("/runs", json={"ticker": "RELIANCE", "fast_period": 50, "slow_period": 20})
    assert r.status_code == 400


def test_detail_and_audit(client):
    rid = client.post("/runs", json={"ticker": "RELIANCE"}).json()["run_id"]
    r = client.get(f"/runs/{rid}")
    assert r.status_code == 200
    assert r.json()["run_id"] == rid
    a = client.get(f"/runs/{rid}/audit")
    assert a.status_code == 200
    assert len(a.json()) >= 5
    rec = a.json()[0]
    for f in ["id", "run_id", "agent_name", "timestamp", "input_json", "output_json", "human_approval_status"]:
        assert f in rec


def test_backtest_endpoint(client):
    rid = client.post("/runs", json={"ticker": "RELIANCE"}).json()["run_id"]
    r = client.get(f"/runs/{rid}/backtest")
    assert r.status_code == 200
    j = r.json()
    for k in ["ticker", "trade_count", "win_rate", "max_drawdown", "fees_included", "commission_assumption"]:
        assert k in j
    assert j["is_mock"] is False


def test_risk_endpoint(client):
    rid = client.post("/runs", json={"ticker": "RELIANCE"}).json()["run_id"]
    r = client.get(f"/runs/{rid}/risk")
    assert r.status_code == 200
    assert "checks_passed" in r.json()
    assert "risk_warnings" in r.json()


def test_review_not_yet(client):
    rid = client.post("/runs", json={"ticker": "RELIANCE"}).json()["run_id"]
    r = client.get(f"/runs/{rid}/review")
    assert r.status_code == 404


def test_approve_flow(client):
    rid = client.post("/runs", json={"ticker": "RELIANCE"}).json()["run_id"]
    r = client.post(f"/runs/{rid}/approve")
    assert r.status_code == 200
    assert r.json()["approval_status"] == "approved"
    assert r.json()["paper_execution"]["execution_type"] == "PAPER_ONLY"
    rv = client.get(f"/runs/{rid}/review")
    assert rv.status_code == 200
    assert client.post(f"/runs/{rid}/approve").status_code == 409
    assert client.post(f"/runs/{rid}/reject").status_code == 409


def test_reject_flow(client):
    rid = client.post("/runs", json={"ticker": "RELIANCE"}).json()["run_id"]
    r = client.post(f"/runs/{rid}/reject")
    assert r.status_code == 200
    assert r.json()["approval_status"] == "rejected"
    assert client.get(f"/runs/{rid}/review").status_code == 404
    assert client.post(f"/runs/{rid}/approve").status_code == 409
    assert client.post(f"/runs/{rid}/reject").status_code == 409


def test_invalid_run_id(client):
    assert client.get("/runs/invalid!@#").status_code in (400, 404)
    assert client.get("/runs/00000000-0000-0000-0000-000000000000").status_code == 404
    assert client.post("/runs/00000000-0000-0000-0000-000000000000/approve").status_code == 404


def test_no_broker_in_code(client):
    import pathlib
    p = pathlib.Path("paper_execution/engine.py").read_text()
    assert "broker" not in p.lower() or "NOT a broker" in p
    q = pathlib.Path("api/main.py").read_text().lower()
    assert "broker" not in q or "broker" in q and "never call a broker" in q
    assert "PAPER_ONLY" in pathlib.Path("paper_execution/engine.py").read_text()


def test_audit_preserves_fields(client):
    rid = client.post("/runs", json={"ticker": "RELIANCE"}).json()["run_id"]
    audit = client.get(f"/runs/{rid}/audit").json()
    for rec in audit:
        assert "human_approval_status" in rec
        assert "approved_by" in rec
        assert "approved_at" in rec
