from openai import OpenAI
import os

client = OpenAI(
    base_url="https://integrate.api.nvidia.com/v1",
    api_key=os.environ["NVIDIA_API_KEY"],
)

system_prompt = """
You are a financial research analysis agent.

Analyze ONLY the supplied market data.

Return ONLY valid JSON with exactly these fields:
{
  "trend": "string",
  "key_levels": ["string"],
  "relevant_news_summary": "string",
  "data_sources_used": ["string"],
  "data_quality": "string",
  "data_warnings": ["string"]
}

STRICT RULES:
1. key_levels MUST be an array of descriptive strings.
2. NEVER return bare numbers in key_levels.
3. Every key level MUST follow this format:
   "<value> - <semantic role> (date/context)"
4. Preserve the actual semantic role supported by the data.
5. Do not invent support, resistance, highs, lows, dates, news, or catalysts.
6. If the data does not establish a semantic role, use:
   "<value> - level identified from supplied OHLC data (date/context)"
7. Do not calculate investment returns, P&L, drawdown, win rate, or position sizing.
"""

user_input = """
Ticker: TCS.NS

Recent OHLC information:
- 2026-09-21: Open 2135.10, High 2142.00, Low 2090.00, Close 2128.70
- 2026-09-22: Open 2135.10, High 2138.00, Low 2105.00, Close 2110.00
- 2026-09-23: Open 2110.00, High 2120.00, Low 2089.00, Close 2095.00
- 2026-09-24: Open 2095.00, High 2100.00, Low 2087.00, Close 2087.00
- 2026-09-25: Open 2087.00, High 2090.00, Low 2082.00, Close 2082.00

Research context:
- Recent 5-day price movement is downward.
- 20-day price change: -13.22%.
- No company-specific news was provided.

Produce the JSON exactly according to the rules above.
"""

response = client.chat.completions.create(
    model="nvidia/nemotron-3.5-lightning-30b-a3b",
    messages=[
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_input},
    ],
    temperature=0.1,
    max_tokens=1200,
    stream=False,
    extra_body={
        "chat_template_kwargs": {
            "enable_thinking": False
        }
    },
)

print("\n========== RAW NVIDIA RESPONSE ==========\n")
print(response.choices[0].message.content)
print("\n=========================================\n")
