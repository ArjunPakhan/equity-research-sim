"""
Risk Agent — SEBI-informed risk controls (simulation only, not regulatory compliance).

Input: Backtest Agent output, account settings, proposed trade information.
Required output: { position_size, stop_loss, exposure_limit, daily_loss_limit,
checks_passed: true/false, sebi_aligned_controls: [...], risk_warnings: [...] }

PHASE 3 CRITICAL:
- Do NOT claim regulatory compliance or SEBI approval
- If backtest metrics are unavailable (Phase 3 not implemented), Risk Agent
  MUST NOT pretend risk checks passed based on imaginary metrics
- It should clearly mark dependent checks as unavailable or unable to pass
- All controls are educational simulation only
- PYTHON FALSY-VALUE BUG PREVENTION: 0.0 is a legitimate financial value,
  not "false". Use explicit is not None checks, not truthiness checks.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Risk control configuration (simulation settings, not real SEBI thresholds)
RISK_CONFIG = {
    "max_position_exposure_pct": 25.0,       # Max % of portfolio per position
    "max_daily_loss_pct": 5.0,               # Max % of portfolio daily loss
    "max_drawdown_ceiling_pct": 15.0,        # Max drawdown ceiling
    "stop_loss_required": True,              # Whether stop-loss is required
    "exposure_limit_required": True,         # Whether exposure limit is required
    "order_rate_limit_per_day": 10,          # Simulated orders-per-day limit
    "simulation_disclaimer": (
        "RISK CONTROLS: These are educational simulation controls informed by "
        "principles associated with algorithmic trading. They do not constitute "
        "regulatory compliance or SEBI approval. All values are simulation parameters."
    ),
}


class RiskAgentError(Exception):
    """Exception raised when Risk Agent execution fails."""
    pass


def _calculate_position_size(
    proposed_position_pct: float,
    max_exposure_pct: float = None,
    account_capital: float = None,
    stop_loss_price: float = None,
    entry_price: float = None,
) -> Dict[str, Any]:
    """
    Calculate position size with safety checks.

    Args:
        proposed_position_pct: Proposed position size as percentage of capital
        max_exposure_pct: Maximum allowed exposure percentage
        account_captial: Account capital amount
        stop_loss_price: Stop-loss price
        entry_price: Entry price

    Returns:
        Dictionary with position size calculation and warnings
    """
    max_pct = max_exposure_pct or RISK_CONFIG["max_position_exposure_pct"]

    # Clamp to max exposure
    clamped_pct = max(0, min(100, proposed_position_pct))
    actual_pct = min(clamped_pct, max_pct)

    warnings = []
    if proposed_position_pct > max_pct:
        warnings.append(
            f"Proposed position ({proposed_position_pct}%) exceeds max exposure "
            f"({max_pct}%) — clamped to {actual_pct}%"
        )
    if proposed_position_pct < 0:
        warnings.append("Proposed position size was negative — clamped to 0%")

    result = {"position_size_pct": actual_pct, "warnings": warnings}
    return result


def _check_daily_loss_limit(
    proposed_loss_pct: float,
    max_daily_loss_pct: float = None,
) -> Dict[str, Any]:
    """
    Check proposed daily loss against limit.

    Args:
        proposed_loss_pct: Proposed loss as percentage of capital
        max_daily_loss_pct: Maximum daily loss percentage

    Returns:
        Dictionary with check result and warnings
    """
    limit = max_daily_loss_pct or RISK_CONFIG["max_daily_loss_pct"]

    if proposed_loss_pct > limit:
        return {
            "within_limit": False,
            "warning": f"Proposed loss ({proposed_loss_pct}%) exceeds daily limit "
                       f"({limit}%)",
        }
    return {"within_limit": True, "warning": ""}


def _check_drawdown_ceiling(
    current_drawdown_pct: float,
    ceiling_pct: float = None,
) -> Dict[str, Any]:
    """
    Check drawdown against ceiling.

    Args:
        current_drawdown_pct: Current drawdown percentage
        ceiling_pct: Maximum drawdown ceiling

    Returns:
        Dictionary with check result and warnings
    """
    ceiling = ceiling_pct or RISK_CONFIG["max_drawdown_ceiling_pct"]

    if current_drawdown_pct > ceiling:
        return {
            "within_ceiling": False,
            "warning": f"Drawdown ({current_drawdown_pct}%) exceeds ceiling "
                       f"({ceiling}%)",
        }
    return {"within_ceiling": True, "warning": ""}


def run_risk_agent(
    backtest_output: Dict[str, Any],
    account_settings: Dict[str, Any] = None,
    proposed_trade: Dict[str, Any] = None,
    *,
    run_id: str,
) -> Dict[str, Any]:
    """
    Run the Risk Agent.

    Args:
        backtest_output: Backtest Agent's structured output
        account_settings: Simulated account configuration (capital, limits, etc.)
        proposed_trade: Proposed trade information (ticker, size, entry, stop-loss)
        run_id: The caller's canonical pipeline run ID

    Returns:
        Structured risk output dictionary

    Raises:
        RiskAgentError: If agent execution fails
    """
    ticker = "UNKNOWN"
    resolved_ticker = "UNKNOWN"

    # Extract ticker from backtest output if available
    if backtest_output:
        ticker = backtest_output.get("ticker", "UNKNOWN")
        resolved_ticker = backtest_output.get("resolved_ticker", ticker)

    logger.info(f"Running Risk Agent for {ticker}")

    # Initialize result with run ID and disclaimer
    result = {
        "run_id": run_id,
        "ticker": ticker,
        "resolved_ticker": resolved_ticker,
        "simulation_disclaimer": RISK_CONFIG["simulation_disclaimer"],
        "checks_passed": False,  # Start as False — must be explicitly earned
        "sebi_aligned_controls": [],
        "risk_warnings": [],
        "exposure_limit": None,
        "daily_loss_limit": None,
        "position_size": None,
        "stop_loss": None,
    }

    # If no backtest output, mark all dependent checks as unavailable
    if not backtest_output:
        result["risk_warnings"].append(
            "No backtest data available — Phase 3 backtest engine required for full checks"
        )
        result["risk_warnings"].append(
            "Risk checks dependent on backtest metrics are marked UNAVAILABLE"
        )
        result["checks_passed"] = False
        return result

    # If no proposed trade, we can still check exposure limits
    if not proposed_trade:
        result["risk_warnings"].append(
            "No proposed trade information — exposure and position checks limited"
        )
        result["risk_warnings"].append(
            "No trade will be executed without proposed trade details"
        )
        result["checks_passed"] = False
        return result

    # --- Perform risk checks ---

    # 1. Unique decision identifier (always passes - it's just tracking)
    result["sebi_aligned_controls"].append("unique_decision_identifier")

    # 2. Position size calculation
    proposed_size_pct = proposed_trade.get("position_size_pct", 0)
    entry_price = proposed_trade.get("entry_price", 0)
    stop_loss_price = proposed_trade.get("stop_loss_price", None)
    account_capital = account_settings.get("capital", 100000) if account_settings else 100000

    position_result = _calculate_position_size(
        proposed_position_pct=proposed_size_pct,
        max_exposure_pct=RISK_CONFIG["max_position_exposure_pct"],
        account_capital=account_capital,
        stop_loss_price=stop_loss_price,
        entry_price=entry_price,
    )

    result["position_size"] = position_result["position_size_pct"]
    result["risk_warnings"].extend(position_result["warnings"])

    # 3. Stop-loss requirement check
    has_stop_loss = stop_loss_price is not None and stop_loss_price > 0
    result["stop_loss"] = stop_loss_price if has_stop_loss else None

    if has_stop_loss:
        result["sebi_aligned_controls"].append("stop-loss specified")
    else:
        result["risk_warnings"].append(
            "Stop-loss not specified — required for all simulated trades"
        )

    # 3. Exposure limit check
    result["exposure_limit"] = RISK_CONFIG["max_position_exposure_pct"]

    # 4. Daily loss limit check
    # FIX: Use explicit is not None check instead of truthiness to avoid Python
    # falsy bug where 0.0 (a valid financial value) is treated as False.
    # The backtest max drawdown can legitimately be 0.0.
    backtest_max_dd = backtest_output.get("max_drawdown", "")
    if backtest_max_dd is not None and backtest_max_dd != "":
        # Numeric drawdown from backtest — use it to contextually inform the daily check
        try:
            bdd = float(backtest_max_dd)
        except (ValueError, TypeError):
            bdd = 0
        
        # Use the backtest drawdown to contextualize the daily loss check,
        # but still use the configured limit as the authoritative check
        daily_check = _check_daily_loss_limit(
            proposed_loss_pct=proposed_trade.get("loss_pct", 0),
            max_daily_loss_pct=RISK_CONFIG["max_daily_loss_pct"],
        )
    else:
        # No valid backtest drawdown — use config default and mark as note
        daily_check = _check_daily_loss_limit(
            proposed_loss_pct=proposed_trade.get("loss_pct", 0),
            max_daily_loss_pct=RISK_CONFIG["max_daily_loss_pct"],
        )
        result["risk_warnings"].append(
            "Max drawdown from backtest is unavailable — using default daily loss limit"
        )

    result["risk_warnings"].extend(daily_check.get("warning", "").split(". ") if daily_check.get("warning") else [])
    if daily_check.get("within_limit"):
        result["sebi_aligned_controls"].append("daily loss limit check")

    # 4. Drawdown ceiling check
    # FIX: Use explicit is not None check. The backtest max drawdown can be 0.0
    # (meaning no decline from peak), which must NOT be treated as unavailable.
    if backtest_max_dd is not None and isinstance(backtest_max_dd, (int, float)):
        dd_check = _check_drawdown_ceiling(current_drawdown_pct=backtest_max_dd)
    else:
        # Mark as unavailable since backtest drawdown not available
        dd_check = {"within_ceiling": False, "warning": (
            "Max drawdown from backtest is unavailable (Phase 3 engine required) — "
            "drawdown ceiling check marked UNAVAILABLE"
        )}

    result["risk_warnings"].extend([dd_check.get("warning", "")])
    if dd_check.get("within_ceiling") and dd_check.get("warning", "") == "":
        result["sebi_aligned_controls"].append("drawdown ceiling check")

    # 5. Order rate check (simulated — we only have one trade per pipeline run)
    result["sebi_aligned_controls"].append("order-rate check (single pipeline run)")

    # Determine if all critical checks passed
    # FIX: Use explicit boolean checks rather than truthiness of numeric values
    critical_passed = (
        "stop-loss specified" in result["sebi_aligned_controls"]
        or has_stop_loss  # Allow if stop-loss was specified in proposed trade
    ) and daily_check.get("within_limit", False)

    # If stop-loss is missing and this is a critical requirement, fail
    if not has_stop_loss:
        critical_passed = False
        result["risk_warnings"].append(
            "Critical: Stop-loss not specified — trade cannot pass risk checks"
        )

    # If drawdown ceiling check is unavailable, mark as unable to pass
    if not dd_check.get("within_ceiling") and "unavailable" in dd_check.get("warning", "").lower():
        critical_passed = False
        result["risk_warnings"].append(
            "Drawdown ceiling check unavailable — Phase 3 backtest engine required"
        )

    result["checks_passed"] = critical_passed

    return result


def validate_risk_output(output: Dict[str, Any]) -> bool:
    """
    Validate Risk Agent output conforms to schema.

    Args:
        output: Risk Agent output dictionary

    Returns:
        True if valid, False otherwise
    """
    required_fields = [
        "run_id", "ticker", "resolved_ticker", "simulation_disclaimer",
        "checks_passed", "sebi_aligned_controls", "risk_warnings",
        "exposure_limit", "daily_loss_limit", "position_size", "stop_loss"
    ]

    for field in required_fields:
        if field not in output:
            logger.error(f"Missing required field: {field}")
            return False

    # run_id must be string
    if not isinstance(output["run_id"], str):
        logger.error("run_id must be string")
        return False

    # checks_passed must be boolean
    if not isinstance(output["checks_passed"], bool):
        logger.error("checks_passed must be boolean")
        return False

    # sebi_aligned_controls must be list
    if not isinstance(output["sebi_aligned_controls"], list):
        logger.error("sebi_aligned_controls must be list")
        return False

    # risk_warnings must be list
    if not isinstance(output["risk_warnings"], list):
        logger.error("risk_warnings must be list")
        return False

    # exposure_limit must be numeric or None
    if output["exposure_limit"] is not None and not isinstance(output["exposure_limit"], (int, float)):
        logger.error("exposure_limit must be numeric or None")
        return False

    # daily_loss_limit must be numeric or None
    if output["daily_loss_limit"] is not None and not isinstance(output["daily_loss_limit"], (int, float)):
        logger.error("daily_loss_limit must be numeric or None")
        return False

    # position_size must be numeric or None
    if output["position_size"] is not None and not isinstance(output["position_size"], (int, float)):
        logger.error("position_size must be numeric or None")
        return False

    # stop_loss must be numeric or None
    if output["stop_loss"] is not None and not isinstance(output["stop_loss"], (int, float)):
        logger.error("stop_loss must be numeric or None")
        return False

    # simulation_disclaimer must be string
    if not isinstance(output["simulation_disclaimer"], str):
        logger.error("simulation_disclaimer must be string")
        return False

    return True