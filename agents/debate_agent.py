"""
Debate Agent — presents bull/bear cases and detects behavioral biases.

Input: Research Agent output.
Output: Structured JSON with structured argumentation and bias detection.

STRICT RULES:
- Only use information explicitly provided in the input data
- NEVER invent prices, financial ratios, news, company facts, or market events
- If evidence is insufficient, explicitly say so
- Distinguish "bias detected" from "no evidence of this bias"
- Return VALID JSON ONLY
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from agents.nvidia_llm import llm_enabled, nvidia_api_key, nvidia_base_url, nvidia_model

logger = logging.getLogger(__name__)


class DebateAgentError(Exception):
    """Exception raised when Debate Agent execution fails."""
    pass


# Behavioral bias checklist (fixed, exhaustive for this project)
BIAS_CHECKLIST = [
    "anchoring",
    "recency_bias",
    "overconfidence",
    "confirmation_bias",
    "herding",
    "loss_aversion",
]


# System prompt for LLM-powered debate (if LLM is available)
DEBATE_SYSTEM_PROMPT = """You are a skeptical investment debate opponent for an AI equity research analyst covering Indian equities (NSE/BSE).

Run a genuine evidence-based debate using ONLY the supplied Research Agent output.

HARD RULES
1. Return ONLY valid JSON - no markdown, no preamble, no analysis outside the JSON, no chain-of-thought or reasoning transcript.
2. Exactly these six fields, with these types:
{
    "bull_case": "string, at most 80 words",
    "bear_case": "string, at most 80 words",
    "failure_conditions": ["up to 3 short strings"],
    "no_trade_conditions": ["up to 3 short strings"],
    "biases_flagged": [{"bias_name": "one of: anchoring | recency_bias | overconfidence | confirmation_bias | herding | loss_aversion | no evidence of this bias", "where_it_shows_up": "short evidence-based explanation"}],
    "data_sources_used": ["strings copied from the research output data sources, e.g. 'yahoo_finance', 'cache"]
}
3. bull_case and bear_case must BOTH exist; each is ONE concise string of at most 80 words.
4. Use only the evidence supplied by Research (trend, key levels, news summary, data quality, data warnings, data sources). Never invent news, catalysts, events, prices, financial metrics, company facts, or classifications.
5. NEVER calculate returns, P&L, drawdown, win rate, or position sizing - only interpret values already supplied.
6. Preserve the semantic role of each Research key level exactly as Research labeled it (low, high, recent close, opening price, support, resistance) unless Research itself provides evidence for a different interpretation.
7. Do not force symmetry of evidence: if the evidence is one-sided, the weaker side may be an explicitly conditional scenario naming trigger level(s) from the Research and labeled as conditional.
8. If no company-specific news exists, state that briefly in the case instead of inventing a catalyst.
9. failure_conditions: at most 3 short strings tied to the supplied Research evidence.
10. no_trade_conditions: at most 3 short strings referencing actual levels, missing information, or stated research limitations.
11. biases_flagged: at most 3 objects in the schema above; flag a bias only with specific evidence from the Research output, otherwise use bias_name "no evidence of this bias" with a short note on what was checked."""

# Mock debate response for development without LLM
MOCK_DEBATE_RESPONSE = {
    "bull_case": "Insufficient evidence - LLM not configured.",
    "bear_case": "Insufficient evidence - LLM not configured.",
    "failure_conditions": ["No stop-loss defined", "Max drawdown exceeded"],
    "no_trade_conditions": ["Price below critical support", "Negative earnings surprise"],
    "biases_flagged": [
        {
            "bias_name": "confirmation_bias",
            "where_it_shows_up": "no evidence of this bias",
        }
    ],
    "data_sources_used": [],
}


def _prepare_debate_input(research_output: Dict[str, Any]) -> str:
    """
    Prepare structured input for the Debate Agent from Research Agent output.

    Args:
        research_output: Research Agent's JSON output dictionary

    Returns:
        Formatted string for LLM consumption
    """
    ticker = research_output.get("ticker", "UNKNOWN")
    resolved_ticker = research_output.get("resolved_ticker", ticker)
    trend = research_output.get("trend", "")
    key_levels = research_output.get("key_levels", [])
    news_summary = research_output.get("relevant_news_summary", "")
    data_warnings = research_output.get("data_warnings", [])
    data_quality = research_output.get("data_quality", "")
    data_sources = research_output.get("data_sources_used", [])

    # Extract key data points
    data_points = []
    if key_levels:
        data_points.append(f"Key levels: {key_levels}")
    if data_warnings:
        data_points.append(f"Data warnings: {data_warnings}")
    if news_summary:
        data_points.append(f"News: {news_summary}")
    else:
        data_points.append("News: none provided in research output")
    if data_quality:
        data_points.append(f"Data quality: {data_quality}")
    if data_sources:
        data_points.append(f"Data sources: {data_sources}")

    data_section = ""
    if data_points:
        data_section = "\n\nResearch data:\n" + "\n".join(data_points)

    input_text = f"""TICKER: {ticker}
