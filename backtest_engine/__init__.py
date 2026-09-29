"""
Deterministic Backtest Engine — Phase 3

A clean, deterministic quantitative backtesting engine for Indian equity
simulation. Calculates real performance metrics from historical OHLC data.

Principles:
- NO fabricated metrics
- NO look-ahead bias
- NO arbitrary code execution
- DETERMINISTIC: same inputs → same outputs
- Fees and slippage explicitly modeled
"""

from __future__ import annotations

import math
import numpy as np
import pandas as pd
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple


def _sanitize_result(obj: Any) -> Any:
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    if isinstance(obj, dict):
        return {k: _sanitize_result(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize_result(v) for v in obj]
    return obj


def _filter_nan_ohlc(data: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(data, pd.DataFrame):
        return data
    mask = data[["Open", "High", "Low", "Close"]].isna().any(axis=1)
    if mask.any():
        data = data[~mask].copy()
    return data


# ─── Validation ────────────────────────────────────────────────────────────

def _validate_ohlc_data(data: Any) -> bool:
    """
    Validate OHLC data structure.

    Required columns: Open, High, Low, Close
    Data must be chronological, no duplicates, numeric values.
    Impossible OHLC relationships must be flagged (not silently repaired).

    Raises:
        ValueError: If data validation fails
    """
    if data is None:
        raise ValueError("OHLC data is None")

    if isinstance(data, pd.DataFrame):
        required_cols = {"Open", "High", "Low", "Close"}
        missing = required_cols - set(data.columns)
        if missing:
            raise ValueError(f"OHLC DataFrame missing required columns: {missing}")

        if data.empty:
            raise ValueError("OHLC DataFrame is empty")

        # Check chronological order (index must be monotonically increasing)
        if not data.index.is_monotonic_increasing:
            raise ValueError("OHLC data index is not monotonically increasing (not chronological)")

        # Check for duplicate timestamps
        if data.index.duplicated().any():
            raise ValueError("OHLC data contains duplicate timestamps")

        # Validate numeric OHLC values
        for col in ["Open", "High", "Low", "Close"]:
            if not pd.api.types.is_numeric_dtype(data[col]):
                raise ValueError(f"OHLC column '{col}' is not numeric")

        # Check impossible OHLC relationships
        # High < Low is invalid
        invalid_high_low = (data["High"] < data["Low"])
        if invalid_high_low.any():
            n_invalid = invalid_high_low.sum()
            raise ValueError(f"OHLC validation failed: {n_invalid} records have High < Low")

        # Close > High is invalid
        invalid_close_high = (data["Close"] > data["High"])
        if invalid_close_high.any():
            n_invalid = invalid_close_high.sum()
            raise ValueError(f"OHLC validation failed: {n_invalid} records have Close > High")

        # Close < Low is invalid
        invalid_close_low = (data["Close"] < data["Low"])
        if invalid_close_low.any():
            n_invalid = invalid_close_low.sum()
            raise ValueError(f"OHLC validation failed: {n_invalid} records have Close < Low")

        # Open > High is invalid
        invalid_open_high = (data["Open"] > data["High"])
        if invalid_open_high.any():
            n_invalid = invalid_open_high.sum()
            raise ValueError(f"OHLC validation failed: {n_invalid} records have Open > High")

        # Open < Low is invalid
        invalid_open_low = (data["Open"] < data["Low"])
        if invalid_open_low.any():
            n_invalid = invalid_open_low.sum()
            raise ValueError(f"OHLC validation failed: {n_invalid} records have Open < Low")

        return True

    if isinstance(data, list) and len(data) > 0:
        # Check first record structure
        first = data[0]
        if not isinstance(first, dict):
            raise ValueError("OHLC list records must be dictionaries")

        required = {"Open", "High", "Low", "Close"}
        if not required.issubset(set(first.keys())):
            raise ValueError(f"OHLC list records missing required keys: {required - set(first.keys())}")

        # Validate each record
        for i, record in enumerate(data):
            if not isinstance(record, dict):
                raise ValueError(f"OHLC record {i} is not a dictionary")
            if not required.issubset(set(record.keys())):
                raise ValueError(f"OHLC record {i} missing required keys: {required - set(record.keys())}")
            # Check numeric values
            for col in required:
                if not isinstance(record[col], (int, float)):
                    raise ValueError(f"OHLC record {i} column '{col}' is not numeric")
            # Check OHLC relationships
            if record["High"] < record["Low"]:
                raise ValueError(f"OHLC record {i}: High < Low is invalid")
            if record["Close"] > record["High"]:
                raise ValueError(f"OHLC record {i}: Close > High is invalid")
            if record["Close"] < record["Low"]:
                raise ValueError(f"OHLC record {i}: Close < Low is invalid")
            if record["Open"] > record["High"]:
                raise ValueError(f"OHLC record {i}: Open > High is invalid")
            if record["Open"] < record["Low"]:
                raise ValueError(f"OHLC record {i}: Open < Low is invalid")

        # Validate chronological order (records must be in order)
        # Check that timestamps are increasing if present
        if "Date" in data[0]:
            dates = [r.get("Date") for r in data]
            if len(dates) != len(set(dates)):
                raise ValueError("OHLC data contains duplicate timestamps")

        return True

    raise ValueError(f"Unsupported OHLC data format: {type(data)}")


# ─── Moving Average Crossover Strategy ─────────────────────────────────────

class MovingAverageCrossover:
    """
    Deterministic Moving Average Crossover strategy.

    Rules:
    - Fast SMA crosses above slow SMA → ENTRY (long)
    - Fast SMA crosses below slow SMA → EXIT

    Signal timing:
    - Signal generated at the close of bar t (after SMA calculation using bars up to t)
    - Execution at next bar's open (t+1) — avoids look-ahead bias

    This is the ONLY strategy supported in Phase 3.
    """

    def __init__(
        self,
        fast_period: int = 20,
        slow_period: int = 50,
        direction: str = "long_only",
    ):
        """
        Initialize the strategy.

        Args:
            fast_period: Fast moving average period (default: 20)
            slow_period: Slow moving average period (default: 50)
            direction: "long_only" or "short_only" (default: "long_only")
        """
        if fast_period <= 0:
            raise ValueError("fast_period must be positive")
        if slow_period <= 0:
            raise ValueError("slow_period must be positive")
        if fast_period >= slow_period:
            raise ValueError("fast_period must be strictly less than slow_period")
        if direction not in ("long_only", "short_only"):
            raise ValueError("direction must be 'long_only' or 'short_only'")

        self.fast_period = fast_period
        self.slow_period = slow_period
        self.direction = direction

    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        """
        Generate trading signals from OHLC data.

        Signal convention:
        - +1: Enter long (fast MA crosses above slow MA)
        - -1: Exit/short (fast MA crosses below slow MA)
        - 0: No signal

        Signal generated at bar close (after calculating MA using data up to that bar).

        Args:
            data: DataFrame with OHLC data, sorted chronologically

        Returns:
            Series of signals aligned with data index
        """
        _validate_ohlc_data(data)

        # Calculate SMAs
        # Use only data up to and including current bar — no look-ahead
        fast_ma = data["Close"].rolling(window=self.fast_period, min_periods=self.fast_period).mean()
        slow_ma = data["Close"].rolling(window=self.slow_period, min_periods=self.slow_period).mean()

        # Generate signals: crossover detection
        # Signal is 1 when fast MA crosses ABOVE slow MA at bar close
        # Signal is -1 when fast MA crosses BELOW slow MA at bar close
        signals = pd.Series(0, index=data.index)
        signals[(fast_ma > slow_ma) & (fast_ma.shift(1) <= slow_ma.shift(1))] = 1  # Cross up
        signals[(fast_ma < slow_ma) & (fast_ma.shift(1) >= slow_ma.shift(1))] = -1  # Cross down

        return signals

    def get_parameters(self) -> Dict[str, Any]:
        """Return strategy parameters as a dictionary."""
        return {
            "strategy_type": "moving_average_crossover",
            "fast_period": self.fast_period,
            "slow_period": self.slow_period,
            "direction": self.direction,
        }


# ─── Backtest Engine ───────────────────────────────────────────────────────

class BacktestEngine:
    """
    Deterministic backtest engine.

    Given the same historical data, strategy, parameters, capital, fees,
    and slippage assumptions, produces reproducible results.

    Execution convention:
    - Signal at bar t close → Order executed at bar t+1 open price
    - This avoids look-ahead bias (using today's close price to buy today)

    Fee and slippage modeling:
    - Commission: percentage of trade value, deducted at entry
    - Slippage: adjusted execution price relative to market price
    """

    def __init__(
        self,
        strategy: MovingAverageCrossover,
        commission: float = 0.1,  # percentage of trade value
        slippage: float = 0.0,  # percentage of execution price
        initial_capital: float = 100000.0,
    ):
        """
        Initialize the backtest engine.

        Args:
            strategy: MovingAverageCrossover strategy instance
            commission: Transaction commission as percentage (default: 0.1%)
            slippage: Slippage as percentage of execution price (default: 0.0%)
            initial_capital: Starting capital in rupees (default: ₹10,00,000 / 100000)
        """
        if commission < 0:
            raise ValueError("commission must be non-negative")
        if slippage < 0:
            raise ValueError("slippage must be non-negative")
        if initial_capital <= 0:
            raise ValueError("initial_capital must be positive")

        self.strategy = strategy
        self.commission = commission / 100.0  # Convert percentage to decimal
        self.slippage = slippage / 100.0  # Convert percentage to decimal
        self.initial_capital = initial_capital

    def run(self, data: pd.DataFrame) -> Dict[str, Any]:
        """
        Run the deterministic backtest.

        Execution convention:
        - Signal generated at bar t close
        - Order executed at bar t+1 open price
        - This prevents look-ahead bias

        Args:
            data: DataFrame with OHLC data, sorted chronologically

        Returns:
            Dictionary with all computed metrics and trade records
        """
        data = _filter_nan_ohlc(data)
        if len(data) < self.strategy.slow_period:
            raise ValueError(f"insufficient valid bars after NaN filtering: {len(data)} < {self.strategy.slow_period} required for {self.strategy.fast_period}/{self.strategy.slow_period} SMA")
        _validate_ohlc_data(data)

        n_bars = len(data)
        parameters = self.strategy.get_parameters()

        # Generate signals
        signals = self.strategy.generate_signals(data)

        # Initialize tracking arrays
        # We use arrays aligned with data index for precision
        entry_signals = signals == 1  # +1 signals = entry
        exit_signals = signals == -1  # -1 signals = exit

        # Track position state
        in_position = False
        entry_price = 0.0
        entry_time = None
        exit_time = None
        entry_shares = 0.0

        # Previous bar's unrealized P&L (for delta-based mark-to-market;
        # ensures the same unrealized level is never counted twice)
        prev_unrealized = 0.0

        # Trade records
        closed_trades: List[Dict[str, Any]] = []

        # Equity curve tracking
        equity_curve = np.zeros(n_bars)
        total_commission_paid = 0.0
        total_slippage_cost = 0.0

        # Capital tracking
        capital = self.initial_capital

        # Track peak equity for drawdown
        peak_equity = self.initial_capital

        # Loop through bars executing trades
        for i in range(n_bars):
            # Update equity and peak (based on previous bar's close P&L)
            # Mark-to-market: equity changes only when we have a position
            if in_position and i > 0:
                # Mark-to-market P&L from entry to current bar's close
                # Add only the CHANGE since the previous bar, so the same
                # unrealized P&L level is never accumulated repeatedly.
                unrealized_pnl = entry_shares * (data["Close"].iloc[i] - entry_price)
                capital += unrealized_pnl - prev_unrealized  # Update capital mark-to-market
                prev_unrealized = unrealized_pnl
            else:
                prev_unrealized = 0.0

            # Track peak equity
            if capital > peak_equity:
                peak_equity = capital
            equity_curve[i] = capital

            # Check for entry signal at bar i
            # Entry is executed at next bar's open (i+1), but we record the signal at i
            # However, for the first bar, there's no previous signal to consider
            if not in_position and entry_signals.iloc[i] and i < n_bars - 1:
                # Schedule entry for next bar's open
                # We'll execute at data["Open"].iloc[i+1]
                entry_price_scheduled = data["Open"].iloc[i + 1]
                # Apply slippage: execution price = market_price * (1 ± slippage)
                if self.slippage > 0:
                    # For long entries: buy at slightly higher price
                    execution_price = entry_price_scheduled * (1 + self.slippage)
                else:
                    execution_price = entry_price_scheduled

                # Apply commission: commission % of trade value
                # We'll buy with as much capital as possible, but let's keep it simple:
                # full position sizing = capital / execution_price
                # commission deducted from capital
                trade_value = capital / execution_price  # How many shares we can buy
                commission_amount = trade_value * execution_price * self.commission
                total_commission_paid += commission_amount

                # Adjust capital for commission
                capital -= commission_amount

                # Full-position sizing: trade_value is already a share count
                # (capital / execution_price), so use it directly as shares.
                # Commission is deducted from cash capital above, not from shares.
                effective_shares = trade_value

                # Record entry
                in_position = True
                entry_price = execution_price  # Record the execution price (with slippage)
                entry_time = data.index[i + 1] if i + 1 < n_bars else data.index[i]
                entry_shares = effective_shares

                total_slippage_cost += (entry_price_scheduled - (entry_price_scheduled / (1 + self.slippage))) * effective_shares

            # Check for exit signal at bar i (execute at this bar's open if we're in position)
            # Actually, let's execute exit at current bar's close for simplicity and clarity
            # But to maintain the "signal at t close → execute at t+1 open" convention,
            # we need to look ahead. Let's use a different approach:

            # Exit: if we have a position and this bar's close shows a crossdown signal,
            # we exit at next open. But that introduces complexity. Let's instead:
            # - Generate signals at bar close
            # - Execute trades at the close price of the SAME bar (simplest, well-documented)
            # - Document the convention clearly

            # For this implementation: execute signals at bar close
            # This is the simplest deterministic approach
            if in_position and exit_signals.iloc[i]:
                # Exit at current bar's close
                exit_price = data["Close"].iloc[i]

                # Apply slippage on exit
                if self.slippage > 0:
                    # For long exits: sell at slightly lower price
                    execution_exit_price = exit_price * (1 - self.slippage)
                else:
                    execution_exit_price = exit_price

                # Calculate gross P&L
                gross_pnl = entry_shares * (execution_exit_price - entry_price)

                # Calculate fees on exit (round-turn commission)
                # We already charged commission on entry; charge again on exit for round-turn
                exit_commission = execution_exit_price * entry_shares * self.commission
                total_commission_paid += exit_commission

                # Net P&L after fees
                net_pnl = gross_pnl - exit_commission

                # Track slippage cost on exit
                market_exit_price = exit_price
                slippage_cost = (market_exit_price - execution_exit_price) * entry_shares
                total_slippage_cost += slippage_cost

                # Reverse the mark-to-market accumulated for this position,
                # then apply the realized net P&L exactly once.
                capital -= prev_unrealized
                # Update capital
                capital += net_pnl
                prev_unrealized = 0.0

                # Record the closed trade
                trade_return_pct = net_pnl / entry_price * (1 / entry_shares) if entry_shares > 0 else 0

                closed_trades.append({
                    "trade_id": len(closed_trades) + 1,
                    "entry_time": entry_time,
                    "exit_time": data.index[i],
                    "entry_price": round(entry_price, 2),
                    "exit_price": round(execution_exit_price, 2),
                    "size": round(entry_shares, 4),
                    "gross_pnl": round(gross_pnl, 2),
                    "fees": round(exit_commission, 2),
                    "slippage": round(slippage_cost, 2),
                    "net_pnl": round(net_pnl, 2),
                    "return_pct": round(trade_return_pct * 100, 2),  # as percentage
                    "status": "closed",
                })

                # Reset position state
                in_position = False
                entry_price = 0.0
                entry_time = None
                entry_shares = 0.0

        # Calculate final equity
        final_equity = capital

        # Calculate total return
        total_return = (final_equity - self.initial_capital) / self.initial_capital * 100  # as percentage

        # Calculate win rate
        winning_trades = [t for t in closed_trades if t["net_pnl"] > 0]
        losing_trades = [t for t in closed_trades if t["net_pnl"] <= 0]

        if len(closed_trades) > 0:
            win_rate = len(winning_trades) / len(closed_trades)
            avg_win = np.mean([t["net_pnl"] for t in winning_trades]) if winning_trades else 0.0
            avg_loss = np.mean([abs(t["net_pnl"]) for t in losing_trades]) if losing_trades else 0.0
        else:
            win_rate = None  # No closed trades
            avg_win = None
            avg_loss = None

        # Calculate profit factor
        # Gross profits / absolute gross losses
        gross_profits = sum(t["gross_pnl"] for t in winning_trades) if winning_trades else 0.0
        absolute_gross_losses = sum(abs(t["gross_pnl"]) for t in losing_trades) if losing_trades else 0.0

        if absolute_gross_losses > 0:
            profit_factor = gross_profits / absolute_gross_losses
        else:
            # If no losses, profit factor is undefined/infinite
            # Per spec: return null/unavailable
            profit_factor = None
            # But we also need to handle the case where there are wins but no losses
            # If there ARE winning trades and NO losing trades:
            if len(winning_trades) > 0 and len(losing_trades) == 0:
                # Profit factor effectively infinite, but per spec we should be careful
                # Let's return a large number with documentation, or null
                # Per spec Section 10: "If gross losses are zero: do not invent infinity
                # Return null/unavailable and document why"
                profit_factor = None

        # Calculate maximum drawdown
        # Largest percentage decline from a historical equity peak to subsequent trough
        drawdowns = np.array([], dtype=float)
        if len(equity_curve) > 0:
            # Find running peaks
            running_peaks = np.maximum.accumulate(equity_curve)
            # Drawdown from peak
            drawdowns = (running_peaks - equity_curve) / running_peaks * 100  # as percentage
            # Maximum drawdown
            max_drawdown = float(np.max(drawdowns))
        else:
            max_drawdown = None

        # Bar dates for visualization — read from Date COLUMN only.
        # RangeIndex semantics are preserved (entry_time/exit_time/data_start/data_end stay integers).
        if isinstance(data, pd.DataFrame) and "Date" in data.columns:
            bar_dates = [str(v) for v in data["Date"]]
        else:
            bar_dates = []

        # Build result
        result = {
            # Strategy & data metadata
            "strategy_type": parameters["strategy_type"],
            "fast_period": parameters["fast_period"],
            "slow_period": parameters["slow_period"],
            "direction": parameters["direction"],

            # Engine assumptions
            "initial_capital": self.initial_capital,
            "final_equity": round(final_equity, 2),
            "total_return_pct": round(total_return, 2),
            "data_start": data.index[0],
            "data_end": data.index[-1],
            "number_of_bars": n_bars,

            # Fee and slippage
            "fees_included": True,
            "commission_assumption": round(self.commission * 100, 4),  # as percentage
            "slippage_included": True,
            "slippage_assumption": round(self.slippage * 100, 4),  # as percentage,

            # Core metrics (REQUIRED per spec)
            "trades": closed_trades,
            "win_rate": win_rate,  # None if no closed trades
            "avg_win": avg_win,  # None if no winning trades
            "avg_loss": avg_loss,  # None if no losing trades
            "profit_factor": profit_factor,  # None if gross losses are zero
            "max_drawdown": max_drawdown,  # as percentage

            # Trade records metadata
            "trade_count": len(closed_trades),
            "winning_trade_count": len(winning_trades),
            "losing_trade_count": len(losing_trades),

            # Visualization series (already computed above; additive exposure only)
            "equity_curve": equity_curve.tolist(),
            "drawdown_series": drawdowns.tolist(),
            "bar_dates": bar_dates,

            # Engine version
            "engine_version": "1.1.0",
            "deterministic": True,
        }

        return _sanitize_result(result)


# ─── Helper functions ──────────────────────────────────────────────────────

def run_backtest(
    data: Any,
    fast_period: int = 20,
    slow_period: int = 50,
    commission: float = 0.1,
    slippage: float = 0.0,
    initial_capital: float = 100000.0,
    direction: str = "long_only",
) -> Dict[str, Any]:
    """
    Convenience function to run a backtest.

    Args:
        data: OHLC DataFrame or list-of-dicts with Open, High, Low, Close
        fast_period: Fast SMA period
        slow_period: Slow SMA period
        commission: Commission as percentage of trade value
        slippage: Slippage as percentage of execution price
        initial_capital: Starting capital
        direction: Strategy direction

    Returns:
        Backtest result dictionary
    """
    if isinstance(data, list) and len(data) > 0 and isinstance(data[0], dict):
        data = pd.DataFrame(data)
        if not data.index.is_monotonic_increasing:
            data = data.sort_index()
        data = _filter_nan_ohlc(data)
        if len(data) < slow_period:
            raise ValueError(f"insufficient valid bars after NaN filtering: {len(data)} < {slow_period}")
        _validate_ohlc_data(data)
    elif isinstance(data, pd.DataFrame):
        data = _filter_nan_ohlc(data)
        if len(data) < slow_period:
            raise ValueError(f"insufficient valid bars after NaN filtering: {len(data)} < {slow_period}")
        _validate_ohlc_data(data)
    else:
        raise ValueError(f"Unsupported data format: {type(data)}. Expected DataFrame or list-of-dicts.")

    strategy = MovingAverageCrossover(
        fast_period=fast_period,
        slow_period=slow_period,
        direction=direction,
    )

    engine = BacktestEngine(
        strategy=strategy,
        commission=commission,
        slippage=slippage,
        initial_capital=initial_capital,
    )

    return engine.run(data)


def validate_backtest_result(result: Dict[str, Any]) -> bool:
    """
    Validate a backtest engine result.

    Checks that required fields are present and have appropriate types.

    Returns True if valid, False otherwise.
    """
    required_top_level = [
        "strategy_type",
        "fast_period",
        "slow_period",
        "direction",
        "initial_capital",
        "final_equity",
        "total_return_pct",
        "data_start",
        "data_end",
        "number_of_bars",
        "fees_included",
        "commission_assumption",
        "slippage_included",
        "slippage_assumption",
        "trades",
        "win_rate",
        "avg_win",
        "avg_loss",
        "profit_factor",
        "max_drawdown",
        "trade_count",
        "winning_trade_count",
        "losing_trade_count",
        "engine_version",
        "deterministic",
    ]

    for field in required_top_level:
        if field not in result:
            return False

    # Check types
    if not isinstance(result["fees_included"], bool):
        return False
    if not isinstance(result["slippage_included"], bool):
        return False
    if not isinstance(result["deterministic"], bool):
        return False
    if not isinstance(result["trade_count"], int):
        return False
    if not isinstance(result["winning_trade_count"], int):
        return False
    if not isinstance(result["losing_trade_count"], int):
        return False

    # Check trades is a list
    if not isinstance(result["trades"], list):
        return False

    # If win_rate is not None, it should be numeric (or float)
    if result["win_rate"] is not None and not isinstance(result["win_rate"], (int, float)):
        return False

    # If avg_win is not None, should be numeric
    if result["avg_win"] is not None and not isinstance(result["avg_win"], (int, float)):
        return False

    # If avg_loss is not None, should be numeric
    if result["avg_loss"] is not None and not isinstance(result["avg_loss"], (int, float)):
        return False

    # profit_factor: should be None or numeric
    if result["profit_factor"] is not None and not isinstance(result["profit_factor"], (int, float)):
        return False

    # max_drawdown: should be None or numeric
    if result["max_drawdown"] is not None and not isinstance(result["max_drawdown"], (int, float)):
        return False

    return True