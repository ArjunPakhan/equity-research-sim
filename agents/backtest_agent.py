"""
Backtest Agent — interfaces with deterministic backtest engine.

IMPORTANT:
This agent now uses the Phase 3 deterministic backtest engine.

Architecture (Phase 3):
  Debate Agent
      ↓
  structured strategy rules
      ↓
  Deterministic Backtest Engine
      ↓
  real computed metrics
      ↓
  Backtest Agent interprets & presents results
      ↓
  Risk Agent

The Backtest Agent does NOT calculate metrics independently.
It receives the deterministic engine result and presents it.

Rules:
- NEVER fabricate realistic-looking percentages
- is_mock: False when engine ran successfully
- is_mock: True only when data is genuinely unavailable
- If engine fails: explicit error/data_status, not fake metrics
"""

from __future__ import annotations

import json
import logging
import math
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def _sanitize(obj: Any) -> Any:
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize(v) for v in obj]
    return obj

# Import deterministic engine components
try:
    from backtest_engine.runner import run_backtest_from_data
    from backtest_engine import validate_backtest_result
    BACKTEST_ENGINE_AVAILABLE = True
except ImportError as e:
    BACKTEST_ENGINE_AVAILABLE = False
    _engine_import_error = str(e)

logger = logging.getLogger(__name__)

# Minimum required fields for backtest output (per spec Section 10)
MIN_REQUIRED_BACKTEST_FIELDS = [
    "trades", "win_rate", "avg_win", "avg_loss",
    "profit_factor", "max_drawdown",
    "fees_included", "slippage_included",
    "is_mock", "data_status",
    "ticker", "resolved_ticker",
    "generated_at"
]

# Default strategy parameters (Phase 3: only supported strategy)
DEFAULT_FAST_PERIOD = 20
DEFAULT_SLOW_PERIOD = 50
DEFAULT_COMMISSION = 0.1  # 0.1% per trade
DEFAULT_SLIPPAGE = 0.05  # 0.05% per trade
DEFAULT_INITIAL_CAPITAL = 100000.0  # ₹10 lakhs
DEFAULT_DIRECTION = "long_only"


# ─── Mock result (used ONLY when data is genuinely unavailable) ─────────────

MOCK_BACKTEST_RESULT = {
    "trades": [],
    "win_rate": "UNAVAILABLE — Phase 3 deterministic backtest engine required (no OHLC data)",
    "avg_win": "UNAVAILABLE — Phase 3 deterministic backtest engine required (no OHLC data)",
    "avg_loss": "UNAVAILABLE — Phase 3 deterministic backtest engine required (no OHLC data)",
    "profit_factor": "UNAVAILABLE — Phase 3 deterministic backtest engine required (no OHLC data)",
    "max_drawdown": "UNAVAILABLE — Phase 3 deterministic backtest engine required (no OHLC data)",
    "fees_included": False,
    "slippage_included": False,
    "is_mock": True,
    "equity_curve": [],
    "drawdown_series": [],
    "bar_dates": [],
    "data_status": "no OHLC data provided — Phase 3 engine cannot run",
    "ticker": "",
    "resolved_ticker": "",
    "generated_at": "",
}


# ─── Strategy preparation from debate output ───────────────────────────────