RESOLVED: {resolved_ticker}

TREND: {trend}{data_section}

Return only the six-field JSON object. Keep each case <=80 words."""
    return input_text


def _parse_debate_response(response: str, research_output: Dict[str, Any]) -> Dict[str, Any]:
    """
    Parse and validate the Debate Agent's JSON response.

    Args:
        response: Raw LLM response string
        research_output: Original research output for metadata

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
        required_fields = ["bull_case", "bear_case", "failure_conditions", "no_trade_conditions", "biases_flagged"]
        for field in required_fields:
            if field not in parsed:
                if field == "bull_case":
                    parsed["bull_case"] = ""
                elif field == "bear_case":
                    parsed["bear_case"] = ""
                elif field == "failure_conditions":
                    parsed["failure_conditions"] = []
                elif field == "no_trade_conditions":
                    parsed["no_trade_conditions"] = []
                elif field == "biases_flagged":
                    parsed["biases_flagged"] = []

        # Validate biases_flagged structure
        if "biases_flagged" in parsed and isinstance(parsed["biases_flagged"], list):
            for bias_entry in parsed["biases_flagged"]:
                if not isinstance(bias_entry, dict):
                    bias_entry = {}
                if "bias_name" not in bias_entry:
                    bias_entry["bias_name"] = ""
                if "where_it_shows_up" not in bias_entry:
                    bias_entry["where_it_shows_up"] = ""

                # Only allow approved bias names
                approved_names = set(BIAS_CHECKLIST)
                if bias_entry["bias_name"] not in approved_names:
                    bias_entry["bias_name"] = "no evidence of this bias"

        # Ensure data_sources_used is present
        if "data_sources_used" not in parsed:
            parsed["data_sources_used"] = []

        # Add metadata
        parsed["ticker"] = research_output.get("ticker", "")
        parsed["resolved_ticker"] = research_output.get("resolved_ticker", "")
        parsed["generated_at"] = datetime.now(timezone.utc).isoformat()

        # Validate bias names
        if "biases_flagged" in parsed:
            for bias_entry in parsed["biases_flagged"]:
                if bias_entry["bias_name"] not in set(BIAS_CHECKLIST):
                    bias_entry["bias_name"] = "no evidence of this bias"

        return parsed

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse Debate Agent response as JSON: {e}")
        logger.error(f"Raw response: {response[:500]}")
        raise DebateAgentError(f"Debate Agent returned invalid JSON: {e}")
    except Exception as e:
        logger.error(f"Failed to process Debate Agent response: {e}")
        raise DebateAgentError(f"Response processing failed: {e}")


