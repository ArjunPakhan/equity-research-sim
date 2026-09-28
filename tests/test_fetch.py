"""
Unit tests for data/fetch.py
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
import pandas as pd
from datetime import datetime, timezone

# Import the module under test
import sys
sys.path.insert(0, str(__file__).replace("tests/test_fetch.py", ""))

from data.fetch import (
    _normalize_ticker,
    _get_cache_path,
    _read_cache,
    _write_cache,
    _is_cache_valid,
    get_ohlc,
    get_fundamentals,
    get_news,
    get_all_data,
    validate_ticker,
    clear_cache,
    DataFetchError,
    CacheError,
    DEFAULT_PERIOD,
    DEFAULT_INTERVAL,
    VALID_TICKERS,
)


class TestTickerNormalization:
    """Tests for ticker normalization."""

    def test_normalize_nse_default(self):
        """Test default NSE normalization."""
        assert _normalize_ticker("RELIANCE") == "RELIANCE.NS"
        assert _normalize_ticker("TCS") == "TCS.NS"
        assert _normalize_ticker("infy") == "INFY.NS"

    def test_normalize_bse_explicit(self):
        """Test explicit BSE normalization."""
        assert _normalize_ticker("RELIANCE", "BO") == "RELIANCE.BO"
        assert _normalize_ticker("TCS", "BO") == "TCS.BO"

    def test_already_normalized_ns(self):
        """Test ticker already with .NS suffix."""
        assert _normalize_ticker("RELIANCE.NS") == "RELIANCE.NS"

    def test_already_normalized_bo(self):
        """Test ticker already with .BO suffix."""
        assert _normalize_ticker("RELIANCE.BO") == "RELIANCE.BO"

    def test_empty_ticker_raises(self):
        """Test empty ticker raises ValueError."""
        with pytest.raises(ValueError):
            _normalize_ticker("")

    def test_whitespace_handling(self):
        """Test whitespace is stripped."""
        assert _normalize_ticker("  RELIANCE  ") == "RELIANCE.NS"


class TestCachePath:
    """Tests for cache path generation."""

    def test_basic_cache_path(self):
        """Test basic cache path generation."""
        path = _get_cache_path("RELIANCE.NS", "ohlc")
        assert "RELIANCE_NS_ohlc" in str(path)
        assert path.suffix == ".parquet"

    def test_cache_path_with_params(self):
        """Test cache path with parameters."""
        path = _get_cache_path("RELIANCE.NS", "ohlc", period="1y", interval="1d")
        assert "period=1y" in str(path)
        assert "interval=1d" in str(path)

    def test_cache_path_sanitization(self):
        """Test special characters are sanitized."""
        path = _get_cache_path("RELIANCE.NS", "ohlc", period="1y/1mo")
        assert "/" not in str(path) or "_" in str(path)


class TestCacheOperations:
    """Tests for cache read/write operations."""

    @pytest.fixture
    def sample_df(self):
        """Create sample DataFrame for testing."""
        return pd.DataFrame({
            "Date": pd.date_range("2024-01-01", periods=5),
            "Open": [100, 101, 102, 103, 104],
            "High": [105, 106, 107, 108, 109],
            "Low": [99, 100, 101, 102, 103],
            "Close": [104, 105, 106, 107, 108],
            "Volume": [1000, 1100, 1200, 1300, 1400],
        })

    def test_write_and_read_cache(self, sample_df, tmp_path):
        """Test writing and reading cache."""
        from data.fetch import CACHE_DIR
        import data.fetch as fetch_module

        # Temporarily redirect cache dir
        original_cache = fetch_module.CACHE_DIR
        fetch_module.CACHE_DIR = tmp_path

        try:
            cache_path = tmp_path / "test_cache.parquet"
            metadata = {
                "cached_at": datetime.now(timezone.utc).isoformat(),
                "ticker": "TEST.NS",
                "data_type": "ohlc",
            }

            _write_cache(cache_path, sample_df, metadata)
            assert cache_path.exists()

            result = _read_cache(cache_path)
            assert result is not None
            assert "data" in result
            assert "cached_at" in result
            assert len(result["data"]) == 5
        finally:
            fetch_module.CACHE_DIR = original_cache

    def test_read_nonexistent_cache(self, tmp_path):
        """Reading nonexistent cache returns None."""
        cache_path = tmp_path / "nonexistent.parquet"
        result = _read_cache(cache_path)
        assert result is None

    def test_is_cache_valid_fresh(self, sample_df, tmp_path):
        """Test cache validity for fresh cache."""
        from data.fetch import CACHE_DIR
        import data.fetch as fetch_module

        original_cache = fetch_module.CACHE_DIR
        fetch_module.CACHE_DIR = tmp_path

        try:
            cache_path = tmp_path / "fresh_cache.parquet"
            metadata = {
                "cached_at": datetime.now(timezone.utc).isoformat(),
                "ticker": "TEST.NS",
                "data_type": "ohlc",
            }
            _write_cache(cache_path, sample_df, metadata)

            assert _is_cache_valid(cache_path, max_age_hours=24) is True
        finally:
            fetch_module.CACHE_DIR = original_cache

    def test_is_cache_valid_stale(self, sample_df, tmp_path):
        """Test cache validity for stale cache."""
        from data.fetch import CACHE_DIR
        import data.fetch as fetch_module

        original_cache = fetch_module.CACHE_DIR
        fetch_module.CACHE_DIR = tmp_path

        try:
            cache_path = tmp_path / "stale_cache.parquet"
            # Old timestamp
            old_time = datetime(2020, 1, 1, tzinfo=timezone.utc).isoformat()
            metadata = {
                "cached_at": old_time,
                "ticker": "TEST.NS",
                "data_type": "ohlc",
            }
            _write_cache(cache_path, sample_df, metadata)

            assert _is_cache_valid(cache_path, max_age_hours=24) is False
        finally:
            fetch_module.CACHE_DIR = original_cache


class TestTickerValidation:
    """Tests for ticker validation."""

    def test_valid_tickers(self):
        """Test known valid tickers pass validation."""
        for ticker in VALID_TICKERS:
            assert validate_ticker(ticker) is True
            assert validate_ticker(ticker.lower()) is True

    def test_invalid_tickers(self):
        """Test unknown tickers fail validation."""
        assert validate_ticker("INVALID") is False
        assert validate_ticker("AAPL") is False
        assert validate_ticker("") is False


class TestOHLCFetching:
    """Tests for OHLC data fetching (mocked)."""

    @patch("data.fetch.yf.Ticker")
    def test_get_ohlc_success(self, mock_ticker_class):
        """Test successful OHLC fetch."""
        # Setup mock
        mock_stock = Mock()
        mock_ticker_class.return_value = mock_stock

        # Create mock history data
        dates = pd.date_range("2024-01-01", periods=10, freq="D")
        mock_hist = pd.DataFrame({
            "Open": [100 + i for i in range(10)],
            "High": [105 + i for i in range(10)],
            "Low": [99 + i for i in range(10)],
            "Close": [104 + i for i in range(10)],
            "Volume": [1000 * (i + 1) for i in range(10)],
        }, index=dates)
        mock_stock.history.return_value = mock_hist

        # Call function
        result = get_ohlc("RELIANCE", use_cache=False)

        # Assertions
        assert result["ticker"] == "RELIANCE"
        assert result["resolved_ticker"] == "RELIANCE.NS"
        assert result["source"] == "yahoo_finance"
        assert len(result["data"]) == 10
        assert all(k in result["data"][0] for k in ["Open", "High", "Low", "Close", "Volume"])

    @patch("data.fetch.yf.Ticker")
    def test_get_ohlc_empty_response(self, mock_ticker_class):
        """Test handling of empty OHLC response."""
        mock_stock = Mock()
        mock_ticker_class.return_value = mock_stock
        mock_stock.history.return_value = pd.DataFrame()  # Empty

        with pytest.raises(DataFetchError):
            get_ohlc("INVALID", use_cache=False)

    @patch("data.fetch.yf.Ticker")
    def test_get_ohlc_missing_columns(self, mock_ticker_class):
        """Test handling of missing OHLC columns."""
        mock_stock = Mock()
        mock_ticker_class.return_value = mock_stock

        # DataFrame missing required columns
        mock_hist = pd.DataFrame({"Open": [100], "Close": [101]})
        mock_stock.history.return_value = mock_hist

        with pytest.raises(DataFetchError):
            get_ohlc("RELIANCE", use_cache=False)


class TestFundamentalsFetching:
    """Tests for fundamentals data fetching (mocked)."""

    @patch("data.fetch.yf.Ticker")
    def test_get_fundamentals_success(self, mock_ticker_class):
        """Test successful fundamentals fetch."""
        mock_stock = Mock()
        mock_ticker_class.return_value = mock_stock
        mock_stock.info = {
            "longName": "Reliance Industries Ltd",
            "sector": "Energy",
            "marketCap": 1500000000000,
            "trailingPE": 25.5,
            "priceToBook": 2.1,
            "dividendYield": 0.003,
        }

        result = get_fundamentals("RELIANCE", use_cache=False)

        assert result["ticker"] == "RELIANCE"
        assert result["resolved_ticker"] == "RELIANCE.NS"
        assert "longName" in result["data"]
        assert result["data"]["sector"] == "Energy"

    @patch("data.fetch.yf.Ticker")
    def test_get_fundamentals_empty(self, mock_ticker_class):
        """Test handling of empty fundamentals."""
        mock_stock = Mock()
        mock_ticker_class.return_value = mock_stock
        mock_stock.info = {}

        with pytest.raises(DataFetchError):
            get_fundamentals("INVALID", use_cache=False)


class TestNewsFetching:
    """Tests for news data fetching (mocked)."""

    @patch("data.fetch.yf.Ticker")
    def test_get_news_success(self, mock_ticker_class):
        """Test successful news fetch."""
        mock_stock = Mock()
        mock_ticker_class.return_value = mock_stock
        mock_stock.news = [
            {
                "title": "Test News 1",
                "publisher": "Test Publisher",
                "link": "http://example.com/1",
                "providerPublishTime": 1704067200,  # 2024-01-01
                "type": "STORY",
            },
            {
                "title": "Test News 2",
                "publisher": "Another Publisher",
                "link": "http://example.com/2",
                "providerPublishTime": 1704153600,  # 2024-01-02
                "type": "STORY",
            },
        ]

        result = get_news("RELIANCE", use_cache=False)

        assert result["ticker"] == "RELIANCE"
        assert len(result["data"]) == 2
        assert result["data"][0]["title"] == "Test News 1"
        assert "providerPublishTime" in result["data"][0]

    @patch("data.fetch.yf.Ticker")
    def test_get_news_empty(self, mock_ticker_class):
        """Test handling of empty news."""
        mock_stock = Mock()
        mock_ticker_class.return_value = mock_stock
        mock_stock.news = []

        result = get_news("RELIANCE", use_cache=False)
        assert result["data"] == []


class TestGetAllData:
    """Tests for combined data fetching."""

    @patch("data.fetch.get_ohlc")
    @patch("data.fetch.get_fundamentals")
    @patch("data.fetch.get_news")
    def test_get_all_data(self, mock_news, mock_fund, mock_ohlc):
        """Test get_all_data calls all fetchers."""
        mock_ohlc.return_value = {"data": [{"Close": 100}], "source": "yahoo_finance"}
        mock_fund.return_value = {"data": {"sector": "Energy"}, "source": "yahoo_finance"}
        mock_news.return_value = {"data": [], "source": "yahoo_finance"}

        result = get_all_data("RELIANCE", use_cache=False)

        assert "ohlc" in result
        assert "fundamentals" in result
        assert "news" in result
        assert result["ticker"] == "RELIANCE"


class TestClearCache:
    """Tests for cache clearing."""

    def test_clear_cache_specific_ticker(self, tmp_path):
        """Test clearing cache for specific ticker."""
        from data.fetch import CACHE_DIR
        import data.fetch as fetch_module

        original_cache = fetch_module.CACHE_DIR
        fetch_module.CACHE_DIR = tmp_path

        try:
            # Create some cache files
            (tmp_path / "RELIANCE_NS_ohlc_period=1y.parquet").write_text("dummy")
            (tmp_path / "TCS_NS_ohlc_period=1y.parquet").write_text("dummy")
            (tmp_path / "RELIANCE_NS_fundamentals.parquet").write_text("dummy")

            deleted = clear_cache(ticker="RELIANCE")
            assert deleted == 2

            remaining = list(tmp_path.glob("*.parquet"))
            assert len(remaining) == 1
            assert "TCS" in str(remaining[0])
        finally:
            fetch_module.CACHE_DIR = original_cache


# Integration test markers
pytestmark = pytest.mark.unit


def test_regression_fundamentals_data_is_dict_after_cache_read():
    """Regression test for: 'list' object has no attribute 'keys'.

    Verifies that fundamentals data read from cache is a dict, not a list,
    so that .keys() and other dict methods work correctly.

    This bug occurred because _read_cache() returned data as a list of records
    (from df.to_dict(orient="records")), but fundamentals data is inherently
    a dict of key-value pairs. When cached and read back, the list-of-one-record
    format caused .keys() to fail.
    """
    from data.fetch import get_fundamentals, CACHE_DIR
    import data.fetch as fetch_module

    import tempfile
    import os

    # Fetch fundamentals (populates cache)
    result = get_fundamentals("RELIANCE", use_cache=True)

    # Read cache directly and verify data type
    cache_path = CACHE_DIR / "RELIANCE_NS_fundamentals.parquet"
    cached = fetch_module._read_cache(cache_path)

    # The fix: cached["data"] should be a dict, not a list
    assert isinstance(cached["data"], dict), (
        f"Expected fundamentals data to be a dict, got {type(cached['data']).__name__}"
    )

    # .keys() should work on the data
    assert hasattr(cached["data"], "keys"), "Fundamentals data should have .keys() method"
    assert "longName" in cached["data"], "Fundamentals data should contain longName"

    # Verify the data is the same as the original result
    assert cached["data"]["longName"] == result["data"]["longName"]
    assert cached["data"]["sector"] == result["data"]["sector"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])