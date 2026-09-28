"""
Data fetch module for Indian equity market data.

Provides functions to retrieve OHLC, fundamentals, and news data for NSE/BSE tickers.
Implements local caching to avoid repeated API calls.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import pandas as pd
import yfinance as yf

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Cache directory
CACHE_DIR = Path(__file__).parent / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Default period and interval for OHLC data
DEFAULT_PERIOD = "1y"
DEFAULT_INTERVAL = "1d"

# Valid NSE tickers for validation
VALID_TICKERS = {"RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK"}


class DataFetchError(Exception):
    """Exception raised when data fetching fails."""
    pass


class CacheError(Exception):
    """Exception raised when cache operations fail."""
    pass


def _normalize_ticker(ticker: str, exchange: str = "NS") -> str:
    """
    Normalize ticker to yfinance format.

    Args:
        ticker: Raw ticker symbol (e.g., "RELIANCE")
        exchange: Exchange suffix, "NS" for NSE, "BO" for BSE

    Returns:
        Normalized ticker with exchange suffix (e.g., "RELIANCE.NS")
    """
    ticker = ticker.strip().upper()
    if not ticker:
        raise ValueError("Ticker cannot be empty")

    # Already has exchange suffix
    if ticker.endswith(".NS") or ticker.endswith(".BO"):
        return ticker

    # Add default exchange suffix
    suffix = ".NS" if exchange == "NS" else ".BO"
    return f"{ticker}{suffix}"


def _get_cache_path(ticker: str, data_type: str, **params) -> Path:
    """
    Generate deterministic cache file path.

    Args:
        ticker: Normalized ticker symbol
        data_type: Type of data ("ohlc", "fundamentals", "news")
        **params: Additional parameters for cache key (period, interval, etc.)

    Returns:
        Path to cache file
    """
    # Create cache key from parameters
    param_str = "_".join(f"{k}={v}" for k, v in sorted(params.items()))
    if param_str:
        cache_key = f"{ticker}_{data_type}_{param_str}"
    else:
        cache_key = f"{ticker}_{data_type}"

    # Sanitize for filesystem
    cache_key = cache_key.replace("/", "_").replace(":", "_").replace(".", "_")
    return CACHE_DIR / f"{cache_key}.parquet"


def _read_cache(cache_path: Path) -> Optional[Dict[str, Any]]:
    """
    Read data from cache file.

    Args:
        cache_path: Path to cache file

    Returns:
        Cached data dictionary or None if not found/invalid
    """
    if not cache_path.exists():
        return None

    try:
        df = pd.read_parquet(cache_path)
        if df.empty:
            return None

        # Convert DataFrame to dict and extract metadata
        data = df.to_dict(orient="records")
        # If data is a list with a single dict record (e.g. fundamentals cached
        # and read back), convert to dict for consistency with the return contract.
        if isinstance(data, list) and len(data) == 1 and isinstance(data[0], dict):
            data = data[0]
        # Metadata is stored as attributes in the parquet file
        return {"data": data, "cached_at": datetime.fromisoformat(df.attrs.get("cached_at", ""))}
    except Exception as e:
        logger.warning(f"Failed to read cache {cache_path}: {e}")
        return None


def _write_cache(cache_path: Path, data: Any, metadata: Dict[str, Any]) -> None:
    """
    Write data to cache file with metadata.

    Args:
        cache_path: Path to cache file
        data: Data to cache (DataFrame, dict, or list)
        metadata: Metadata to store with the data
    """
    try:
        if isinstance(data, pd.DataFrame):
            df = data.copy()
        elif isinstance(data, list):
            df = pd.DataFrame(data)
        elif isinstance(data, dict):
            df = pd.DataFrame([data])
        else:
            df = pd.DataFrame({"value": [data]})

        # Add metadata as DataFrame attributes
        df.attrs.update(metadata)
        df.to_parquet(cache_path, index=False)
        logger.debug(f"Cached data to {cache_path}")
    except Exception as e:
        logger.warning(f"Failed to write cache {cache_path}: {e}")
        raise CacheError(f"Cache write failed: {e}")


def _is_cache_valid(cache_path: Path, max_age_hours: int = 24) -> bool:
    """
    Check if cache is still valid.

    Args:
        cache_path: Path to cache file
        max_age_hours: Maximum age of cache in hours

    Returns:
        True if cache is valid, False otherwise
    """
    cached_data = _read_cache(cache_path)
    if not cached_data or "cached_at" not in cached_data:
        return False

    age = datetime.now(timezone.utc) - cached_data["cached_at"]
    return age.total_seconds() < (max_age_hours * 3600)


def get_ohlc(
    ticker: str,
    period: str = DEFAULT_PERIOD,
    interval: str = DEFAULT_INTERVAL,
    exchange: str = "NS",
    use_cache: bool = True,
    max_cache_age_hours: int = 24,
) -> Dict[str, Any]:
    """
    Fetch OHLC (Open, High, Low, Close) data for a ticker.

    Args:
        ticker: Ticker symbol (e.g., "RELIANCE")
        period: Data period (e.g., "1d", "1mo", "1y", "max")
        interval: Data interval (e.g., "1m", "1h", "1d", "1wk")
        exchange: Exchange suffix ("NS" for NSE, "BO" for BSE)
        use_cache: Whether to use cached data
        max_cache_age_hours: Maximum age of cached data in hours

    Returns:
        Dictionary containing OHLC data and metadata

    Raises:
        DataFetchError: If data fetching fails
    """
    normalized_ticker = _normalize_ticker(ticker, exchange)
    cache_path = _get_cache_path(normalized_ticker, "ohlc", period=period, interval=interval)

    # Try cache first
    if use_cache and _is_cache_valid(cache_path, max_cache_age_hours):
        cached = _read_cache(cache_path)
        if cached:
            logger.info(f"Using cached OHLC data for {normalized_ticker}")
            return {
                "ticker": ticker,
                "resolved_ticker": normalized_ticker,
                "period": period,
                "interval": interval,
                "data": cached["data"],
                "source": "cache",
                "cached_at": cached["cached_at"].isoformat() if cached.get("cached_at") else None,
                "retrieved_at": datetime.now(timezone.utc).isoformat(),
            }

    # Fetch from yfinance
    try:
        logger.info(f"Fetching OHLC data for {normalized_ticker} from Yahoo Finance")
        stock = yf.Ticker(normalized_ticker)
        hist = stock.history(period=period, interval=interval)

        if hist.empty:
            raise DataFetchError(f"No OHLC data returned for {normalized_ticker}")

        # Validate required columns
        required_columns = {"Open", "High", "Low", "Close", "Volume"}
        missing = required_columns - set(hist.columns)
        if missing:
            raise DataFetchError(f"Missing required OHLC columns: {missing}")

        # Reset index to make Date a column
        hist = hist.reset_index()
        hist.columns = [col.replace(" ", "_") for col in hist.columns]

        data_records = hist.to_dict(orient="records")

        result = {
            "ticker": ticker,
            "resolved_ticker": normalized_ticker,
            "period": period,
            "interval": interval,
            "data": data_records,
            "source": "yahoo_finance",
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
        }

        # Cache the result
        if use_cache:
            _write_cache(cache_path, hist, {
                "cached_at": datetime.now(timezone.utc).isoformat(),
                "ticker": normalized_ticker,
                "data_type": "ohlc",
                "period": period,
                "interval": interval,
            })

        return result

    except DataFetchError:
        raise
    except Exception as e:
        logger.error(f"Failed to fetch OHLC for {normalized_ticker}: {e}")
        raise DataFetchError(f"OHLC fetch failed for {normalized_ticker}: {e}")


def get_fundamentals(
    ticker: str,
    exchange: str = "NS",
    use_cache: bool = True,
    max_cache_age_hours: int = 168,  # 1 week for fundamentals
) -> Dict[str, Any]:
    """
    Fetch fundamental data for a ticker.

    Args:
        ticker: Ticker symbol (e.g., "RELIANCE")
        exchange: Exchange suffix ("NS" for NSE, "BO" for BSE)
        use_cache: Whether to use cached data
        max_cache_age_hours: Maximum age of cached data in hours

    Returns:
        Dictionary containing fundamental data and metadata

    Raises:
        DataFetchError: If data fetching fails
    """
    normalized_ticker = _normalize_ticker(ticker, exchange)
    cache_path = _get_cache_path(normalized_ticker, "fundamentals")

    # Try cache first
    if use_cache and _is_cache_valid(cache_path, max_cache_age_hours):
        cached = _read_cache(cache_path)
        if cached:
            logger.info(f"Using cached fundamentals for {normalized_ticker}")
            return {
                "ticker": ticker,
                "resolved_ticker": normalized_ticker,
                "data": cached["data"],
                "source": "cache",
                "cached_at": cached["cached_at"].isoformat() if cached.get("cached_at") else None,
                "retrieved_at": datetime.now(timezone.utc).isoformat(),
            }

    # Fetch from yfinance
    try:
        logger.info(f"Fetching fundamentals for {normalized_ticker} from Yahoo Finance")
        stock = yf.Ticker(normalized_ticker)
        info = stock.info

        if not info:
            raise DataFetchError(f"No fundamental data returned for {normalized_ticker}")

        # Extract relevant fundamental fields
        fundamental_fields = {
            "longName": info.get("longName"),
            "sector": info.get("sector"),
            "industry": info.get("industry"),
            "marketCap": info.get("marketCap"),
            "enterpriseValue": info.get("enterpriseValue"),
            "trailingPE": info.get("trailingPE"),
            "forwardPE": info.get("forwardPE"),
            "priceToBook": info.get("priceToBook"),
            "dividendYield": info.get("dividendYield"),
            "beta": info.get("beta"),
            "fiftyTwoWeekHigh": info.get("fiftyTwoWeekHigh"),
            "fiftyTwoWeekLow": info.get("fiftyTwoWeekLow"),
            "fiftyDayAverage": info.get("fiftyDayAverage"),
            "twoHundredDayAverage": info.get("twoHundredDayAverage"),
            "averageVolume": info.get("averageVolume"),
            "sharesOutstanding": info.get("sharesOutstanding"),
            "heldPercentInsiders": info.get("heldPercentInsiders"),
            "heldPercentInstitutions": info.get("heldPercentInstitutions"),
            "profitMargins": info.get("profitMargins"),
            "operatingMargins": info.get("operatingMargins"),
            "returnOnEquity": info.get("returnOnEquity"),
            "returnOnAssets": info.get("returnOnAssets"),
            "totalRevenue": info.get("totalRevenue"),
            "revenueGrowth": info.get("revenueGrowth"),
            "earningsGrowth": info.get("earningsGrowth"),
            "currentRatio": info.get("currentRatio"),
            "debtToEquity": info.get("debtToEquity"),
            "freeCashflow": info.get("freeCashflow"),
            "operatingCashflow": info.get("operatingCashflow"),
        }

        # Remove None values
        fundamental_data = {k: v for k, v in fundamental_fields.items() if v is not None}

        if not fundamental_data:
            raise DataFetchError(f"Fundamental data is empty for {normalized_ticker}")

        result = {
            "ticker": ticker,
            "resolved_ticker": normalized_ticker,
            "data": fundamental_data,
            "source": "yahoo_finance",
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
        }

        # Cache the result
        if use_cache:
            _write_cache(cache_path, fundamental_data, {
                "cached_at": datetime.now(timezone.utc).isoformat(),
                "ticker": normalized_ticker,
                "data_type": "fundamentals",
            })

        return result

    except DataFetchError:
        raise
    except Exception as e:
        logger.error(f"Failed to fetch fundamentals for {normalized_ticker}: {e}")
        raise DataFetchError(f"Fundamentals fetch failed for {normalized_ticker}: {e}")


def get_news(
    ticker: str,
    exchange: str = "NS",
    use_cache: bool = True,
    max_cache_age_hours: int = 6,  # News is more time-sensitive
) -> Dict[str, Any]:
    """
    Fetch recent news for a ticker.

    Args:
        ticker: Ticker symbol (e.g., "RELIANCE")
        exchange: Exchange suffix ("NS" for NSE, "BO" for BSE)
        use_cache: Whether to use cached data
        max_cache_age_hours: Maximum age of cached data in hours

    Returns:
        Dictionary containing news data and metadata

    Raises:
        DataFetchError: If data fetching fails
    """
    normalized_ticker = _normalize_ticker(ticker, exchange)
    cache_path = _get_cache_path(normalized_ticker, "news")

    # Try cache first
    if use_cache and _is_cache_valid(cache_path, max_cache_age_hours):
        cached = _read_cache(cache_path)
        if cached:
            logger.info(f"Using cached news for {normalized_ticker}")
            return {
                "ticker": ticker,
                "resolved_ticker": normalized_ticker,
                "data": cached["data"],
                "source": "cache",
                "cached_at": cached["cached_at"].isoformat() if cached.get("cached_at") else None,
                "retrieved_at": datetime.now(timezone.utc).isoformat(),
            }

    # Fetch from yfinance
    try:
        logger.info(f"Fetching news for {normalized_ticker} from Yahoo Finance")
        stock = yf.Ticker(normalized_ticker)
        news = stock.news

        if not news:
            logger.warning(f"No news returned for {normalized_ticker}")
            news_data = []
        else:
            # Extract relevant news fields
            news_data = []
            for item in news[:20]:  # Limit to 20 most recent
                news_item = {
                    "title": item.get("title"),
                    "publisher": item.get("publisher"),
                    "link": item.get("link"),
                    "providerPublishTime": item.get("providerPublishTime"),
                    "type": item.get("type"),
                    "thumbnail": item.get("thumbnail", {}).get("resolutions", [{}])[0].get("url") if item.get("thumbnail") else None,
                }
                # Convert timestamp to ISO format if present
                if news_item["providerPublishTime"]:
                    news_item["providerPublishTime"] = datetime.fromtimestamp(
                        news_item["providerPublishTime"], tz=timezone.utc
                    ).isoformat()
                news_data.append(news_item)

        result = {
            "ticker": ticker,
            "resolved_ticker": normalized_ticker,
            "data": news_data,
            "source": "yahoo_finance",
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
        }

        # Cache the result
        if use_cache:
            _write_cache(cache_path, news_data, {
                "cached_at": datetime.now(timezone.utc).isoformat(),
                "ticker": normalized_ticker,
                "data_type": "news",
            })

        return result

    except DataFetchError:
        raise
    except Exception as e:
        logger.error(f"Failed to fetch news for {normalized_ticker}: {e}")
        raise DataFetchError(f"News fetch failed for {normalized_ticker}: {e}")


def get_all_data(
    ticker: str,
    period: str = DEFAULT_PERIOD,
    interval: str = DEFAULT_INTERVAL,
    exchange: str = "NS",
    use_cache: bool = True,
) -> Dict[str, Any]:
    """
    Fetch all data (OHLC, fundamentals, news) for a ticker.

    Args:
        ticker: Ticker symbol
        period: OHLC period
        interval: OHLC interval
        exchange: Exchange suffix
        use_cache: Whether to use cached data

    Returns:
        Dictionary containing all data types
    """
    normalized_ticker = _normalize_ticker(ticker, exchange)

    ohlc_data = get_ohlc(ticker, period, interval, exchange, use_cache)
    fundamentals_data = get_fundamentals(ticker, exchange, use_cache)
    news_data = get_news(ticker, exchange, use_cache)

    return {
        "ticker": ticker,
        "resolved_ticker": normalized_ticker,
        "ohlc": ohlc_data,
        "fundamentals": fundamentals_data,
        "news": news_data,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
    }


def validate_ticker(ticker: str) -> bool:
    """
    Validate if ticker is in the known valid set.

    Args:
        ticker: Ticker symbol to validate

    Returns:
        True if valid, False otherwise
    """
    return ticker.strip().upper() in VALID_TICKERS


def clear_cache(ticker: Optional[str] = None, data_type: Optional[str] = None) -> int:
    """
    Clear cache files.

    Args:
        ticker: Specific ticker to clear (None for all)
        data_type: Specific data type to clear (None for all)

    Returns:
        Number of files deleted
    """
    deleted = 0
    pattern = "*"
    if ticker:
        pattern = f"{ticker.upper()}*"
    if data_type:
        pattern = f"*{data_type}*"

    for cache_file in CACHE_DIR.glob(f"{pattern}.parquet"):
        try:
            cache_file.unlink()
            deleted += 1
            logger.info(f"Deleted cache file: {cache_file}")
        except Exception as e:
            logger.warning(f"Failed to delete {cache_file}: {e}")

    return deleted


if __name__ == "__main__":
    # Quick test
    import sys

    test_ticker = sys.argv[1] if len(sys.argv) > 1 else "RELIANCE"

    print(f"Testing data fetch for {test_ticker}...")
    try:
        result = get_all_data(test_ticker)
        print(f"Success! Retrieved data for {result['resolved_ticker']}")
        print(f"OHLC records: {len(result['ohlc']['data'])}")
        print(f"Fundamentals keys: {list(result['fundamentals']['data'].keys())}")
        print(f"News items: {len(result['news']['data'])}")
    except Exception as e:
        print(f"Error: {e}")