from __future__ import annotations

import json
import logging
import math
import os
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


def _sanitize(obj: Any) -> Any:
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize(v) for v in obj]
    return obj

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = str(BASE_DIR / "audit.db")

TICKER_RE = re.compile(r"^[A-Za-z0-9._-]{1,20}$")
VALID_EXCHANGES = {"NSE", "BSE"}

ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]

app = FastAPI(title="Equity Research Sim API", version="4.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_db_path() -> str:
    return os.environ.get("AUDIT_DB_PATH", DEFAULT_DB_PATH)


def _ensure_table(db_path: str):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY,
            run_id TEXT,
            agent_name TEXT,
            timestamp TEXT,
            input_json TEXT,
            output_json TEXT,
            human_approval_status TEXT,
            approved_by TEXT,
            approved_at TEXT
        )
    """)
    conn.commit()
    conn.close()


def _parse_json(s: Optional[str]):
    if s is None:
        return None
    try:
        return json.loads(s)
    except Exception:
        return s


def _fetch_records(db_path: str, run_id: str) -> List[Dict[str, Any]]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT * FROM audit_log WHERE run_id=? ORDER BY id ASC", (run_id,))
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def _get_output(records: List[Dict], agent: str) -> Optional[Dict]:
    for r in reversed(records):
        if r["agent_name"] == agent and r["output_json"]:
            p = _parse_json(r["output_json"])
            if isinstance(p, dict):
                return _sanitize(p)
    return None


def _approval_state(records: List[Dict]) -> str:
    for r in reversed(records):
        if r["agent_name"] == "human_approval" and r["human_approval_status"] in ("approved", "rejected", "pending"):
            return r["human_approval_status"]
    has_risk = any(r["agent_name"] == "risk" for r in records)
    has_execution = any(r["agent_name"] == "paper_execution" for r in records)
    if has_execution:
        return "approved"
    if has_risk:
        return "pending"
    return "n/a"


def _pipeline_status(records: List[Dict]) -> str:
    approval = _approval_state(records)
    has_review = any(r["agent_name"] == "review" for r in records)
    has_exec = any(r["agent_name"] == "paper_execution" for r in records)
    if has_review and has_exec:
        return "completed"
    if approval == "rejected":
        return "rejected"
    if approval == "pending":
        return "awaiting_approval"
    if approval == "approved" and not has_exec:
        return "approved"
    agents = {r["agent_name"] for r in records}
    if not agents:
        return "unknown"
    return "running"


class CreateRunRequest(BaseModel):
    ticker: str = Field(..., description="NSE ticker")
    exchange: str = Field(default="NSE")
    initial_capital: Optional[float] = Field(default=None, ge=1)
    commission: Optional[float] = Field(default=None, ge=0, le=5)
    slippage: Optional[float] = Field(default=None, ge=0, le=5)
    fast_period: Optional[int] = Field(default=None, ge=1, le=100)
    slow_period: Optional[int] = Field(default=None, ge=2, le=200)

    @field_validator("ticker")
    @classmethod
    def validate_ticker(cls, v: str):
        v = v.strip().upper()
        if not v:
            raise ValueError("ticker is required")
        if not TICKER_RE.match(v):
            raise ValueError("invalid ticker format")
        if len(v) > 20:
            raise ValueError("ticker too long")
        return v

    @field_validator("exchange")
    @classmethod
    def validate_exchange(cls, v: str):
        v = v.strip().upper()
        if v not in VALID_EXCHANGES:
            raise ValueError("exchange must be NSE or BSE")
        return v


@app.get("/health")
def health():
    return {"status": "ok", "service": "equity-research-sim-api", "paper_trading_only": True}


@app.get("/runs")
def list_runs():
    db_path = get_db_path()
    _ensure_table(db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT run_id, MAX(timestamp) as created_at, MAX(id) as max_id FROM audit_log GROUP BY run_id ORDER BY max_id DESC LIMIT 50")
    groups = cur.fetchall()
    conn.close()
    result = []
    for g in groups:
        run_id = g["run_id"]
        records = _fetch_records(db_path, run_id)
        if not records:
            continue
        first = records[0]
        backtest = _get_output(records, "backtest")
        risk = _get_output(records, "risk")
        review = _get_output(records, "review")
        paper = _get_output(records, "paper_execution")
        ticker = None
        for r in records:
            o = _parse_json(r["output_json"]) if r["output_json"] else None
            if isinstance(o, dict) and o.get("ticker"):
                ticker = o.get("ticker")
                break
        if not ticker:
            ticker = "UNKNOWN"
        result.append({
            "run_id": run_id,
            "ticker": ticker,
            "created_at": g["created_at"],
            "pipeline_status": _pipeline_status(records),
            "approval_status": _approval_state(records),
            "execution_status": paper.get("execution_status") if paper else None,
            "total_return_pct": backtest.get("total_return_pct") if backtest else None,
            "trade_count": backtest.get("trade_count") if backtest else None,
            "checks_passed": risk.get("checks_passed") if risk else None,
        })
    return _sanitize(result)


@app.get("/runs/{run_id}")
def get_run(run_id: str):
    if not re.match(r"^[a-zA-Z0-9_-]{8,64}$", run_id):
        raise HTTPException(status_code=400, detail="invalid run_id format")
    db_path = get_db_path()
    _ensure_table(db_path)
    records = _fetch_records(db_path, run_id)
    if not records:
        raise HTTPException(status_code=404, detail="run not found")
    backtest = _get_output(records, "backtest")
    risk = _get_output(records, "risk")
    paper = _get_output(records, "paper_execution")
    review = _get_output(records, "review")
    ticker = None
    for r in records:
        o = _parse_json(r["output_json"]) if r["output_json"] else None
        if isinstance(o, dict) and o.get("ticker"):
            ticker = o.get("ticker")
            break
    stages = [r["agent_name"] for r in records]
    return _sanitize({
        "run_id": run_id,
        "ticker": ticker or "UNKNOWN",
        "created_at": records[0]["timestamp"],
        "pipeline_status": _pipeline_status(records),
        "approval_status": _approval_state(records),
        "stages_completed": stages,
        "backtest_summary": backtest,
        "risk_summary": risk,
        "paper_execution_summary": paper,
        "review_summary": review,
    })


@app.get("/runs/{run_id}/audit")
def get_audit(run_id: str):
    if not re.match(r"^[a-zA-Z0-9_-]{8,64}$", run_id):
        raise HTTPException(status_code=400, detail="invalid run_id format")
    db_path = get_db_path()
    _ensure_table(db_path)
    records = _fetch_records(db_path, run_id)
    if not records:
        raise HTTPException(status_code=404, detail="run not found")
    out = []
    for r in records:
        out.append({
            "id": r["id"],
            "run_id": r["run_id"],
            "agent_name": r["agent_name"],
            "timestamp": r["timestamp"],
            "input_json": _sanitize(_parse_json(r["input_json"])),
            "output_json": _sanitize(_parse_json(r["output_json"])),
            "human_approval_status": r["human_approval_status"],
            "approved_by": r["approved_by"],
            "approved_at": r["approved_at"],
        })
    return _sanitize(out)


@app.get("/runs/{run_id}/backtest")
def get_backtest(run_id: str):
    if not re.match(r"^[a-zA-Z0-9_-]{8,64}$", run_id):
        raise HTTPException(status_code=400, detail="invalid run_id format")
    db_path = get_db_path()
    _ensure_table(db_path)
    records = _fetch_records(db_path, run_id)
    if not records:
        raise HTTPException(status_code=404, detail="run not found")
    bt = _get_output(records, "backtest")
    if not bt:
        raise HTTPException(status_code=404, detail="backtest not found for run")
    return _sanitize(bt)


@app.get("/runs/{run_id}/risk")
def get_risk(run_id: str):
    if not re.match(r"^[a-zA-Z0-9_-]{8,64}$", run_id):
        raise HTTPException(status_code=400, detail="invalid run_id format")
    db_path = get_db_path()
    _ensure_table(db_path)
    records = _fetch_records(db_path, run_id)
    if not records:
        raise HTTPException(status_code=404, detail="run not found")
    rk = _get_output(records, "risk")
    if not rk:
        raise HTTPException(status_code=404, detail="risk not found for run")
    return rk


@app.get("/runs/{run_id}/review")
def get_review(run_id: str):
    if not re.match(r"^[a-zA-Z0-9_-]{8,64}$", run_id):
        raise HTTPException(status_code=400, detail="invalid run_id format")
    db_path = get_db_path()
    _ensure_table(db_path)
    records = _fetch_records(db_path, run_id)
    if not records:
        raise HTTPException(status_code=404, detail="run not found")
    rv = _get_output(records, "review")
    if not rv:
        raise HTTPException(status_code=404, detail="review not found for run")
    return rv


def _run_until_risk(ticker: str, db_path: str, run_id: str, req: CreateRunRequest):
    import sys
    sys.path.insert(0, str(BASE_DIR))
    from data.fetch import get_all_data
    from agents.nvidia_llm import llm_enabled
    from agents.research_agent import run_research_agent
    from agents.debate_agent import run_debate_agent
    from agents.backtest_agent import run_backtest_agent
    from agents.risk_agent import run_risk_agent

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    ts = datetime.now(timezone.utc).isoformat()

    def log(agent, inp, out, status=None, by=None):
        cur.execute("INSERT INTO audit_log (run_id, agent_name, timestamp, input_json, output_json, human_approval_status, approved_by, approved_at) VALUES (?,?,?,?,?,?,?,?)",
                    (run_id, agent, datetime.now(timezone.utc).isoformat(), json.dumps(inp, default=str) if inp else None, json.dumps(out, default=str) if out else None, status, by, datetime.now(timezone.utc).isoformat() if status == "approved" else None))
        conn.commit()

    market_data = get_all_data(ticker, use_cache=True)
    research_out = run_research_agent(market_data, mock_mode=not llm_enabled())
    log("research", market_data, research_out)

    debate_out = run_debate_agent(research_out, mock_mode=not llm_enabled())
    log("debate", research_out, debate_out)

    ohlc_data = market_data.get("ohlc", {}).get("data", [])
    if req.fast_period or req.slow_period or req.commission is not None or req.slippage is not None or req.initial_capital:
        from backtest_engine import MovingAverageCrossover, BacktestEngine
        import pandas as pd
        df = pd.DataFrame(ohlc_data) if isinstance(ohlc_data, list) and ohlc_data else ohlc_data
        try:
            fp = req.fast_period or 20
            sp = req.slow_period or 50
            comm = req.commission if req.commission is not None else 0.1
            slip = req.slippage if req.slippage is not None else 0.05
            cap = req.initial_capital or 100000.0
            strat = MovingAverageCrossover(fast_period=fp, slow_period=sp)
            eng = BacktestEngine(strategy=strat, commission=comm, slippage=slip, initial_capital=cap)
            if isinstance(df, pd.DataFrame) and not df.empty:
                eng_result = eng.run(df)
                eng_result["generated_at"] = datetime.now(timezone.utc).isoformat()
                eng_result["ticker"] = ticker
                eng_result["resolved_ticker"] = ticker
                eng_result["data_status"] = "success — deterministic backtest completed"
                backtest_out = {
                    "trades": eng_result.get("trades", []),
                    "win_rate": eng_result.get("win_rate"),
                    "avg_win": eng_result.get("avg_win"),
                    "avg_loss": eng_result.get("avg_loss"),
                    "profit_factor": eng_result.get("profit_factor"),
                    "max_drawdown": eng_result.get("max_drawdown"),
                    "fees_included": True,
                    "slippage_included": True,
                    "is_mock": False,
                    "data_status": eng_result.get("data_status"),
                    "ticker": ticker,
                    "resolved_ticker": ticker,
                    "generated_at": eng_result.get("generated_at"),
                    "strategy_type": eng_result.get("strategy_type"),
                    "fast_period": eng_result.get("fast_period"),
                    "slow_period": eng_result.get("slow_period"),
                    "direction": eng_result.get("direction"),
                    "commission_assumption": eng_result.get("commission_assumption"),
                    "slippage_assumption": eng_result.get("slippage_assumption"),
                    "trade_count": eng_result.get("trade_count", 0),
                    "winning_trade_count": eng_result.get("winning_trade_count", 0),
                    "losing_trade_count": eng_result.get("losing_trade_count", 0),
                    "initial_capital": eng_result.get("initial_capital"),
                    "final_equity": eng_result.get("final_equity"),
                    "total_return_pct": eng_result.get("total_return_pct"),
                    "data_start": str(eng_result.get("data_start")),
                    "data_end": str(eng_result.get("data_end")),
                    "number_of_bars": eng_result.get("number_of_bars"),
                    "equity_curve": eng_result.get("equity_curve", []),
                    "drawdown_series": eng_result.get("drawdown_series", []),
                    "bar_dates": eng_result.get("bar_dates", []),
                }
            else:
                backtest_out = run_backtest_agent(debate_out, ohlc_data, ticker)
        except Exception as e:
            backtest_out = run_backtest_agent(debate_out, ohlc_data, ticker)
    else:
        backtest_out = run_backtest_agent(debate_out, ohlc_data, ticker)

    backtest_out = _sanitize(backtest_out)
    log("backtest", debate_out, backtest_out)

    risk_out = _sanitize(run_risk_agent(backtest_out, account_settings={"capital": req.initial_capital or 100000}, proposed_trade={
        "position_size_pct": 10.0,
        "entry_price": market_data.get("ohlc", {}).get("data", [{}])[0].get("Close", 0) if market_data.get("ohlc", {}).get("data") else 0,
        "stop_loss_price": None,
        "loss_pct": 2.0,
    }, run_id=run_id))
    log("risk", backtest_out, risk_out)

    cur.execute("INSERT INTO audit_log (run_id, agent_name, timestamp, input_json, output_json, human_approval_status, approved_by, approved_at) VALUES (?,?,?,?,?,?,?,?)",
                (run_id, "human_approval", datetime.now(timezone.utc).isoformat(), json.dumps(risk_out, default=str), json.dumps({"approval_status": "pending"}), "pending", None, None))
    conn.commit()
    conn.close()
    return backtest_out, risk_out


@app.post("/runs")
def create_run(req: CreateRunRequest):
    if req.fast_period and req.slow_period and req.fast_period >= req.slow_period:
        raise HTTPException(status_code=400, detail="fast_period must be < slow_period")
    if req.initial_capital is not None and req.initial_capital <= 0:
        raise HTTPException(status_code=400, detail="initial_capital must be positive")
    db_path = get_db_path()
    _ensure_table(db_path)
    run_id = str(uuid.uuid4())
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("INSERT INTO audit_log (run_id, agent_name, timestamp, human_approval_status, approved_by, approved_at) VALUES (?,?,?,?,?,?)",
                (run_id, "pipeline_initialization", datetime.now(timezone.utc).isoformat(), "pending", "system", None))
    conn.commit()
    conn.close()
    try:
        _run_until_risk(req.ticker, db_path, run_id, req)
    except Exception as e:
        logger.exception("pipeline failed")
        raise HTTPException(status_code=500, detail=f"pipeline error: {e}")
    return {"run_id": run_id, "ticker": req.ticker, "status": "awaiting_approval", "approval_status": "pending"}


@app.post("/runs/{run_id}/approve")
def approve_run(run_id: str):
    if not re.match(r"^[a-zA-Z0-9_-]{8,64}$", run_id):
        raise HTTPException(status_code=400, detail="invalid run_id format")
    db_path = get_db_path()
    _ensure_table(db_path)
    records = _fetch_records(db_path, run_id)
    if not records:
        raise HTTPException(status_code=404, detail="run not found")
    state = _approval_state(records)
    if state == "approved":
        raise HTTPException(status_code=409, detail="run already approved")
    if state == "rejected":
        raise HTTPException(status_code=409, detail="run already rejected cannot approve")
    if state != "pending":
        raise HTTPException(status_code=409, detail=f"run not awaiting approval (state={state})")
    risk_out = _get_output(records, "risk")
    backtest_out = _get_output(records, "backtest")
    if not risk_out:
        raise HTTPException(status_code=400, detail="risk output missing cannot approve")

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("INSERT INTO audit_log (run_id, agent_name, timestamp, input_json, output_json, human_approval_status, approved_by, approved_at) VALUES (?,?,?,?,?,?,?,?)",
                (run_id, "human_approval", datetime.now(timezone.utc).isoformat(), json.dumps(risk_out, default=str), json.dumps({"approval_status": "approved", "approved_by": "api_user"}), "approved", "api_user", datetime.now(timezone.utc).isoformat()))
    conn.commit()
    conn.close()

    import sys
    sys.path.insert(0, str(BASE_DIR))
    from paper_execution.engine import run_paper_execution
    from agents.review_agent import run_review_agent

    research_out = _get_output(records, "research")
    debate_out = _get_output(records, "debate")
    capital = risk_out.get("account_capital") or 100000
    try:
        paper_result = run_paper_execution(risk_out, {"capital": capital})
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"paper execution failed: {e}")

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("INSERT INTO audit_log (run_id, agent_name, timestamp, input_json, output_json, human_approval_status, approved_by, approved_at) VALUES (?,?,?,?,?,?,?,?)",
                (run_id, "paper_execution", datetime.now(timezone.utc).isoformat(), json.dumps(risk_out, default=str), json.dumps(paper_result, default=str), "n/a", None, None))
    conn.commit()
    conn.close()

    try:
        review_out = run_review_agent(paper_result, backtest_out, risk_out, {"research": research_out, "debate": debate_out})
    except Exception:
        review_out = {"summary": "review failed", "paper_trade_id": paper_result.get("trade_id")}

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("INSERT INTO audit_log (run_id, agent_name, timestamp, input_json, output_json, human_approval_status, approved_by, approved_at) VALUES (?,?,?,?,?,?,?,?)",
                (run_id, "review", datetime.now(timezone.utc).isoformat(), json.dumps(paper_result, default=str), json.dumps(review_out, default=str), "n/a", None, None))
    conn.commit()
    conn.close()

    return {"run_id": run_id, "approval_status": "approved", "pipeline_status": "completed", "paper_execution": paper_result, "review": review_out}


@app.post("/runs/{run_id}/reject")
def reject_run(run_id: str):
    if not re.match(r"^[a-zA-Z0-9_-]{8,64}$", run_id):
        raise HTTPException(status_code=400, detail="invalid run_id format")
    db_path = get_db_path()
    _ensure_table(db_path)
    records = _fetch_records(db_path, run_id)
    if not records:
        raise HTTPException(status_code=404, detail="run not found")
    state = _approval_state(records)
    if state == "rejected":
        raise HTTPException(status_code=409, detail="run already rejected")
    if state == "approved":
        raise HTTPException(status_code=409, detail="run already approved cannot reject")
    if state != "pending":
        raise HTTPException(status_code=409, detail=f"run not awaiting approval (state={state})")
    risk_out = _get_output(records, "risk")
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("INSERT INTO audit_log (run_id, agent_name, timestamp, input_json, output_json, human_approval_status, approved_by, approved_at) VALUES (?,?,?,?,?,?,?,?)",
                (run_id, "human_approval", datetime.now(timezone.utc).isoformat(), json.dumps(risk_out or {}, default=str), json.dumps({"approval_status": "rejected", "approved_by": "api_user"}), "rejected", "api_user", datetime.now(timezone.utc).isoformat()))
    conn.commit()
    conn.close()
    return {"run_id": run_id, "approval_status": "rejected", "pipeline_status": "rejected"}
