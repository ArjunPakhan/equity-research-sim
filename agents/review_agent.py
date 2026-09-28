"""
Review Agent — skeptical evaluation of completed pipeline run.

Input: paper execution result, backtest result, risk result, relevant research/debate context.
Output: structured report object.

TONE: skeptical and honest. Do not hype the result.
If Phase 3 metrics are unavailable, explicitly state that. Do not fabricate performance.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def run_review_agent(
    paper_execution: Dict[str, Any],
    backtest_result: Dict[str, Any],
    risk_result: Dict[str, Any],
    context: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Run the Review Agent.

    Args:
        paper_execution: Paper Execution Engine result
        backtest_result: Backtest Agent result
        risk_result: Risk Agent result
        context: Dictionary containing research, debate, and pipeline context

    Returns:
        Structured review report dictionary
    """
    ticker = paper_execution.get("ticker", "UNKNOWN")
    trade_id = paper_execution.get("trade_id", "N/A")
    execution_status = paper_execution.get("execution_status", "unknown")

    # Build review report
    report: Dict[str, Any] = {
        "ticker": ticker,
        "trade_id": trade_id,
        "execution_status": execution_status,
        "review_timestamp": datetime.now(timezone.utc).isoformat(),
        "evidence_assessment": "",
        "risk_concerns": [],
        "curve_fitting_concerns": "",
        "should_have_traded": "unavailable",
        "improvements": [],
        "data_limitations": [],
    }

    # --- Evidence Assessment ---
    # Check if there was sufficient evidence for the trade
    risk_warnings = risk_result.get("risk_warnings", [])
    checks_passed = risk_result.get("checks_passed", False)

    if not checks_passed:
        report["evidence_assessment"] = (
            "Insufficient evidence to justify the trade. "
            "Risk checks did not all pass. "
            "Key concerns: " + "; ".join(risk_warnings[:3])
        )
    elif execution_status == "completed":
        report["evidence_assessment"] = (
            "Trade executed with risk checks passed. "
            "Evidence from research and debate was considered, "
            "but retrospective review questions the decision given "
            "subsequent risk assessment."
        )
    else:
        report["evidence_assessment"] = (
            "Trade was initiated but did not complete (no stop-loss). "
            "Evidence was marginal; retrospective review recommends "
            "greater caution on future similar setups."
        )

    # --- Risk Concerns ---
    # Aggregate risk warnings from the risk agent
    if risk_warnings:
        report["risk_concerns"] = risk_warnings[:5]  # Top 5 warnings
    else:
        report["risk_concerns"] = ["No specific risk warnings recorded"]

    # If backtest metrics are unavailable, flag this
    backtest_win_rate = backtest_result.get("win_rate", "")
    if backtest_win_rate and "UNAVAILABLE" in str(backtest_win_rate):
        report["data_limitations"].append(
            "Backtest metrics unavailable (Phase 3 engine required) — "
            "risk assessment based on limited data"
        )

    # --- Curve-Fitting Concerns ---
    # If the trade was based on specific technical levels, flag potential curve-fitting
    key_levels = backtest_result.get("trades", [])
    if key_levels and isinstance(key_levels, list) and len(key_levels) > 0:
        report["curve_fitting_concerns"] = (
            "Trade was based on identifiable technical levels — "
            "reviewers should assess whether these levels were "
            "objectively derived or curve-fitted to historical data"
        )
    else:
        report["curve_fitting_concerns"] = (
            "Insufficient technical data to assess curve-fitting risk "
            "(Phase 3 backtest engine required for full evaluation)"
        )

    # --- Should Have Traded Assessment ---
    # Based on the full pipeline context
    debate_bull = context.get("research", {}).get("trend", "")
    risk_warnings_count = len(risk_warnings) if risk_warnings else 0
    checks_passed_bool = risk_result.get("checks_passed", False)

    if checks_passed_bool and risk_warnings_count <= 2 and "bull" in str(debate_bull).lower():
        report["should_have_traded"] = "possibly — all checks passed and bullish trend present, "
        "but retrospective review is never definitive"
    elif not checks_passed_bool:
        report["should_have_traded"] = "no"
    else:
        report["should_have_traded"] = "unavailable — Phase 3 metrics required for definitive assessment"

    # --- Improvements ---
    improvements = []
    if not checks_passed_bool:
        improvements.append("Ensure all risk checks pass before trade execution")
    if execution_status != "completed":
        improvements.append("Add stop-loss requirement to prevent unlimited loss exposure")
    if "UNAVAILABLE" in str(backtest_win_rate):
        improvements.append("Implement Phase 3 backtest engine for complete metrics")
    if report["data_limitations"]:
        improvements.append("Address data limitations before future similar trades")
    if not improvements:
        improvements.append("No specific improvements identified — result was broadly acceptable")
    report["improvements"] = improvements

    # --- Data Limitations ---
    # Document what data is missing/unavailable
    if not paper_execution.get("entry_price_source") or paper_execution.get("entry_price_source") == "unavailable":
        report["data_limitations"].append(
            "Entry price unavailable — paper execution used simulated price"
        )
    if "UNAVAILABLE" in str(backtest_win_rate):
        report["data_limitations"].append(
            "Backtest win rate unavailable — Phase 3 engine required"
        )
    if risk_result.get("simulation_disclaimer"):
        report["data_limitations"].append(
            "Risk controls are simulation-only, not regulatory compliance"
        )

    logger.info(f"Review Agent completed for {ticker} (trade {trade_id})")
    return report


def validate_review_output(output: Dict[str, Any]) -> bool:
    """
    Validate Review Agent output conforms to expected schema.

    Args:
        output: Review Agent output dictionary

    Returns:
        True if valid, False otherwise
    """
    required_top_level = [
        "ticker", "trade_id", "execution_status", "review_timestamp",
        "evidence_assessment", "risk_concerns", "curve_fitting_concerns",
        "should_have_traded", "improvements", "data_limitations"
    ]

    for field in required_top_level:
        if field not in output:
            logger.error(f"Missing required review field: {field}")
            return False

    # should_have_traded must be one of the allowed values
    allowed_should = {"possibly", "no", "unavailable"}
    if output["should_have_traded"] not in allowed_should:
        logger.error(f"Invalid should_have_traded value: {output['should_have_traded']}")
        return False

    # improvements must be a list
    if not isinstance(output["improvements"], list):
        logger.error("improvements must be a list")
        return False

    # risk_concerns must be a list
    if not isinstance(output["risk_concerns"], list):
        logger.error("risk_concerns must be a list")
        return False

    # data_limitations must be a list
    if not isinstance(output["data_limitations"], list):
        logger.error("data_limitations must be a list")
        return False

    return True