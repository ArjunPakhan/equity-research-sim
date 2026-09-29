"""
Regression tests for backtest trade-accounting corrections.

Covers: full-position share sizing (no double division by price),
entry notional, per-side 0.1% commission semantics, delta-based
mark-to-market (no level re-accumulation), exact-once exit accounting,
and unchanged 20/50 signal timing.

Deterministic synthetic OHLC only — no yfinance, no network, no LLM.
"""
import pandas as pd
import pytest

from agents.backtest_agent import run_backtest_agent, validate_backtest_output
from backtest_engine import BacktestEngine, MovingAverageCrossover


def _make_step_df():
    """80-bar synthetic series: flat 1000, step to 3000 at bar 55,
    controlled closes 2000/2010/2020 at bars 56-58, back to 1000.
    Yields exactly one +1 signal (bar 55) and one -1 signal (bar 77)."""
    closes = [1000.0] * 55 + [3000.0, 2000.0, 2010.0, 2020.0] + [1000.0] * 21
    opens = [1000.0] * 56 + [2000.0, 2010.0, 2020.0] + [1000.0] * 21
    assert len(closes) == 80 and len(opens) == 80
    return pd.DataFrame({
        "Open": opens,
        "High": [max(o, c) + 1.0 for o, c in zip(opens, closes)],
        "Low": [min(o, c) - 1.0 for o, c in zip(opens, closes)],
        "Close": closes,
    })


def _run(commission=0.0, slippage=0.0):
    eng = BacktestEngine(
        strategy=MovingAverageCrossover(20, 50),
        commission=commission,
        slippage=slippage,
        initial_capital=100000.0,
    )
    return eng.run(_make_step_df())


def test_signal_timing_entry_bar_and_price():
    res = _run()
    assert res["trade_count"] == 1
    t = res["trades"][0]
    assert t["entry_time"] == 56
    assert t["entry_price"] == 2000.0
    assert t["exit_time"] == 77
    assert res["fast_period"] == 20
    assert res["slow_period"] == 50


def test_strategy_signal_bar_unchanged():
    sig = MovingAverageCrossover(20, 50).generate_signals(_make_step_df())
    assert list(sig[sig == 1].index) == [55]
    assert list(sig[sig == -1].index) == [77]
    assert (sig.iloc[:55] == 0).all()


def test_full_position_share_count():
    t = _run()["trades"][0]
    assert t["size"] == 50.0


def test_entry_notional_equals_capital():
    t = _run()["trades"][0]
    assert t["size"] * t["entry_price"] == 100000.0


def test_entry_commission_is_0_1_pct_of_entry_notional():
    res = _run(commission=0.1)
    # bar 57: 100 entry commission deducted, first 500 MTM delta added
    assert res["equity_curve"][57] == pytest.approx(100000.0 - 100.0 + 500.0)


def test_exit_commission_is_0_1_pct_of_exit_notional():
    res = _run(commission=0.1)
    t = res["trades"][0]
    # exit executes at bar-77 close = 1000.0 with 50 shares
    assert t["fees"] == pytest.approx(round(1000.0 * 50.0 * 0.001, 2))
    assert t["net_pnl"] == pytest.approx(t["gross_pnl"] - t["fees"])


def test_unrealized_pnl_added_as_daily_delta_only():
    res = _run()
    eq = res["equity_curve"]
    assert eq[56] == 100000.0
    assert eq[57] - eq[56] == 500.0
    assert eq[58] - eq[57] == 500.0
    assert eq[58] == 101000.0


def test_exit_accounted_exactly_once():
    res = _run()
    t = res["trades"][0]
    assert t["gross_pnl"] == -50000.0
    assert t["fees"] == 0.0
    assert t["net_pnl"] == -50000.0
    assert res["final_equity"] == 50000.0
    assert all(v == 50000.0 for v in res["equity_curve"][78:])


def test_engine_version_bumped():
    assert _run()["engine_version"] == "1.1.0"


def test_backtest_agent_exposes_engine_version():
    records = _make_step_df().to_dict(orient="records")
    out = run_backtest_agent({}, records, "RELIANCE")
    assert out["is_mock"] is False
    assert out["engine_version"] == "1.1.0"
    assert out["trade_count"] == 1
    assert validate_backtest_output(out) is True
