"""
Unit tests for agents/research_agent.py
"""

import pytest
import json
from datetime import datetime, timezone
from unittest.mock import Mock, patch, MagicMock

# Import the module under test
import sys
sys.path.insert(0, str(__file__).replace("tests/test_research_agent.py", ""))

from agents.research_agent import (
    _prepare_llm_input,
    _parse_llm_response,
    run_research_agent,
    validate_research_output,
    ResearchAgentError,
    RESEARCH_SYSTEM_PROMPT,
    MOCK_RESEARCH_RESPONSE,
)


class TestPrepareLLMInput:
    """Tests for LLM input preparation."""

    def test_prepare_with_complete_data(self):
        """Test input preparation with all data types."""
        market_data = {
            "ticker": "RELIANCE",
            "resolved_ticker": "RELIANCE.NS",
            "ohlc": {
                "data": [
                    {"Date": "2024-01-01", "Open": 2500, "High": 2550, "Low": 2490, "Close": 2540, "Volume": 1000000},
                    {"Date": "2024-01-02", "Open": 2540, "High": 2580, "Low": 2530, "Close": 2570, "Volume": 1100000},
                ],
                "source": "yahoo_finance",
                "retrieved_at": datetime.now(timezone.utc).isoformat(),
            },
            "fundamentals": {
                "data": {"longName": "Reliance Industries Ltd", "sector": "Energy", "trailingPE": 25.5},
                "source": "yahoo_finance",
                "retrieved_at": datetime.now(timezone.utc).isoformat(),
            },
            "news": {
                "data": [
                    {"title": "Reliance announces new project", "publisher": "Economic Times", "providerPublishTime": "2024-01-01T10:00:00+00:00"},
                ],
                "source": "yahoo_finance",
                "retrieved_at": datetime.now(timezone.utc).isoformat(),
            },
        }

        result = _prepare_llm_input(market_data)

        assert "TICKER: RELIANCE" in result
        assert "RESOLVED TICKER: RELIANCE.NS" in result
        assert "OHLC DATA:" in result
        assert "FUNDAMENTALS:" in result
        assert "NEWS:" in result
        assert "Reliance Industries Ltd" in result
        assert "Energy" in result
        assert "Reliance announces new project" in result

    def test_prepare_with_missing_data(self):
        """Test input preparation with missing data."""
        market_data = {
            "ticker": "RELIANCE",
            "resolved_ticker": "RELIANCE.NS",
            "ohlc": {"data": [], "source": "yahoo_finance", "retrieved_at": datetime.now(timezone.utc).isoformat()},
            "fundamentals": {"data": {}, "source": "yahoo_finance", "retrieved_at": datetime.now(timezone.utc).isoformat()},
            "news": {"data": [], "source": "yahoo_finance", "retrieved_at": datetime.now(timezone.utc).isoformat()},
        }

        result = _prepare_llm_input(market_data)

        assert "No OHLC data available" in result
        assert "No fundamental data available" in result
        assert "No news data available" in result


