"""
Orchestrator — sequential 5-agent pipeline with human approval gate.

Flow:
    research
  → debate
  → backtest
  → risk
  → HUMAN APPROVAL GATE (hard stop)
  → paper execution
  → review

Every agent call generates an audit record. The pipeline pauses at the
risk agent output and requires explicit human approval before proceeding
to paper execution. Rejection terminates the pipeline safely.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from data.fetch import get_all_data
from agents.nvidia_llm import llm_enabled
from agents.research_agent import run_research_agent, validate_research_output
from agents.debate_agent import run_debate_agent, validate_debate_output
from agents.backtest_agent import run_backtest_agent, validate_backtest_output
from agents.risk_agent import run_risk_agent, validate_risk_output
from agents.review_agent import run_review_agent, validate_review_output
from backtest_engine.runner import run_backtest_from_data

logger = logging.getLogger(__name__)

# Pipeline approval statuses (SQLite-compatible)
APPROVAL_PENDING = "pending"
APPROVAL_APPROVED = "approved"
APPROVAL_REJECTED = "rejected"
APPROVAL_N_A = "n/a"

# Accepted affirmative approval inputs
AFFIRMATIVE_INPUTS = {"y", "yes"}

# Minimum required fields for each agent output
MIN_REQUIRED_FIELDS = {
    "research": ["trend", "key_levels", "relevant_news_summary", "data_sources_used",
                 "ticker", "resolved_ticker", "generated_at", "data_quality", "data_warnings"],
    "debate": ["bull_case", "bear_case", "failure_conditions", "no_trade_conditions",
               "biases_flagged", "data_sources_used", "ticker", "resolved_ticker", "generated_at"],
    "backtest": ["trades", "win_rate", "avg_win", "avg_loss", "profit_factor",
                 "max_drawdown", "fees_included", "slippage_included", "is_mock", "data_status",
                 "ticker", "resolved_ticker", "generated_at"],
    "risk": ["run_id", "ticker", "resolved_ticker", "simulation_disclaimer",
             "checks_passed", "sebi_aligned_controls", "risk_warnings",
                 "position_size", "stop_loss", "exposure_limit", "daily_loss_limit"],
    "review": [],  # Review output schema validated separately
    "paper_execution": ["trade_id", "run_id", "ticker", "simulation", "execution_status"],
}


def _initialize_audit_database(db_path: str = "audit.db") -> str:
    """
    Initialize the SQLite audit database.

    Args:
        db_path: Path to SQLite database file

    Returns:
        The run_id that was generated at the start of the pipeline
    """
    run_id = str(uuid.uuid4())
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
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
    logger.info(f"Audit database initialized: {db_path}, run_id: {run_id}")
    return run_id


def _log_agent_call(
    conn: sqlite3.Connection,
    run_id: str,
    agent_name: str,
    input_data: Optional[Dict[str, Any]],
    output_data: Optional[Dict[str, Any]],
    human_approval_status: Optional[str] = None,
    approved_by: Optional[str] = None,
    approved_at: Optional[str] = None,
) -> None:
    """
    Log an agent call to the audit database.

    Args:
        conn: SQLite connection
        run_id: Unique pipeline run identifier
        agent_name: Name of the agent
        input_data: Input JSON (dict) or None
        output_data: Output JSON (dict) or None
        human_approval_status: 'pending' | 'approved' | 'rejected' | 'n/a'
        approved_by: Name or ID of the approver
        approved_at: ISO timestamp of approval
    """
    cursor = conn.cursor()
    timestamp = datetime.now(timezone.utc).isoformat()

    # Serialize input/output to JSON safely (handle non-serializable types)
    input_json = json.dumps(input_data, default=str) if input_data is not None else None
    output_json = json.dumps(output_data, default=str) if output_data is not None else None

    cursor.execute("""
        INSERT INTO audit_log
        (run_id, agent_name, timestamp, input_json, output_json,
         human_approval_status, approved_by, approved_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        run_id,
        agent_name,
        timestamp,
        input_json,
        output_json,
        human_approval_status,
        approved_by,
        approved_at,
    ))

    conn.commit()


