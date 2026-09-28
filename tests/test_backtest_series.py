import math
import numpy as np
import pandas as pd
import pytest

from backtest_engine import BacktestEngine, MovingAverageCrossover
from backtest_engine.runner import run_backtest_from_data


def _make_df(n=240, with_date=True):
    """Sine-wave OHLC on default RangeIndex (Date as column), deterministic."""
    idx = np.arange(n)
    closes = 100 + 40 * np.sin(idx / 12.0)
    opens = np.roll(closes, 1)
    opens[0] = closes[0]
    highs = np.maximum(opens, closes) + 1
    lows = np.minimum(opens, closes) - 1
    data = {
        "Open": opens,
        "High": highs,
        "Low": lows,
        "Close": closes,
        "Volume": np.full(n, 1000),
    }
    if with_date:
        data["Date"] = [str(pd.Timestamp("2024-01-01") + pd.Timedelta(days=i)) for i in range(n)]
    return pd.DataFrame(data)


def _run(with_date=True):
    df = _make_df(with_date=with_date)
    eng = BacktestEngine(
        strategy=MovingAverageCrossover(20, 50),
        commission=0.1,
        slippage=0.05,
        initial_capital=100000,
    )
    return eng.run(df), df


def _is_int_bar_index(v):
    return isinstance(v, (int, np.integer)) and not isinstance(v, bool)


# 1. equity_curve exists
def test_equity_curve_exists():
    res, _ = _run()
    assert "equity_curve" in res
    assert isinstance(res["equity_curve"], list)


# 2. drawdown_series exists
def test_drawdown_series_exists():
    res, _ = _run()
    assert "drawdown_series" in res
    assert isinstance(res["drawdown_series"], list)


# 3. bar_dates exists when Date is available
def test_bar_dates_exists_with_date_column():
    res, df = _run(with_date=True)
    assert "bar_dates" in res
    assert len(res["bar_dates"]) == len(df)


def test_bar_dates_empty_without_date_column():
    res, _ = _run(with_date=False)
    assert res["bar_dates"] == []


# 4. equity_curve length == number_of_bars
def test_equity_curve_length_equals_number_of_bars():
    res, _ = _run()
    assert len(res["equity_curve"]) == res["number_of_bars"]


# 5. drawdown_series length == number_of_bars
def test_drawdown_series_length_equals_number_of_bars():
    res, _ = _run()
    assert len(res["drawdown_series"]) == res["number_of_bars"]


# 6. bar_dates length == number_of_bars
def test_bar_dates_length_equals_number_of_bars():
    res, _ = _run()
    assert len(res["bar_dates"]) == res["number_of_bars"]


# 7. trade entry_time remains an integer bar index
def test_trade_entry_time_is_integer_bar_index():
    res, _ = _run()
    assert res["trade_count"] > 0, "expected at least one closed trade"
    for t in res["trades"]:
        assert _is_int_bar_index(t["entry_time"]), (
            f"entry_time must be int bar index, got {t['entry_time']!r}"
        )


# 8. trade exit_time remains an integer bar index
def test_trade_exit_time_is_integer_bar_index():
    res, _ = _run()
    assert res["trade_count"] > 0
    for t in res["trades"]:
        assert _is_int_bar_index(t["exit_time"]), (
            f"exit_time must be int bar index, got {t['exit_time']!r}"
        )


# 9. data_start / data_end remain integer bar indexes
def test_data_start_data_end_are_integer_bar_indexes():
    res, _ = _run()
    assert _is_int_bar_index(res["data_start"]), res["data_start"]
    assert _is_int_bar_index(res["data_end"]), res["data_end"]
    assert res["data_start"] == 0
    assert res["data_end"] == res["number_of_bars"] - 1


# 10. all new numeric values are finite
def test_new_series_values_are_finite():
    res, _ = _run()
    for name in ("equity_curve", "drawdown_series"):
        for v in res[name]:
            if v is None:
                continue
            assert isinstance(v, (int, float)) and math.isfinite(v), (
                f"{name} has non-finite value: {v!r}"
            )


# Pass-through: runner keeps the three fields
def test_runner_passes_through_series_fields():
    df = _make_df(with_date=True)
    records = df.to_dict(orient="records")
    result = run_backtest_from_data(records, fast_period=20, slow_period=50)
    assert "equity_curve" in result
    assert "drawdown_series" in result
    assert "bar_dates" in result
    assert len(result["equity_curve"]) == result["number_of_bars"]
    assert len(result["bar_dates"]) == result["number_of_bars"]
    for v in result["equity_curve"]:
        if v is not None:
            assert math.isfinite(v)
