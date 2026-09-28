"""
Paper Execution Engine — local simulation only.

This is NOT a broker. It does not connect to any broker API, send any external
orders, or handle real-money execution. All activity is local/simulated.

The engine accepts a validated Risk Agent output and simulates a paper order,
recording the trade for audit purposes.
"""

from __future__ import annotations

import json
import logging
import uuid
import json
from datetime import datetime, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Constants for paper execution
PAPER_ONLY = "PAPER_ONLY"
EXECUTION_STATUS_INITIATED = "initiated"
EXECUTION_STATUS_COMPLETED = "completed"
EXECUTION_STATUS_REJECTED = "rejected"


def run_paper_execution(
    risk_output: Dict[str, Any],
    account: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Simulate a paper trade execution.

    Args:
        risk_output: Risk Agent's structured output (must contain ticker,
                     position_size, stop_loss, etc.)
        account: Account simulation settings (capital, etc.)

    Returns:
        Structured paper execution result dictionary

    Raises:
        ValueError: If required data is missing or invalid
    """
    ticker = risk_output.get("ticker", "UNKNOWN")
    resolved_ticker = risk_output.get("resolved_ticker", ticker)
    position_size_pct = risk_output.get("position_size", 0)
    stop_loss = risk_output.get("stop_loss", None)
    account_capital = account.get("capital", 100000)

    # Validate that we have minimum required data
    if not ticker or ticker == "UNKNOWN":
        raise ValueError("Cannot execute paper trade: ticker is unavailable")

    # Calculate simulated quantity based on position size and capital
    # Position size is a percentage; convert to share quantity simulation
    # Using a simple simulation: quantity = (capital * pct / 100) / entry_price
    # But we don't have a real entry price, so we simulate the concepts

    # Simulated entry price — use last known price from market data if available,
    # otherwise mark as unavailable
    entry_price = risk_output.get("entry_price", None)
    entry_price_source = "unavailable"

    if entry_price is not None and entry_price > 0:
        entry_price_source = "calculated"
    else:
        # Try to get from market data via the risk output metadata
        # In Phase 2, we mark this as unavailable
        entry_price = 0.0
        entry_price_source = "unavailable — Phase 2 mock"

    # Simulated execution price (same as entry for simple simulation)
    execution_price = entry_price

    # Calculate simulated notional
    if entry_price and entry_price > 0:
        notional = (account_capital * position_size_pct / 100) / entry_price
        simulated_quantity = int(notional)  # Integer share simulation
    else:
        notional = 0.0
        simulated_quantity = 0
        entry_price = 0.0

    # Generate paper trade ID
    trade_id = str(uuid.uuid4())

    # Determine execution status
    has_stop_loss = stop_loss is not None and stop_loss > 0
    execution_status = EXECUTION_STATUS_COMPLETED if has_stop_loss else EXECUTION_STATUS_INITIATED

    # Build result
    result = {
        "trade_id": trade_id,
        "run_id": risk_output.get("run_id", "UNKNOWN"),
        "ticker": ticker,
        "resolved_ticker": resolved_ticker,
        "execution_status": execution_status,
        "execution_type": PAPER_ONLY,
        "entry_price": entry_price,
        "execution_price": execution_price,
        "simulated_quantity": simulated_quantity,
        "position_size_pct": position_size_pct,
        "stop_loss": stop_loss,
        "account_capital": account_capital,
        "notional": notional,
        "entry_price_source": entry_price_source,
        "execution_timestamp": datetime.now(timezone.utc).isoformat(),
        "simulation_disclaimer": (
            "This is a paper-trading simulation only. No real orders were placed. "
            "No real money was involved. Results are for educational purposes."
        ),
    }

    logger.info(f"Paper execution simulated: {trade_id} for {ticker}")
    return result


def validate_paper_execution_output(output: Dict[str, Any]) -> bool:
    """
    Validate Paper Execution Engine output conforms to schema.

    Args:
        output: Paper execution result dictionary

    Returns:
        True if valid, False otherwise
    """
    required_fields = [
        "trade_id", "run_id", "ticker", "resolved_ticker",
        "execution_status", "execution_type", "entry_price",
        "execution_price", "simulated_quantity", "position_size_pct",
        "stop_loss", "account_capital", "notional", "entry_price_source",
        "execution_timestamp", "simulation_disclaimer"
    ]

    for field in required_fields:
        if field not in output:
            return False

    # execution_status must be one of the known values
    valid_statuses = [EXECUTION_STATUS_INITIATED, EXECUTION_STATUS_COMPLETED, EXECUTION_STATUS_REJECTED]
    if output["execution_status"] not in valid_statuses:
        return False

    # execution_type must be PAPER_ONLY
    if output["execution_type"] != PAPER_ONLY:
        return False

    # trade_id must be a non-empty string
    if not output["trade_id"] or not isinstance(output["trade_id"], str):
        return False

    # run_id must be a non-empty string
    if not output["run_id"] or not isinstance(output["run_id"], str):
        return False

    # simulation_disclaimer must be a non-empty string
    if not output["simulation_disclaimer"] or not isinstance(output["simulation_disclaimer"], str):
        return False

    # If execution_status is COMPLETED, stop_loss should ideally be present
    if output["execution_status"] == EXECUTION_STATUS_COMPLETED and output["stop_loss"] is None:
        # This is allowed in Phase 2 — stop-loss may be unavailable
        pass  # Not a hard failure

    return True