def _prepare_strategy_from_debate(debate_rules: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract strategy parameters from Debate Agent output.

    Phase 3: The Backtest Agent uses the predefined MovingAverageCrossover
    strategy regardless of debate output. The debate output's failure_conditions
    and no_trade_conditions are used by the Risk Agent and pipeline, not
    the backtest engine strategy selection.

    Returns:
        Strategy parameters dictionary
    """
    return {
        "strategy_type": "moving_average_crossover",
        "fast_period": DEFAULT_FAST_PERIOD,
        "slow_period": DEFAULT_SLOW_PERIOD,
        "direction": DEFAULT_DIRECTION,
    }


# ─── Backtest Agent ────────────────────────────────────────────────────────

def run_backtest_agent(
    debate_rules: Dict[str, Any],
    ohlc_data: Any,
    ticker: str = "UNKNOWN",
) -> Dict[str, Any]:
    """
    Run the Backtest Agent.

    Phase 3 Architecture:
    - Receives structured strategy rules from Debate Agent (for pipeline use)
    - Passes OHLC data to the deterministic backtest engine
    - Engine returns real computed metrics
    - Agent presents the results without modification/fabrication

    Args:
        debate_rules: Debate Agent's output containing entry/exit rules
                      (currently not directly consumed for strategy selection;
                       Phase 3 uses predefined MovingAverageCrossover)
        ohlc_data: Historical OHLC price data
        ticker: Ticker symbol

    Returns:
        Structured backtest output dictionary

    Raises:
        BacktestAgentError: If agent execution fails
    """
    logger.info(f"Running Backtest Agent for {ticker}")

    # Input validation
    if ohlc_data is None:
        # No data at all — return explicit mock result
        result = MOCK_BACKTEST_RESULT.copy()
        result["ticker"] = ticker
        result["resolved_ticker"] = ticker
        result["generated_at"] = datetime.now(timezone.utc).isoformat()
        return result

    # Check if deterministic engine is available
    if not BACKTEST_ENGINE_AVAILABLE:
        logger.warning(f"Deterministic backtest engine not available: {_engine_import_error}")
        result = MOCK_BACKTEST_RESULT.copy()
        result["ticker"] = ticker
        result["resolved_ticker"] = ticker
        result["data_status"] = f"deterministic engine unavailable: {_engine_import_error}"
        result["generated_at"] = datetime.now(timezone.utc).isoformat()
        return result

    # Try the deterministic backtest engine
    try:
        # Prepare strategy parameters (Phase 3: always moving average crossover)
        strategy_params = _prepare_strategy_from_debate(debate_rules if debate_rules else {})

        # Run the deterministic backtest engine
        engine_result = run_backtest_from_data(
            ohlc_data=ohlc_data,
            fast_period=strategy_params["fast_period"],
            slow_period=strategy_params["slow_period"],
            commission=DEFAULT_COMMISSION,
            slippage=DEFAULT_SLIPPAGE,
            initial_capital=DEFAULT_INITIAL_CAPITAL,
            direction=strategy_params["direction"],
        )

        # Validate the engine result structure
        if engine_result is None:
            # Engine returned None unexpectedly
            result = MOCK_BACKTEST_RESULT.copy()
            result["ticker"] = ticker
            result["resolved_ticker"] = ticker
            result["data_status"] = "backtest engine returned no result"
            result["generated_at"] = datetime.now(timezone.utc).isoformat()
            return result

        result = {
            "trades": engine_result.get("trades", []),
            "win_rate": engine_result.get("win_rate"),
            "avg_win": engine_result.get("avg_win"),
            "avg_loss": engine_result.get("avg_loss"),
            "profit_factor": engine_result.get("profit_factor"),
            "max_drawdown": engine_result.get("max_drawdown"),
            "fees_included": engine_result.get("fees_included", True),
            "slippage_included": engine_result.get("slippage_included", True),
            "is_mock": False,
            "data_status": engine_result.get("data_status", "success — deterministic backtest completed"),
            "ticker": engine_result.get("ticker", ticker),
            "resolved_ticker": engine_result.get("resolved_ticker", ticker),
            "generated_at": engine_result.get("generated_at", datetime.now(timezone.utc).isoformat()),
            "strategy_type": engine_result.get("strategy_type", "moving_average_crossover"),
            "engine_version": engine_result.get("engine_version"),
            "fast_period": engine_result.get("fast_period", DEFAULT_FAST_PERIOD),
            "slow_period": engine_result.get("slow_period", DEFAULT_SLOW_PERIOD),
            "direction": engine_result.get("direction", DEFAULT_DIRECTION),
            "commission_assumption": engine_result.get("commission_assumption", DEFAULT_COMMISSION),
            "slippage_assumption": engine_result.get("slippage_assumption", DEFAULT_SLIPPAGE),
            "trade_count": engine_result.get("trade_count", 0),
            "winning_trade_count": engine_result.get("winning_trade_count", 0),
            "losing_trade_count": engine_result.get("losing_trade_count", 0),
            "initial_capital": engine_result.get("initial_capital", DEFAULT_INITIAL_CAPITAL),
            "final_equity": engine_result.get("final_equity"),
            "total_return_pct": engine_result.get("total_return_pct"),
            "data_start": engine_result.get("data_start"),
            "data_end": engine_result.get("data_end"),
            "number_of_bars": engine_result.get("number_of_bars"),

            # Visualization series
            "equity_curve": engine_result.get("equity_curve", []),
            "drawdown_series": engine_result.get("drawdown_series", []),
            "bar_dates": engine_result.get("bar_dates", []),
        }

        return _sanitize(result)

    except Exception as e:
        logger.error(f"Backtest Agent execution error: {e}", exc_info=True)
        # Return explicit error result — NEVER fabricate metrics
        result = {
            "trades": [],
            "win_rate": f"UNAVAILABLE — backtest agent error: {e}",
            "avg_win": f"UNAVAILABLE — backtest agent error: {e}",
            "avg_loss": f"UNAVAILABLE — backtest agent error: {e}",
            "profit_factor": f"UNAVAILABLE — backtest agent error: {e}",
            "max_drawdown": f"UNAVAILABLE — backtest agent error: {e}",
            "fees_included": False,
            "slippage_included": False,
            "is_mock": True,
            "equity_curve": [],
            "drawdown_series": [],
            "bar_dates": [],
            "data_status": f"backtest agent error: {e}",
            "ticker": ticker,
            "resolved_ticker": ticker,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
        return result


def validate_backtest_output(output: Dict[str, Any]) -> bool:
    """
    Validate Backtest Agent output conforms to schema.

    Phase 3 Validation:
    - If is_mock is True: metrics should be strings marking unavailability
    - If is_mock is False: metrics should be numeric or None (from engine)
    - Required fields must be present
    - trades must be a list

    Args:
        output: Backtest Agent output dictionary

    Returns:
        True if valid, False otherwise
    """
    # Check required fields
    for field in MIN_REQUIRED_BACKTEST_FIELDS:
        if field not in output:
            logger.error(f"Missing required field: {field}")
            return False

    # is_mock must be boolean
    if not isinstance(output["is_mock"], bool):
        logger.error("is_mock must be boolean")
        return False

    # data_status must be string
    if not isinstance(output["data_status"], str):
        logger.error("data_status must be string")
        return False

    # trades must be a list
    if not isinstance(output["trades"], list):
        logger.error("trades must be a list")
        return False

    # If is_mock is True, metrics should be strings marking unavailability
    if output["is_mock"]:
        for metric in ["win_rate", "avg_win", "avg_loss", "profit_factor", "max_drawdown"]:
            metric_val = output[metric]
            if metric_val is not None and not isinstance(metric_val, str):
                logger.error(f"{metric} in mock mode must be a string or None")
                return False
            if metric_val is not None and "UNAVAILABLE" not in str(metric_val).upper():
                # In mock mode, if it's a string, it should mark unavailability
                logger.warning(f"{metric} in mock mode is a string but doesn't mark unavailability: {metric_val}")
        # fees_included and slippage_included should be False in mock mode
        if output.get("fees_included") is not False:
            logger.warning("fees_included in mock mode should be False")
        if output.get("slippage_included") is not False:
            logger.warning("slippage_included in mock mode should be False")

    # If is_mock is False, metrics should be numeric or None (from engine)
    else:
        for metric in ["win_rate", "avg_win", "avg_loss", "profit_factor", "max_drawdown"]:
            metric_val = output[metric]
            # Accept numeric, None, or the string "UNAVAILABLE"
            if metric_val is not None and not isinstance(metric_val, (int, float)):
                # Allow the string "UNAVAILABLE" as a special case
                if not (isinstance(metric_val, str) and str(metric_val).upper() == "UNAVAILABLE"):
                    logger.error(f"{metric} in non-mock mode must be numeric or None, got: {type(metric_val).__name__} = {metric_val}")
                    return False

        # fees_included and slippage_included should be boolean
        if not isinstance(output["fees_included"], bool):
            logger.error("fees_included must be boolean")
            return False
        if not isinstance(output["slippage_included"], bool):
            logger.error("slippage_included must be boolean")
            return False

    return True