def _get_human_approval(risk_output: Dict[str, Any]) -> Dict[str, str]:
    """
    Get human approval at the CLI hard stop.

    Args:
        risk_output: Risk Agent's output dictionary

    Returns:
        Dictionary with approval decision and actor
    """
    # Display clear CLI summary
    print("\n" + "=" * 60)
    print("HUMAN APPROVAL REQUIRED")
    print("=" * 60)
    print(f"Run ID: {risk_output.get('run_id', 'N/A')}")
    print(f"Ticker: {risk_output.get('ticker', 'N/A')}")
    print()
    print("Risk assessment:")
    print(f"  Position size: {risk_output.get('position_size', 'N/A')}%")
    print(f"  Stop loss: {risk_output.get('stop_loss', 'N/A')}")
    print(f"  Exposure limit: {risk_output.get('exposure_limit', 'N/A')}%")
    print(f"  Daily loss limit: {risk_output.get('daily_loss_limit', 'N/A')}%")
    print(f"  Checks passed: {risk_output.get('checks_passed', False)}")
    print(f"  Warnings: {len(risk_output.get('risk_warnings', []))} active")
    print()
    print("Approved paper trade? [y/N]: ", end="", flush=True)

    try:
        user_input = input().strip().lower()
    except (EOFError, KeyboardInterrupt):
        # No input available (e.g., pytest capture environment) — treat as rejection
        user_input = "n"

    approval_status = APPROVAL_REJECTED
    approved_by = "cli_user"

    if user_input in AFFIRMATIVE_INPUTS:
        approval_status = APPROVAL_APPROVED
        approved_by = "cli_user"
        logger.info(f"Human approval granted for run {risk_output.get('run_id', 'N/A')}")
    else:
        approval_status = APPROVAL_REJECTED
        approved_by = "cli_user"
        logger.info(f"Human approval rejected for run {risk_output.get('run_id', 'N/A')}")

    return {
        "approval_status": approval_status,
        "approved_by": approved_by,
    }


def _validate_agent_output(output: Dict[str, Any], agent_type: str) -> bool:
    """
    Validate agent output conforms to the minimum required schema.

    Args:
        output: Agent output dictionary
        agent_type: Type of agent ('research', 'debate', 'backtest', 'risk', 'review')

    Returns:
        True if valid, False otherwise
    """
    required = MIN_REQUIRED_FIELDS.get(agent_type, [])
    if not required:
        logger.warning(f"Unknown agent type: {agent_type}")
        return True

    for field in required:
        if field not in output:
            logger.error(f"[{agent_type}] Missing required field: {field}")
            return False
    return True


