"""
Research Agent for equity analysis.

Consumes market data and returns structured JSON analysis.
Supports both real LLM execution and deterministic mock mode for testing.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from agents.nvidia_llm import llm_enabled, nvidia_api_key, nvidia_base_url, nvidia_model

logger = logging.getLogger(__name__)

# System prompt for the Research Agent
RESEARCH_SYSTEM_PROMPT = """You are a financial research analyst for Indian equities (NSE/BSE).

Your task is to analyze the provided market data and return a structured JSON response.

STRICT RULES:
1. ONLY use information explicitly provided in the input data
2. NEVER invent prices, financial ratios, news, company facts, technical levels, or market events
3. NEVER pretend unavailable data exists
4. If information required for a conclusion is unavailable, explicitly state so
5. Flag stale or incomplete data in the response
6. Return VALID JSON ONLY - no additional text, no markdown formatting
7. key_levels entries must ALWAYS be descriptive strings in the format '<value> - <semantic role> (date/context)' - NEVER bare numbers. Preserve the semantic role (low, high, recent close, opening price, support, resistance, etc.) and the relevant date/context associated with each level as evidenced by the supplied data; derive value, role, and date from the data only, never invent a classification. The values, dates, and roles shown below are FORMAT EXAMPLES ONLY - do not copy them; compute everything from the input data. If the evidence does not establish a semantic role for a level, use a conservative description based only on the available data rather than inventing one.

OUTPUT SCHEMA:
{
    "trend": "string describing price trend based on OHLC data",
    "key_levels": ["array of strings, each '<value> - <semantic role> (date/context)'"],
    "relevant_news_summary": "string summarizing recent news from provided data only",
    "data_sources_used": ["array of data sources used (e.g., 'yahoo_finance', 'cache')"],
    "ticker": "string",
    "resolved_ticker": "string",
    "generated_at": "ISO timestamp",
    "data_quality": "string: 'complete' | 'partial' | 'stale' | 'unavailable'",
    "data_warnings": ["array of warnings about data limitations"]
}"""

# Mock response for development/testing without LLM API
MOCK_RESEARCH_RESPONSE = {
    "trend": "Unable to determine trend - LLM not configured. Enable LLM or provide mock implementation.",
    "key_levels": [],
    "relevant_news_summary": "No news analysis available - LLM not configured.",
    "data_sources_used": [],
    "ticker": "",
    "resolved_ticker": "",
    "generated_at": "",
    "data_quality": "unavailable",
    "data_warnings": ["LLM not configured - running in mock mode"]
}


class ResearchAgentError(Exception):
    """Exception raised when Research Agent execution fails."""
    pass


def _prepare_llm_input(market_data: Dict[str, Any]) -> str:
    """
    Prepare structured input for the LLM from market data.

    Args:
        market_data: Dictionary containing OHLC, fundamentals, news

    Returns:
        Formatted string for LLM consumption
    """
    ticker = market_data.get("ticker", "UNKNOWN")
    resolved_ticker = market_data.get("resolved_ticker", ticker)

    ohlc = market_data.get("ohlc", {})
    fundamentals = market_data.get("fundamentals", {})
    news = market_data.get("news", {})

    # Build OHLC summary
    ohlc_data = ohlc.get("data", [])
    ohlc_source = ohlc.get("source", "unknown")
    ohlc_retrieved = ohlc.get("retrieved_at", "unknown")

    ohlc_summary = "OHLC DATA:\n"
    if ohlc_data:
        # Get latest few records
        recent = ohlc_data[-5:] if len(ohlc_data) >= 5 else ohlc_data
        for record in recent:
            date = record.get("Date") or record.get("date") or record.get("Datetime") or "unknown"
            open_p = record.get("Open", record.get("open", "N/A"))
            high = record.get("High", record.get("high", "N/A"))
            low = record.get("Low", record.get("low", "N/A"))
            close = record.get("Close", record.get("close", "N/A"))
            volume = record.get("Volume", record.get("volume", "N/A"))
            ohlc_summary += f"  {date}: O={open_p} H={high} L={low} C={close} V={volume}\n"

        # Calculate basic trend from last 20 days if available
        if len(ohlc_data) >= 20:
            recent_closes = [r.get("Close", r.get("close")) for r in ohlc_data[-20:]]
            valid_closes = [c for c in recent_closes if c is not None]
            if len(valid_closes) >= 2:
                change = ((valid_closes[-1] - valid_closes[0]) / valid_closes[0]) * 100
                ohlc_summary += f"\n20-day change: {change:.2f}%\n"
    else:
        ohlc_summary += "  No OHLC data available\n"

    # Build fundamentals summary
    fund_data = fundamentals.get("data", {})
    fund_source = fundamentals.get("source", "unknown")
    fund_retrieved = fundamentals.get("retrieved_at", "unknown")

    fund_summary = "FUNDAMENTALS:\n"
    if fund_data:
        for key, value in fund_data.items():
            fund_summary += f"  {key}: {value}\n"
    else:
        fund_summary += "  No fundamental data available\n"

    # Build news summary
    news_data = news.get("data", [])
    news_source = news.get("source", "unknown")
    news_retrieved = news.get("retrieved_at", "unknown")

    news_summary = "NEWS:\n"
    if news_data:
        for item in news_data[:10]:  # Limit to 10 most recent
            title = item.get("title", "No title")
            publisher = item.get("publisher", "Unknown")
            pub_time = item.get("providerPublishTime", "Unknown time")
            news_summary += f"  - [{pub_time}] {publisher}: {title}\n"
    else:
        news_summary += "  No news data available\n"

    # Combine all
    full_input = f"""TICKER: {ticker}