class TestParseLLMResponse:
    """Tests for LLM response parsing."""

    def test_parse_valid_json(self):
        """Test parsing valid JSON response."""
        response = json.dumps({
            "trend": "Bullish",
            "key_levels": [2500, 2600],
            "relevant_news_summary": "Positive news",
            "data_sources_used": ["yahoo_finance"],
        })

        market_data = {
            "ticker": "RELIANCE",
            "resolved_ticker": "RELIANCE.NS",
            "ohlc": {"data": [{"Close": 2500}], "source": "yahoo_finance"},
            "fundamentals": {"data": {}, "source": "yahoo_finance"},
            "news": {"data": [], "source": "yahoo_finance"},
        }

        result = _parse_llm_response(response, market_data)

        assert result["trend"] == "Bullish"
        assert result["key_levels"] == [2500, 2600]
        assert result["ticker"] == "RELIANCE"
        assert result["resolved_ticker"] == "RELIANCE.NS"
        assert "generated_at" in result

    def test_parse_json_with_markdown(self):
        """Test parsing JSON wrapped in markdown code blocks."""
        response = """```json
{
    "trend": "Bearish",
    "key_levels": [2400],
    "relevant_news_summary": "Negative news",
    "data_sources_used": ["yahoo_finance"]
}
```"""

        market_data = {
            "ticker": "RELIANCE",
            "resolved_ticker": "RELIANCE.NS",
            "ohlc": {"data": [], "source": "yahoo_finance"},
            "fundamentals": {"data": {}, "source": "yahoo_finance"},
            "news": {"data": [], "source": "yahoo_finance"},
        }

        result = _parse_llm_response(response, market_data)
        assert result["trend"] == "Bearish"

    def test_parse_invalid_json_raises(self):
        """Test invalid JSON raises error."""
        response = "This is not valid JSON"

        market_data = {"ticker": "RELIANCE", "ohlc": {"data": []}, "fundamentals": {"data": {}}, "news": {"data": []}}

        with pytest.raises(ResearchAgentError):
            _parse_llm_response(response, market_data)

    def test_parse_missing_fields_filled(self):
        """Test missing fields are filled with defaults."""
        response = json.dumps({
            "trend": "Neutral",
        })

        market_data = {
            "ticker": "RELIANCE",
            "resolved_ticker": "RELIANCE.NS",
            "ohlc": {"data": [], "source": "yahoo_finance"},
            "fundamentals": {"data": {}, "source": "yahoo_finance"},
            "news": {"data": [], "source": "yahoo_finance"},
        }

        result = _parse_llm_response(response, market_data)

        assert result["key_levels"] == []
        assert result["relevant_news_summary"] == ""
        assert result["data_sources_used"] == ["yahoo_finance"]


class TestRunResearchAgent:
    """Tests for Research Agent execution."""

    def test_mock_mode(self):
        """Test agent runs in mock mode."""
        market_data = {
            "ticker": "RELIANCE",
            "resolved_ticker": "RELIANCE.NS",
            "ohlc": {"data": [{"Close": 2500}], "source": "yahoo_finance"},
            "fundamentals": {"data": {"sector": "Energy"}, "source": "yahoo_finance"},
            "news": {"data": [{"title": "Test"}], "source": "yahoo_finance"},
        }

        result = run_research_agent(market_data, mock_mode=True)

        assert result["ticker"] == "RELIANCE"
        assert "LLM not configured" in result["trend"]
        assert result["data_quality"] in ["complete", "partial"]
        assert isinstance(result["data_warnings"], list)

    def test_mock_mode_with_missing_data(self):
        """Test mock mode with missing data shows warnings."""
        market_data = {
            "ticker": "RELIANCE",
            "resolved_ticker": "RELIANCE.NS",
            "ohlc": {"data": [], "source": "yahoo_finance"},
            "fundamentals": {"data": {}, "source": "yahoo_finance"},
            "news": {"data": [], "source": "yahoo_finance"},
        }

        result = run_research_agent(market_data, mock_mode=True)

        assert "No OHLC data available" in result["data_warnings"]
        assert "No fundamental data available" in result["data_warnings"]
        assert "No news data available" in result["data_warnings"]
        assert result["data_quality"] == "partial"

    @patch("agents.research_agent._call_llm")
    def test_llm_mode_success(self, mock_call_llm):
        """Test successful LLM mode."""
        mock_call_llm.return_value = json.dumps({
            "trend": "Bullish on strong fundamentals",
            "key_levels": [2500, 2600, 2700],
            "relevant_news_summary": "Positive sector news",
            "data_sources_used": ["yahoo_finance"],
        })

        market_data = {
            "ticker": "RELIANCE",
            "resolved_ticker": "RELIANCE.NS",
            "ohlc": {"data": [{"Close": 2500}], "source": "yahoo_finance"},
            "fundamentals": {"data": {"sector": "Energy"}, "source": "yahoo_finance"},
            "news": {"data": [{"title": "Good news"}], "source": "yahoo_finance"},
        }

        result = run_research_agent(market_data, use_llm=True, mock_mode=False)

        assert result["trend"] == "Bullish on strong fundamentals"
        assert result["key_levels"] == [2500, 2600, 2700]
        mock_call_llm.assert_called_once()

    @patch("agents.research_agent._call_llm")
    def test_llm_mode_fallback_to_mock(self, mock_call_llm):
        """Test fallback to mock when LLM fails."""
        mock_call_llm.side_effect = ResearchAgentError("API key not found")

        market_data = {
            "ticker": "RELIANCE",
            "resolved_ticker": "RELIANCE.NS",
            "ohlc": {"data": [{"Close": 2500}], "source": "yahoo_finance"},
            "fundamentals": {"data": {"sector": "Energy"}, "source": "yahoo_finance"},
            "news": {"data": [], "source": "yahoo_finance"},
        }

        result = run_research_agent(market_data, use_llm=True, mock_mode=False)

        # Should fall back to mock
        assert "LLM not configured" in result["trend"] or "mock mode" in result.get("data_warnings", [])