def _call_llm_debate(prompt: str, system_prompt: str) -> str:
    """
    Call NVIDIA NIM (OpenAI-compatible chat completions endpoint) for debate.

    Args:
        prompt: User prompt
        system_prompt: System prompt

    Returns:
        LLM response string

    Raises:
        DebateAgentError: If LLM call fails
    """
    if not llm_enabled():
        raise DebateAgentError(
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
            max_tokens=4096,
            stream=False,
            extra_body={"chat_template_kwargs": {"enable_thinking": False}},
        )
        # Observability only: metadata to detect output-token truncation.
        # No API key, no response content, no sensitive data.
        choice = response.choices[0] if getattr(response, "choices", None) else None
        usage = getattr(response, "usage", None)
        content_for_log = getattr(getattr(choice, "message", None), "content", None)
        logger.info(
            "Debate NIM response metadata: finish_reason=%s prompt_tokens=%s "
            "completion_tokens=%s total_tokens=%s content_length=%s",
            getattr(choice, "finish_reason", None),
            getattr(usage, "prompt_tokens", None),
            getattr(usage, "completion_tokens", None),
            getattr(usage, "total_tokens", None),
            len(content_for_log) if isinstance(content_for_log, str) else None,
        )
        content = response.choices[0].message.content
        if not content or not content.strip():
            raise DebateAgentError("NVIDIA NIM returned empty content")
        return content
    except DebateAgentError:
        raise
    except Exception as e:
        logger.error(f"NVIDIA NIM call failed: {type(e).__name__}: {e}")
        raise DebateAgentError(f"NVIDIA NIM call failed: {type(e).__name__}: {e}")


def run_debate_agent(
    research_output: Dict[str, Any],
    use_llm: bool = False,
    mock_mode: bool = True,
) -> Dict[str, Any]:
    """
    Run the Debate Agent on Research Agent output.

    Args:
        research_output: Research Agent's structured JSON output
        use_llm: Whether to attempt LLM call (currently disabled, Phase 2 mock-only)
        mock_mode: Force mock mode for development/testing

    Returns:
        Structured debate output dictionary

    Raises:
        DebateAgentError: If agent execution fails
    """
    ticker = research_output.get("ticker", "UNKNOWN")
    logger.info(f"Running Debate Agent for {ticker}")

    # Force mock mode for Phase 2 (LLM integration is Phase 3+)
    if mock_mode:
        # Enrich mock response with actual data from research output
        mock_response = MOCK_DEBATE_RESPONSE.copy()

        # Populate bull_case and bear_case based on research data
        trend = research_output.get("trend", "")
        key_levels = research_output.get("key_levels", [])
        news_summary = research_output.get("relevant_news_summary", "")
        data_warnings = research_output.get("data_warnings", [])

        # Build bull case from available data
        bull_parts = []
        if trend and "bull" in trend.lower():
            bull_parts.append(trend)
        if key_levels:
            bull_parts.append(f"Price at key technical levels: {key_levels}")
        if not bull_parts:
            bull_parts.append("Insufficient research data to construct bull case")
        if "Unable to determine" in str(bull_parts):
            bull_parts = ["Insufficient evidence to construct a bull case from research output"]

        # Build bear case from available data
        bear_parts = []
        if data_warnings:
            bear_parts.append(f"Data concerns: {data_warnings}")
        if not bear_parts:
            bear_parts.append("Insufficient evidence to construct a bear case from research output")

        mock_response["bull_case"] = " | ".join(bull_parts)
        mock_response["bear_case"] = " | ".join(bear_parts)

        # Populate biases based on research data quality
        research_warnings = research_output.get("data_warnings", [])
        detected_biases = []
        if "No OHLC data available" in research_warnings:
            detected_biases.append({
                "bias_name": "confirmation_bias",
                "where_it_shows_up": "Research output lacked OHLC data validation",
            })
        if "No fundamental data available" in research_warnings:
            detected_biases.append({
                "bias_name": "overconfidence",
                "where_it_shows_up": "Research output lacked fundamental data validation",
            })
        if not detected_biases:
            # Include at least one neutral entry
            detected_biases.append({
                "bias_name": "no evidence of this bias",
                "where_it_shows_up": "No specific bias patterns detected in available data",
            })

        mock_response["biases_flagged"] = detected_biases

        # Add ticker metadata
        mock_response["ticker"] = ticker
        mock_response["resolved_ticker"] = research_output.get("resolved_ticker", ticker)
        mock_response["generated_at"] = datetime.now(timezone.utc).isoformat()
        mock_response["data_sources_used"] = research_output.get("data_sources_used", [])
        mock_response["llm_mode"] = "mock"
        mock_response["model"] = None

        return mock_response

    # Try real LLM (currently disabled for Phase 2)
    try:
        logger.info("Attempting real LLM call for Debate Agent")
        response = _call_llm_debate(_prepare_debate_input(research_output), DEBATE_SYSTEM_PROMPT)
        result = _parse_debate_response(response, research_output)
        result["llm_mode"] = "real"
        result["model"] = nvidia_model()
        return result
    except DebateAgentError as e:
        logger.warning(f"LLM call failed, falling back to mock: {e}")
        # Fall back to mock mode
        return run_debate_agent(research_output, use_llm=False, mock_mode=True)