RESOLVED TICKER: {resolved_ticker}

{ohlc_summary}
Data source: {ohlc_source}, Retrieved: {ohlc_retrieved}

{fund_summary}
Data source: {fund_source}, Retrieved: {fund_retrieved}

{news_summary}
Data source: {news_source}, Retrieved: {news_retrieved}

Analyze the above data and return the JSON response as specified."""
    return full_input


def _parse_llm_response(response: str, market_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Parse and validate LLM response.

    Args:
        response: Raw LLM response string
        market_data: Original market data for metadata

    Returns:
        Validated response dictionary
    """
    try:
        # Clean response - remove any markdown formatting
        cleaned = response.strip()
        if cleaned.startswith("```json"):
            cleaned = cleaned[7:]
        if cleaned.startswith("```"):
            cleaned = cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()

        parsed = json.loads(cleaned)

        # Validate required fields
        required_fields = ["trend", "key_levels", "relevant_news_summary", "data_sources_used"]
        for field in required_fields:
            if field not in parsed:
                parsed[field] = "" if field != "key_levels" and field != "data_sources_used" else []

        # Add metadata
        parsed["ticker"] = market_data.get("ticker", "")
        parsed["resolved_ticker"] = market_data.get("resolved_ticker", "")
        parsed["generated_at"] = datetime.now(timezone.utc).isoformat()

        # Determine data quality
        ohlc_data = market_data.get("ohlc", {}).get("data", [])
        fund_data = market_data.get("fundamentals", {}).get("data", {})
        news_data = market_data.get("news", {}).get("data", [])

        warnings = []
        if not ohlc_data:
            warnings.append("No OHLC data available")
        if not fund_data:
            warnings.append("No fundamental data available")
        if not news_data:
            warnings.append("No news data available")

        # Check data freshness
        for data_type in ["ohlc", "fundamentals", "news"]:
            retrieved = market_data.get(data_type, {}).get("retrieved_at")
            if retrieved:
                try:
                    retrieved_dt = datetime.fromisoformat(retrieved.replace("Z", "+00:00"))
                    age_hours = (datetime.now(timezone.utc) - retrieved_dt).total_seconds() / 3600
                    if age_hours > 24:
                        warnings.append(f"{data_type} data is {age_hours:.1f} hours old")
                except Exception:
                    pass

        if warnings:
            parsed["data_quality"] = "partial"
            parsed["data_warnings"] = warnings
        else:
            parsed["data_quality"] = "complete"
            parsed["data_warnings"] = []

        # Ensure data_sources_used is populated
        if not parsed.get("data_sources_used"):
            sources = set()
            for data_type in ["ohlc", "fundamentals", "news"]:
                src = market_data.get(data_type, {}).get("source")
                if src:
                    sources.add(src)
            parsed["data_sources_used"] = list(sources)

        return parsed

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse LLM response as JSON: {e}")
        logger.error(f"Raw response: {response[:500]}")
        raise ResearchAgentError(f"LLM returned invalid JSON: {e}")
    except Exception as e:
        logger.error(f"Failed to process LLM response: {e}")
        raise ResearchAgentError(f"Response processing failed: {e}")


