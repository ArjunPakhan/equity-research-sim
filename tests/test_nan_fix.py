import math
import pandas as pd
import pytest


def _make_ohlc(n=60, with_trailing_nan=False):
    dates = pd.date_range("2024-01-01", periods=n, freq="D")
    df = pd.DataFrame({
        "Open": [100 + i * 0.5 for i in range(n)],
        "High": [101 + i * 0.5 for i in range(n)],
        "Low": [99 + i * 0.5 for i in range(n)],
        "Close": [100 + i * 0.5 for i in range(n)],
        "Volume": [1000000] * n,
    }, index=dates)
    if with_trailing_nan:
        nan_row = pd.DataFrame({"Open": [float("nan")], "High": [float("nan")], "Low": [float("nan")], "Close": [float("nan")], "Volume": [1000]}, index=[dates[-1] + pd.Timedelta(days=1)])
        df = pd.concat([df, nan_row])
    return df


def test_trailing_nan_excluded():
    from backtest_engine import BacktestEngine, MovingAverageCrossover
    df = _make_ohlc(60, with_trailing_nan=True)
    assert len(df) == 61
    eng = BacktestEngine(strategy=MovingAverageCrossover(20, 50), commission=0.1, slippage=0.05, initial_capital=100000)
    result = eng.run(df)
    assert result["number_of_bars"] == 60


def test_final_equity_finite_after_nan():
    from backtest_engine import BacktestEngine, MovingAverageCrossover
    df = _make_ohlc(60, with_trailing_nan=True)
    eng = BacktestEngine(strategy=MovingAverageCrossover(20, 50))
    result = eng.run(df)
    assert result["final_equity"] is not None
    assert math.isfinite(result["final_equity"])


def test_total_return_finite_after_nan():
    from backtest_engine import BacktestEngine, MovingAverageCrossover
    df = _make_ohlc(60, with_trailing_nan=True)
    result = BacktestEngine(strategy=MovingAverageCrossover(20, 50)).run(df)
    assert result["total_return_pct"] is not None
    assert math.isfinite(result["total_return_pct"])


def test_max_drawdown_finite_after_nan():
    from backtest_engine import BacktestEngine, MovingAverageCrossover
    df = _make_ohlc(60, with_trailing_nan=True)
    result = BacktestEngine(strategy=MovingAverageCrossover(20, 50)).run(df)
    assert result["max_drawdown"] is not None
    assert math.isfinite(result["max_drawdown"])


def test_api_post_runs_with_nan_row():
    import tempfile, os
    os.environ["AUDIT_DB_PATH"] = tempfile.mktemp(suffix=".db")
    from fastapi.testclient import TestClient
    from unittest.mock import patch
    from api.main import app

    df = _make_ohlc(60, with_trailing_nan=True)
    ohlc_list = df.reset_index().to_dict(orient="records")
    for r in ohlc_list:
        r["Date"] = r["index"]
        del r["index"]

    mock_data = {
        "ticker": "TEST",
        "resolved_ticker": "TEST.NS",
        "ohlc": {"data": ohlc_list, "source": "mock", "retrieved_at": "now"},
        "fundamentals": {"data": {}, "source": "mock", "retrieved_at": "now"},
        "news": {"data": [], "source": "mock", "retrieved_at": "now"},
        "retrieved_at": "now",
    }
    with patch("data.fetch.get_all_data", return_value=mock_data):
        c = TestClient(app)
        r = c.post("/runs", json={"ticker": "TEST"})
        assert r.status_code == 200, r.text
        rid = r.json()["run_id"]
        bt = c.get(f"/runs/{rid}/backtest")
        assert bt.status_code == 200
        j = bt.json()
        import json
        json.dumps(j, allow_nan=False)
        assert math.isfinite(j["final_equity"])
    try:
        os.remove(os.environ["AUDIT_DB_PATH"])
    except Exception:
        pass
    os.environ.pop("AUDIT_DB_PATH", None)


def test_zero_preserved_not_none():
    from backtest_engine import _sanitize_result
    from api.main import _sanitize
    assert _sanitize_result(0.0) == 0.0
    assert _sanitize(0.0) == 0.0
    assert _sanitize({"a": 0.0, "b": 1})["a"] == 0.0
    d = _sanitize({"win_rate": 0.0, "profit_factor": 0.0})
    assert d["win_rate"] == 0.0
    assert d["profit_factor"] == 0.0


def test_insufficient_data_honest():
    from backtest_engine import BacktestEngine, MovingAverageCrossover
    df = _make_ohlc(10, with_trailing_nan=False)
    eng = BacktestEngine(strategy=MovingAverageCrossover(20, 50))
    with pytest.raises(ValueError, match="insufficient valid bars"):
        eng.run(df)


def test_list_nan_filtering():
    from backtest_engine.runner import run_backtest_from_data
    df = _make_ohlc(60, with_trailing_nan=True)
    lst = df.reset_index().to_dict(orient="records")
    for r in lst:
        r["Date"] = r.pop("index")
    for r in lst:
        for k in list(r.keys()):
            if k not in ("Open", "High", "Low", "Close", "Volume", "Date"):
                del r[k]
    result = run_backtest_from_data(lst, fast_period=20, slow_period=50)
    assert result["number_of_bars"] == 60
    assert math.isfinite(result["final_equity"])