def run_pipeline(
    ticker: str = "RELIANCE",
    db_path: str = "audit.db",
    use_mock_backtest: bool = False,
    use_mock_research: Optional[bool] = None,
    use_mock_debate: Optional[bool] = None,
    skip_approval: bool = False,
) -> Dict[str, Any]:
    """
    Run the complete 5-agent pipeline with human approval gate.

    Args:
        ticker: Stock ticker to analyze
        db_path: Path to SQLite audit database
        use_mock_backtest: If True, use mock backtest data (Phase 2 legacy).
        use_mock_research: Research mock control. None = auto
            (mock unless NVIDIA_API_KEY is configured; always mock under pytest).
        use_mock_debate: Debate mock control with the same auto semantics.
        skip_approval: Auto-approve for testing/non-CLI environments.

    Returns:
        Final pipeline report dictionary
    """
    # Resolve LLM mode: explicit caller choice wins, otherwise use NVIDIA config
    mock_research = use_mock_research if use_mock_research is not None else (not llm_enabled())
    mock_debate = use_mock_debate if use_mock_debate is not None else (not llm_enabled())
    # Initialize audit database and generate run_id
    run_id = _initialize_audit_database(db_path)

    # Connect to audit database
    conn = sqlite3.connect(db_path)

    report = {
        "run_id": run_id,
        "ticker": ticker,
        "stages_completed": [],
        "approval_status": APPROVAL_REJECTED,
        "paper_execution": None,
        "final_review": None,
        "termination_reason": "",
        "initial_capital": None,
        "final_equity": None,
        "total_return_pct": None,
        "trade_count": None,
        "win_rate": None,
        "avg_win": None,
        "avg_loss": None,
        "profit_factor": None,
        "max_drawdown": None,
        "fees_included": None,
        "commission_assumption": None,
        "slippage_included": None,
        "slippage_assumption": None,
        "is_mock": None,
        "data_status": None,
        "data_start": None,
        "data_end": None,
        "number_of_bars": None,
    }

    try:
        # ============================================
        # Stage 1: Research Agent
        # ============================================
        logger.info(f"Stage 1: Research Agent for {ticker}")
        market_data = get_all_data(ticker, use_cache=True)

        research_out = run_research_agent(market_data, mock_mode=mock_research)

        if not _validate_agent_output(research_out, "research"):
            raise RuntimeError("Research Agent output failed validation")

        _log_agent_call(conn, run_id, "research", market_data, research_out)
        report["stages_completed"].append("research")

        # ============================================
        # Stage 2: Debate Agent
        # ============================================
        logger.info("Stage 2: Debate Agent")
        debate_out = run_debate_agent(research_out, mock_mode=mock_debate)

        if not _validate_agent_output(debate_out, "debate"):
            raise RuntimeError("Debate Agent output failed validation")

        _log_agent_call(conn, run_id, "debate", research_out, debate_out)
        report["stages_completed"].append("debate")

        # ============================================
        # Stage 3: Backtest Agent
        # ============================================
        logger.info("Stage 3: Backtest Agent")
        backtest_out = run_backtest_agent(debate_out, market_data.get("ohlc", {}).get("data", []), ticker)

        if not _validate_agent_output(backtest_out, "backtest"):
            raise RuntimeError("Backtest Agent output failed validation")

        _log_agent_call(conn, run_id, "backtest", debate_out, backtest_out)
        report["stages_completed"].append("backtest")

        for key in ["initial_capital","final_equity","total_return_pct","trade_count","win_rate","avg_win","avg_loss","profit_factor","max_drawdown","fees_included","commission_assumption","slippage_included","slippage_assumption","is_mock","data_status","data_start","data_end","number_of_bars","equity_curve","drawdown_series","bar_dates"]:
            val = backtest_out.get(key)
            if val is not None:
                report[key] = val
        if report["is_mock"] is None:
            report["is_mock"] = False

        # ============================================
        # Stage 4: Risk Agent
        # ============================================
        logger.info("Stage 4: Risk Agent")
        risk_out = run_risk_agent(backtest_out, account_settings={}, proposed_trade={
            "position_size_pct": 10.0,
            "entry_price": market_data.get("ohlc", {}).get("data", [{}])[0].get("Close", 0) if market_data.get("ohlc", {}).get("data") else 0,
            "stop_loss_price": None,  # No stop-loss = will fail risk checks
            "loss_pct": 2.0,
        }, run_id=run_id)

        if not _validate_agent_output(risk_out, "risk"):
            raise RuntimeError("Risk Agent output failed validation")

        _log_agent_call(conn, run_id, "risk", backtest_out, risk_out)
        report["stages_completed"].append("risk")

        # ============================================
        # HUMAN APPROVAL GATE (HARD STOP)
        # ============================================
        logger.info("Proceeding to Human Approval Gate...")

        if skip_approval:
            # Auto-approve for testing/non-CLI environments
            approval_status = APPROVAL_APPROVED
            approved_by = "system"
            logger.info(f"Auto-approval enabled — proceeding to paper execution (run {risk_out.get('run_id', 'N/A')})")
        else:
            approval_decision = _get_human_approval(risk_out)
            approval_status = approval_decision["approval_status"]
            approved_by = approval_decision["approved_by"]

        # Log the approval decision
        _log_agent_call(
            conn, run_id, "human_approval",
            risk_out,
            {"approval_status": approval_status,
             "approved_by": approved_by},
            human_approval_status=approval_status,
            approved_by=approved_by,
        )

        report["approval_status"] = approval_status
        report["approved_by"] = approved_by

        if approval_status == APPROVAL_REJECTED:
            report["termination_reason"] = "Human approval rejected — pipeline terminated"
            logger.info(f"Pipeline terminated: {report['termination_reason']}")
            conn.close()
            return report

        # Approved — proceed to paper execution
        logger.info("Human approval granted — proceeding to paper execution")

        # ============================================
        # Stage 5: Paper Execution Engine
        # ============================================
        logger.info("Stage 5: Paper Execution Engine")
        from paper_execution.engine import run_paper_execution

        paper_result = run_paper_execution(risk_out, {
            "capital": account_settings.get("capital", 100000) if account_settings else 100000
        }) if 'account_settings' in dir() else run_paper_execution(risk_out, {"capital": 100000})

        if not paper_result:
            raise RuntimeError("Paper execution failed")

        _log_agent_call(conn, run_id, "paper_execution", risk_out, paper_result)
        report["stages_completed"].append("paper_execution")
        report["paper_execution"] = paper_result

        # ============================================
        # Stage 6: Review Agent
        # ============================================
        logger.info("Stage 6: Review Agent")
        review_out = run_review_agent(paper_result, backtest_out, risk_out, {
            "research": research_out,
            "debate": debate_out,
        })

        if not validate_review_output(review_out):
            logger.warning("Review Agent output validation failed (best-effort)")

        _log_agent_call(conn, run_id, "review", risk_out, review_out)
        report["stages_completed"].append("review")
        report["final_review"] = review_out

        report["approval_status"] = APPROVAL_APPROVED
        report["termination_reason"] = "Pipeline completed successfully after approval"

    except Exception as e:
        logger.error(f"Pipeline failed: {str(e)}")
        # Ensure all values are string-serializable
        termination_reason = f"Pipeline error: {str(e)}"
        # Convert any non-serializable values in report to strings
        for key, value in report.items():
            if key not in ("stages_completed",) and not isinstance(value, (str, int, float, bool, type(None))):
                report[key] = str(value)
        report["termination_reason"] = termination_reason
        report["stages_completed"] = report.get("stages_completed", [])

    finally:
        conn.close()

    return report