def _call_llm(prompt: str, system_prompt: str) -> str:
    """
    Call NVIDIA NIM (OpenAI-compatible chat completions endpoint).

    Args:
        prompt: User prompt
        system_prompt: System prompt

    Returns:
        LLM response string

    Raises:
        ResearchAgentError: If LLM call fails
    """
    if not llm_enabled():
        raise ResearchAgentError(
            "NVIDIA NIM not enabled (set NVIDIA_API_KEY to enable real LLM calls)"
        )
    try:
        import openai
        client = openai.OpenAI(base_url=nvidia_base_url(), api_key=nvidia_api_key())
        response = client.chat.completions.create(
            model=nvidia_model(),
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
            max_tokens=2048,
            stream=False,
            extra_body={"chat_template_kwargs": {"enable_thinking": False}},
        )
        content = response.choices[0].message.content
        if not content or not content.strip():
            raise ResearchAgentError("NVIDIA NIM returned empty content")
        return content
    except ResearchAgentError:
        raise
    except Exception as e:
        logger.error(f"NVIDIA NIM call failed: {type(e).__name__}: {e}")
        raise ResearchAgentError(f"NVIDIA NIM call failed: {type(e).__name__}: {e}")


def run_research_agent(
    market_data: Dict[str, Any],
    use_llm: bool = True,
    mock_mode: bool = False,
) -> Dict[str, Any]:
    """
    Run the Research Agent on market data.

    Args:
        market_data: Dictionary containing OHLC, fundamentals, news data
        use_llm: Whether to attempt LLM call (if False, uses mock)
        mock_mode: Force mock mode even if LLM is available

    Returns:
        Structured JSON analysis

    Raises:
        ResearchAgentError: If agent execution fails
    """
    # Validate input
    if not market_data:
        raise ResearchAgentError("No market data provided")

    ticker = market_data.get("ticker", "UNKNOWN")
    logger.info(f"Running Research Agent for {ticker}")

    # Prepare input
    llm_input = _prepare_llm_input(market_data)

    # Determine execution mode
    if mock_mode or not use_llm:
        logger.info("Running in mock mode (no LLM)")
        mock_response = MOCK_RESEARCH_RESPONSE.copy()
        mock_response["ticker"] = ticker
        mock_response["resolved_ticker"] = market_data.get("resolved_ticker", ticker)
        mock_response["generated_at"] = datetime.now(timezone.utc).isoformat()

        # Add actual data sources used
        sources = set()
        for data_type in ["ohlc", "fundamentals", "news"]:
            src = market_data.get(data_type, {}).get("source")
            if src:
                sources.add(src)
        mock_response["data_sources_used"] = list(sources)

        # Basic data quality assessment
        warnings = []
        if not market_data.get("ohlc", {}).get("data"):
            warnings.append("No OHLC data available")
        if not market_data.get("fundamentals", {}).get("data"):
            warnings.append("No fundamental data available")
        if not market_data.get("news", {}).get("data"):
            warnings.append("No news data available")
        mock_response["data_warnings"] = warnings
        mock_response["data_quality"] = "partial" if warnings else "complete"

        return mock_response

    # Try real LLM
    try:
        logger.info("Attempting real LLM call")
        response = _call_llm(llm_input, RESEARCH_SYSTEM_PROMPT)
        return _parse_llm_response(response, market_data)
    except ResearchAgentError as e:
        logger.warning(f"LLM call failed, falling back to mock: {e}")
        # Fall back to mock mode
        return run_research_agent(market_data, use_llm=False, mock_mode=True)


def validate_research_output(output: Dict[str, Any]) -> bool:
    """
    Validate Research Agent output conforms to schema.

    Args:
        output: Research Agent output dictionary

    Returns:
        True if valid, False otherwise
    """
    required_fields = [
        "trend", "key_levels", "relevant_news_summary",
        "data_sources_used", "ticker", "resolved_ticker",
        "generated_at", "data_quality", "data_warnings"
    ]

    for field in required_fields:
        if field not in output:
            logger.error(f"Missing required field: {field}")
            return False

    if not isinstance(output["key_levels"], list):
        logger.error("key_levels must be a list")
        return False

    if not isinstance(output["data_sources_used"], list):
        logger.error("data_sources_used must be a list")
        return False

    if not isinstance(output["data_warnings"], list):
        logger.error("data_warnings must be a list")
        return False

    if output["data_quality"] not in ["complete", "partial", "stale", "unavailable"]:
        logger.error(f"Invalid data_quality: {output['data_quality']}")
        return False

    return True


if __name__ == "__main__":
    # Test with mock data
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))

    from data.fetch import get_all_data

    test_ticker = sys.argv[1] if len(sys.argv) > 1 else "RELIANCE"

    print(f"Fetching data for {test_ticker}...")
    market_data = get_all_data(test_ticker)

    print("Running Research Agent (mock mode)...")
    result = run_research_agent(market_data, mock_mode=True)

    print(json.dumps(result, indent=2))
    print(f"\nValidation: {'PASSED' if validate_research_output(result) else 'FAILED'}")