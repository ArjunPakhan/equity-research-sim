"""
Focused tests for LLM mode provenance (llm_mode / model) on Research and Debate.

No live NVIDIA calls — the NIM client is mocked at the agent boundary, so the
agent's real execution path runs while the HTTP transport stays offline.
"""
import sys
import os
import json

sys.path.insert(0, str(__file__).rsplit("\\", 2)[0])

import pytest
from unittest.mock import patch

from agents.research_agent import (
    run_research_agent,
    validate_research_output,
    ResearchAgentError,
)
from agents.debate_agent import run_debate_agent, validate_debate_output
from agents.nvidia_llm import nvidia_model
from audit.logger import initialize_database, log_agent_call, get_audit_records


MARKET_DATA = {
    "ticker": "RELIANCE",
    "resolved_ticker": "RELIANCE.NS",
    "ohlc": {"data": [{"Close": 2500}], "source": "yahoo_finance"},
    "fundamentals": {"data": {"sector": "Energy"}, "source": "yahoo_finance"},
    "news": {"data": [{"title": "Positive news"}], "source": "yahoo_finance"},
}

RESEARCH_LLM_RESPONSE = json.dumps({
    "trend": "Bullish trend",
    "key_levels": ["2500 - support (recent)"],
    "relevant_news_summary": "Positive sector news",
    "data_sources_used": ["yahoo_finance"],
})

DEBATE_LLM_RESPONSE = json.dumps({
    "bull_case": "Support holding above key level",
    "bear_case": "Momentum fading near resistance",
    "failure_conditions": ["Stop-loss breached"],
    "no_trade_conditions": ["Range compression"],
    "biases_flagged": [
        {
            "bias_name": "confirmation_bias",
            "where_it_shows_up": "news summary cites only positive coverage",
        }
    ],
    "data_sources_used": ["yahoo_finance"],
})

RESEARCH_OUTPUT_FOR_DEBATE = {
    "ticker": "RELIANCE",
    "resolved_ticker": "RELIANCE.NS",
    "trend": "bullish trend",
    "key_levels": ["2500 - support"],
    "data_warnings": [],
    "data_sources_used": ["yahoo_finance"],
}


class TestResearchProvenance:
    """Research Agent llm_mode/model truthfulness."""

    def test_research_mock_mode(self):
        result = run_research_agent(MARKET_DATA, mock_mode=True)
        assert result["llm_mode"] == "mock"
        assert result["model"] is None

    @patch("agents.research_agent._call_llm")
    def test_research_real_mode(self, mock_call_llm):
        mock_call_llm.return_value = RESEARCH_LLM_RESPONSE
        result = run_research_agent(MARKET_DATA, use_llm=True, mock_mode=False)
        assert mock_call_llm.called
        assert result["llm_mode"] == "real"
        assert result["model"] == nvidia_model()

    @patch("agents.research_agent._call_llm")
    def test_research_llm_failure_falls_back_to_mock(self, mock_call_llm):
        mock_call_llm.side_effect = ResearchAgentError("NIM unavailable")
        result = run_research_agent(MARKET_DATA, use_llm=True, mock_mode=False)
        assert result["llm_mode"] == "mock"
        assert result["model"] is None


class TestDebateProvenance:
    """Debate Agent llm_mode/model truthfulness."""

    def test_debate_mock_mode(self):
        result = run_debate_agent(RESEARCH_OUTPUT_FOR_DEBATE, mock_mode=True)
        assert result["llm_mode"] == "mock"
        assert result["model"] is None

    @patch("agents.debate_agent._call_llm_debate")
    def test_debate_real_mode(self, mock_call_llm_debate):
        mock_call_llm_debate.return_value = DEBATE_LLM_RESPONSE
        result = run_debate_agent(
            RESEARCH_OUTPUT_FOR_DEBATE, use_llm=True, mock_mode=False
        )
        assert mock_call_llm_debate.called
        assert result["llm_mode"] == "real"
        assert result["model"] == nvidia_model()


class TestProvenanceSchemaAndAudit:
    """Schema truthfulness and audit persistence."""

    def test_model_field_truthful(self):
        research_mock = run_research_agent(MARKET_DATA, mock_mode=True)
        debate_mock = run_debate_agent(RESEARCH_OUTPUT_FOR_DEBATE, mock_mode=True)

        for result in (research_mock, debate_mock):
            assert result["llm_mode"] in ("real", "mock")
            if result["llm_mode"] == "mock":
                assert result["model"] is None

        with patch("agents.research_agent._call_llm") as mock_call_llm:
            mock_call_llm.return_value = RESEARCH_LLM_RESPONSE
            research_real = run_research_agent(
                MARKET_DATA, use_llm=True, mock_mode=False
            )
        assert research_real["llm_mode"] == "real"
        assert isinstance(research_real["model"], str)
        assert research_real["model"] == nvidia_model()

    def test_existing_fields_and_audit_record_unchanged(self):
        research = run_research_agent(MARKET_DATA, mock_mode=True)
        debate = run_debate_agent(RESEARCH_OUTPUT_FOR_DEBATE, mock_mode=True)

        assert validate_research_output(research) is True
        assert validate_debate_output(debate) is True
        assert research["ticker"] == "RELIANCE"
        assert research["resolved_ticker"] == "RELIANCE.NS"
        assert research["generated_at"]
        assert debate["ticker"] == "RELIANCE"
        assert debate["resolved_ticker"] == "RELIANCE.NS"
        assert "bull_case" in debate and "bear_case" in debate

        db_path = "test_llm_provenance_audit.db"
        if os.path.exists(db_path):
            os.remove(db_path)
        try:
            run_id = initialize_database(db_path)
            log_agent_call(
                db_path,
                run_id,
                "research",
                input_data=MARKET_DATA,
                output_data=research,
                human_approval_status="pending",
            )
            records = get_audit_records(db_path, run_id)
            research_record = None
            for record in records:
                if record["agent_name"] == "research":
                    research_record = record
                    break
            assert research_record is not None

            payload = json.loads(research_record["output_json"])
            assert payload["llm_mode"] == "mock"
            assert payload["model"] is None
            assert payload["ticker"] == "RELIANCE"
            assert payload["resolved_ticker"] == "RELIANCE.NS"
            assert research_record["run_id"] == run_id
            assert research_record["input_json"] is not None
            assert research_record["human_approval_status"] == "pending"
        finally:
            if os.path.exists(db_path):
                os.remove(db_path)