class TestValidateResearchOutput:
    """Tests for output validation."""

    def test_valid_output(self):
        """Test valid output passes validation."""
        output = {
            "trend": "Bullish",
            "key_levels": [2500, 2600],
            "relevant_news_summary": "Good news",
            "data_sources_used": ["yahoo_finance"],
            "ticker": "RELIANCE",
            "resolved_ticker": "RELIANCE.NS",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "data_quality": "complete",
            "data_warnings": [],
        }

        assert validate_research_output(output) is True

    def test_missing_required_field(self):
        """Test missing required field fails validation."""
        output = {
            "trend": "Bullish",
            "key_levels": [2500],
            "relevant_news_summary": "Good news",
            "data_sources_used": ["yahoo_finance"],
            "ticker": "RELIANCE",
            # missing resolved_ticker
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "data_quality": "complete",
            "data_warnings": [],
        }

        assert validate_research_output(output) is False

    def test_invalid_key_levels_type(self):
        """Test non-list key_levels fails validation."""
        output = {
            "trend": "Bullish",
            "key_levels": "2500",  # Should be list
            "relevant_news_summary": "Good news",
            "data_sources_used": ["yahoo_finance"],
            "ticker": "RELIANCE",
            "resolved_ticker": "RELIANCE.NS",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "data_quality": "complete",
            "data_warnings": [],
        }

        assert validate_research_output(output) is False

    def test_invalid_data_quality(self):
        """Test invalid data_quality fails validation."""
        output = {
            "trend": "Bullish",
            "key_levels": [2500],
            "relevant_news_summary": "Good news",
            "data_sources_used": ["yahoo_finance"],
            "ticker": "RELIANCE",
            "resolved_ticker": "RELIANCE.NS",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "data_quality": "excellent",  # Invalid value
            "data_warnings": [],
        }

        assert validate_research_output(output) is False


class TestSystemPrompt:
    """Tests for system prompt content."""

    def test_system_contains_rules(self):
        """Test system prompt contains key rules."""
        assert "NEVER invent" in RESEARCH_SYSTEM_PROMPT
        assert "ONLY use information" in RESEARCH_SYSTEM_PROMPT
        assert "VALID JSON ONLY" in RESEARCH_SYSTEM_PROMPT
        assert "Flag stale" in RESEARCH_SYSTEM_PROMPT

    def test_system_contains_output_schema(self):
        """Test system prompt documents output schema."""
        assert "trend" in RESEARCH_SYSTEM_PROMPT
        assert "key_levels" in RESEARCH_SYSTEM_PROMPT
        assert "relevant_news_summary" in RESEARCH_SYSTEM_PROMPT
        assert "data_sources_used" in RESEARCH_SYSTEM_PROMPT


if __name__ == "__main__":
    pytest.main([__file__, "-v"])