def validate_review_output(output: Dict[str, Any]) -> bool:
    """
    Validate Review Agent output has expected structure.

    Args:
        output: Review Agent output dictionary

    Returns:
        True if valid, False otherwise
    """
    # Review output can vary — just check it's a dict with some content
    if not isinstance(output, dict):
        return False

    # Must have at least some content
    has_content = any(
        v is not None and v != "" and v != "UNAVAILABLE"
        for v in output.values()
    )
    return has_content or len(output) > 0


def main():
    """CLI entry point for the pipeline."""
    import argparse

    parser = argparse.ArgumentParser(
        description="AI-Orchestrated Equity Research Pipeline — Phase 2"
    )
    parser.add_argument("ticker", nargs="?", default="RELIANCE",
                        help="NSE ticker to analyze (default: RELIANCE)")
    parser.add_argument("--db", default="audit.db",
                        help="SQLite audit database path (default: audit.db)")
    parser.add_argument("--approve", action="store_true",
                        help="Skip human approval gate (USE WITH CAUTION)")

    args = parser.parse_args()

    print("=" * 60)
    print("AI-Orchestrated Equity Research & Risk Simulation Platform")
    print("Phase 2 — 5-Agent Pipeline with Human Approval Gate")
    print("=" * 60)
    print(f"Ticker: {args.ticker}")
    print(f"Audit DB: {args.db}")
    print(f"Skip approval gate: {args.approve}")
    print()

    # Run the pipeline
    result = run_pipeline(ticker=args.ticker, db_path=args.db)

    # Display results
    print("\n" + "=" * 60)
    print("PIPELINE RESULTS")
    print("=" * 60)
    print(f"Run ID: {result.get('run_id', 'N/A')}")
    print(f"Ticker: {result.get('ticker', 'N/A')}")
    print(f"Approval Status: {result.get('approval_status', 'N/A')}")
    print(f"Stages Completed: {len(result.get('stages_completed', []))}/6")
    print(f"Stages: {result.get('stages_completed', [])}")
    print(f"Termination Reason: {result.get('termination_reason', 'N/A')}")
    print()

    if result.get("approval_status") == "rejected":
        print("✗ Paper trade NOT executed (human rejection)")
    elif result.get("approval_status") == "approved":
        print("✓ Paper trade executed (human approval)")
        if result.get("paper_execution"):
            pe = result["paper_execution"]
            print(f"  Trade ID: {pe.get('trade_id', 'N/A')}")
            print(f"  Execution Status: {pe.get('execution_status', 'N/A')}")
        if result.get("final_review"):
            print(f"  Review generated: {len(str(result['final_review']))} chars")
    else:
        print("? Pipeline terminated with errors")

    print("\nAudit database location: audit.db (inspect with SQLite viewer)")
    print("=" * 60)


if __name__ == "__main__":
    main()