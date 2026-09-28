"""
Deterministic Backtest Engine Runner — Phase 3

Convenience module for running backtests from the pipeline.

Provides a simple interface that the Backtest Agent can consume.

The engine is deterministic: same inputs → same outputs.
No randomness, no LLM involvement in calculations.
"""

from __future__ import annotations

import logging
import math
import pandas as pd
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from backtest_engine import MovingAverageCrossover, BacktestEngine, run_backtest, validate_backtest_result


def _sanitize(obj: Any) -> Any:
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize(v) for v in obj]
    return obj


def _filter_list_nan(data: Any) -> Any:
    if isinstance(data, list):
        return [r for r in data if not any(isinstance(r.get(k), float) and math.isnan(r.get(k)) for k in ("Open", "High", "Low", "Close"))]
    if isinstance(data, pd.DataFrame):
        return data.dropna(subset=["Open", "High", "Low", "Close"])
    return data

logger = logging.getLogger(__name__)


# ─── Default Parameters ────────────────────────────────────────────────────

DEFAULT_FAST_PERIOD = 20
DEFAULT_SLOW_PERIOD = 50
DEFAULT_COMMISSION = 0.1  # 0.1% per trade
DEFAULT_SLIPPAGE = 0.05  # 0.05% per trade
DEFAULT_INITIAL_CAPITAL = 100000.0  # ₹10 lakhs
DEFAULT_DIRECTION = "long_only"


# ─── Runner Function ───────────────────────────────────────────────────────

def run_backtest_from_data(
    ohlc_data: pd.DataFrame,
    fast_period: int = DEFAULT_FAST_PERIOD,
    slow_period: int = DEFAULT_SLOW_PERIOD,
    commission: float = DEFAULT_COMMISSION,
    slippage: float = DEFAULT_SLIPPAGE,
    initial_capital: float = DEFAULT_INITIAL_CAPITAL,
    direction: str = DEFAULT_DIRECTION,
) -> Dict[str, Any]:
    """
    Run the deterministic backtest engine on OHLC data.

    This is the main entry point for the Phase 3 backtest pipeline.

    Args:
        ohlc_data: DataFrame with OHLC data, sorted chronologically
        fast_period: Fast SMA period (default: 20)
        slow_period: Slow SMA period (default: 50)
        commission: Transaction commission as percentage (default: 0.1%)
        slippage: Slippage as percentage of execution price (default: 0.05%)
        initial_capital: Starting capital in rupees (default: ₹10,00,000)
        direction: Strategy direction ("long_only" or "short_only")

    Returns:
        Structured backtest result dictionary

    Raises:
        ValueError: If data validation fails
    """
    ohlc_data = _filter_list_nan(ohlc_data)
    if isinstance(ohlc_data, pd.DataFrame) and len(ohlc_data) < slow_period:
        raise ValueError(f"insufficient valid bars after NaN filtering: {len(ohlc_data)} < {slow_period}")
    if isinstance(ohlc_data, list) and len(ohlc_data) < slow_period:
        raise ValueError(f"insufficient valid bars after NaN filtering: {len(ohlc_data)} < {slow_period}")
    try:
        _validate_ohlc_data(ohlc_data)
    except ValueError as e:
        logger.error(f"OHLC data validation failed: {e}")
        raise

    # Run the backtest
    result = run_backtest(
        data=ohlc_data,
        fast_period=fast_period,
        slow_period=slow_period,
        commission=commission,
        slippage=slippage,
        initial_capital=initial_capital,
        direction=direction,
    )

    # Validate the result structure
    if not validate_backtest_result(result):
        logger.error("Backtest result failed validation")
        # Return a structured error result
        return {
            "strategy_type": "moving_average_crossover",
            "fast_period": fast_period,
            "slow_period": slow_period,
            "direction": direction,
            "initial_capital": initial_capital,
            "final_equity": initial_capital,
            "total_return_pct": 0.0,
            "data_start": ohlc_data.index[0] if len(ohlc_data) > 0 else None,
            "data_end": ohlc_data.index[-1] if len(ohlc_data) > 0 else None,
            "number_of_bars": len(ohlc_data) if len(ohlc_data) > 0 else 0,
            "fees_included": True,
            "commission_assumption": commission,
            "slippage_included": True,
            "slippage_assumption": slippage,
            "trades": [],
            "win_rate": None,
            "avg_win": None,
            "avg_loss": None,
            "profit_factor": None,
            "max_drawdown": None,
            "trade_count": 0,
            "winning_trade_count": 0,
            "losing_trade_count": 0,
            "engine_version": "1.0.0",
            "deterministic": True,
            "equity_curve": [],
            "drawdown_series": [],
            "bar_dates": [],
            "data_status": f"error — data validation failed: {e}",
        }

    result = _sanitize(result)
    result["generated_at"] = datetime.now(timezone.utc).isoformat()
    if "data_status" not in result:
        result["data_status"] = "success — deterministic backtest completed"
    return result