def validate_debate_output(output: Dict[str, Any]) -> bool:
    """
    Validate Debate Agent output conforms to schema.

    Args:
        output: Debate Agent output dictionary

    Returns:
        True if valid, False otherwise
    """
    required_fields = [
        "bull_case", "bear_case", "failure_conditions",
        "no_trade_conditions", "biases_flagged", "data_sources_used"
    ]

    for field in required_fields:
        if field not in output:
            logger.error(f"Missing required field: {field}")
            return False

    if not isinstance(output["bull_case"], str):
        logger.error("bull_case must be a string")
        return False

    if not isinstance(output["bear_case"], str):
        logger.error("bear_case must be a string")
        return False

    if not isinstance(output["failure_conditions"], list):
        logger.error("failure_conditions must be a list")
        return False

    if not isinstance(output["no_trade_conditions"], list):
        logger.error("no_trade_conditions must be a list")
        return False

    if not isinstance(output["biases_flagged"], list):
        logger.error("biases_flagged must be a list")
        return False

    # Validate each bias entry - auto-convert invalid bias names
    for bias_entry in output["biases_flagged"]:
        if not isinstance(bias_entry, dict):
            logger.error("Each biases_flagged entry must be a dict")
            return False
        if "bias_name" not in bias_entry:
            logger.error("Each bias entry must have bias_name")
            return False
        if "where_it_shows_up" not in bias_entry:
            logger.error("Each bias entry must have where_it_shows_up")
            return False
        # Auto-convert invalid bias names to "no evidence of this bias"
        if bias_entry["bias_name"] not in set(BIAS_CHECKLIST) and bias_entry["bias_name"] != "no evidence of this bias":
            bias_entry["bias_name"] = "no evidence of this bias"

    if not isinstance(output["data_sources_used"], list):
        logger.error("data_sources_used must be a list")
        return False

    return True


if __name__ == "__main__":
    # Quick test
    import sys
    sys.path.insert(0, str(__file__).rsplit("\\", 2)[0])

    from data.fetch import get_all_data
    from agents.research_agent import run_research_agent, validate_research_output

    test_ticker = sys.argv[1] if len(sys.argv) > 1 else "RELIANCE"

    print(f"Fetching data for {test_ticker}...")
    market_data = get_all_data(test_ticker, use_cache=False)

    print("Running Research Agent...")
    research_result = run_research_agent(market_data, mock_mode=True)

    if validate_research_output(research_result):
        print("Running Debate Agent...")
        debate_result = run_debate_agent(research_result, mock_mode=True)

        print(f"\nDebate Result for {debate_result['ticker']}:")
        print(f"Bull case: {debate_result['bull_case']}")
        print(f"Bear case: {debate_result['bear_case']}")
        print(f"Biases flagged: {debate_result['biases_flagged']}")
        print(f"Failure conditions: {debate_result['failure_conditions']}")
        print(f"No trade conditions: {debate_result['no_trade_conditions']}")

        print(f"\nValidation: {'PASSED' if validate_debate_output(debate_result) else 'FAILED'}")
    else:
        print("Research Agent output invalid, cannot test debate agent.")