# ─── Validation helper ────────────────────────────────────────────────────

def _validate_ohlc_data(ohlc_data: Any) -> bool:
    """Validate OHLC data structure."""
    from backtest_engine import _validate_ohlc_data as _validate
    return _validate(ohlc_data)


# ─── Interface for Backtest Agent ──────────────────────────────────────────

def run_backtest_agent(
    debate_rules: Dict[str, Any],
    ohlc_data: Any,
    ticker: str = "UNKNOWN",
) -> Dict[str, Any]:
    """
    Run the Backtest Agent using the deterministic engine.

    Architecture (Phase 3):
    Debate Agent → structured strategy rules
    ↓
    Deterministic Backtest Engine
    ↓
    Real computed metrics
    ↓
    Backtest Agent interprets results

    Args:
        debate_rules: Debate Agent's output containing entry/exit rules (not directly used;
                     strategy parameters are hard-coded as the Phase 3 supported strategy)
        ohlc_data: Historical OHLC price data
        ticker: Ticker symbol

    Returns:
        Structured backtest output dictionary
    """
    logger.info(f"Running Backtest Agent for {ticker}")

    # Validate OHLC data
    if ohlc_data is None or (isinstance(ohlc_data, list) and len(ohlc_data) == 0):
        # No data available
        result = {
            "trades": [],
            "win_rate": "UNAVAILABLE — no OHLC data provided, deterministic backtest engine required",
            "avg_win": "UNAVAILABLE — no OHLC data provided, deterministic backtest engine required",
            "avg_loss": "UNAVAILABLE — no OHLC data provided, deterministic backtest engine required",
            "profit_factor": "UNAVAILABLE — no OHLC data provided, deterministic backtest engine required",
            "max_drawdown": "UNAVAILABLE — no OHLC data provided, deterministic backtest engine required",
            "fees_included": False,
            "slippage_included": False,
            "is_mock": True,
            "equity_curve": [],
            "drawdown_series": [],
            "bar_dates": [],
            "data_status": "no OHLC data provided",
            "ticker": ticker,
            "resolved_ticker": ticker,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
        return result

    # Convert list-form OHLC to DataFrame if needed
    if isinstance(ohlc_data, list) and len(ohlc_data) > 0 and isinstance(ohlc_data[0], dict):
        ohlc_df = pd.DataFrame(ohlc_data)
        # Ensure index is monotonically increasing for the engine
        if not ohlc_df.index.is_monotonic_increasing:
            ohlc_df = ohlc_df.sort_index()
    elif isinstance(ohlc_data, pd.DataFrame):
        ohlc_df = ohlc_data
        # Ensure sorted chronologically
        if not ohlc_df.index.is_monotonic_increasing:
            ohlc_df = ohlc_df.sort_index()
    else:
        # Unsupported format
        result = {
            "trades": [],
            "win_rate": "UNAVAILABLE — unsupported OHLC data format, deterministic backtest engine required",
            "avg_win": "UNAVAILABLE — unsupported OHLC data format, deterministic backtest engine required",
            "avg_loss": "UNAVAILABLE — unsupported OHLC data format, deterministic backtest engine required",
            "profit_factor": "UNAVAILABLE — unsupported OHLC data format, deterministic backtest engine required",
            "max_drawdown": "UNAVAILABLE — unsupported OHLC data format, deterministic backtest engine required",
            "fees_included": False,
            "slippage_included": False,
            "is_mock": True,
            "equity_curve": [],
            "drawdown_series": [],
            "bar_dates": [],
            "data_status": f"unsupported OHLC data format: {type(ohlc_data)}",
            "ticker": ticker,
            "resolved_ticker": ticker,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
        return result

    # Run the deterministic backtest engine
    try:
        engine_result = run_backtest_from_data(
            ohlc_data=ohlc_df,
            fast_period=DEFAULT_FAST_PERIOD,
            slow_period=DEFAULT_SLOW_PERIOD,
            commission=DEFAULT_COMMISSION,
            slippage=DEFAULT_SLIPPAGE,
            initial_capital=DEFAULT_INITIAL_CAPITAL,
            direction=DEFAULT_DIRECTION,
        )
    except ValueError as e:
        # Data validation failed
        result = {
            "trades": [],
            "win_rate": f"UNAVAILABLE — backtest engine error: {e}",
            "avg_win": f"UNAVAILABLE — backtest engine error: {e}",
            "avg_loss": f"UNAVAILABLE — backtest engine error: {e}",
            "profit_factor": f"UNAVAILABLE — backtest engine error: {e}",
            "max_drawdown": f"UNAVAILABLE — backtest engine error: {e}",
            "fees_included": True,
            "slippage_included": True,
            "is_mock": False,  # Not mock — engine ran but data was invalid
            "equity_curve": [],
            "drawdown_series": [],
            "bar_dates": [],
            "data_status": f"data validation error: {e}",
            "ticker": ticker,
            "resolved_ticker": ticker,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
        return result

    # Map engine result to Backtest Agent output schema
    # The engine result has all the required metrics; we just need to format them
    # appropriately for the agent output

    closed_trades = engine_result.get("trades", [])

    # Determine is_mock: False if engine ran successfully, True only if data was unavailable
    is_mock = engine_result.get("data_status", "").startswith("error") or engine_result.get("data_status", "").startswith("unsupported")

    # Map the engine result to the agent output schema
    result = {
        # Core required metrics (from deterministic engine)
        "trades": closed_trades,
        "win_rate": engine_result.get("win_rate"),
        "avg_win": engine_result.get("avg_win"),
        "avg_loss": engine_result.get("avg_loss"),
        "profit_factor": engine_result.get("profit_factor"),
        "max_drawdown": engine_result.get("max_drawdown"),
        "fees_included": engine_result.get("fees_included", True),
        "slippage_included": engine_result.get("slippage_included", True),

        # Engine metadata
        "is_mock": is_mock,
        "data_status": engine_result.get("data_status", "success — deterministic backtest completed"),

        # Strategy metadata
        "ticker": ticker,
        "resolved_ticker": ticker,
        "generated_at": engine_result.get("generated_at", datetime.now(timezone.utc).isoformat()),

        # Strategy parameters
        "strategy_type": engine_result.get("strategy_type", "moving_average_crossover"),
        "fast_period": engine_result.get("fast_period", DEFAULT_FAST_PERIOD),
        "slow_period": engine_result.get("slow_period", DEFAULT_SLOW_PERIOD),
        "direction": engine_result.get("direction", DEFAULT_DIRECTION),

        # Engine assumptions
        "commission_assumption": engine_result.get("commission_assumption", DEFAULT_COMMISSION),
        "slippage_assumption": engine_result.get("slippage_assumption", DEFAULT_SLIPPAGE),

        # Additional metadata
        "trade_count": engine_result.get("trade_count", 0),
        "winning_trade_count": engine_result.get("winning_trade_count", 0),
        "losing_trade_count": engine_result.get("losing_trade_count", 0),

        # Visualization series
        "equity_curve": engine_result.get("equity_curve", []),
        "drawdown_series": engine_result.get("drawdown_series", []),
        "bar_dates": engine_result.get("bar_dates", []),
    }

    return result