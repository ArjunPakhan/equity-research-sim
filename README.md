# AI-Orchestrated Equity Research & Risk Simulation Platform

A 5-agent AI pipeline for Indian equity research and paper-trading simulation — combining real NSE market data, LLM reasoning, deterministic quantitative backtesting, risk controls, human-in-the-loop approval, and a full audit trail. **Educational/research simulation only — no live broker execution.**

## Overview

This project simulates the full research → trade workflow used in quantitative equity research, but as a safe, auditable, paper-only system:

- **Real market data** from Yahoo Finance (NSE .NS tickers) with local parquet cache
- **LLM-based research & reasoning** for synthesis, debate, and review
- **Deterministic quantitative engine** for all financial calculations
- **Risk controls** (SEBI-informed, simulation only)
- **Human approval gate** before any paper execution
- **SQLite audit trail** linking every stage by `run_id`
- **FastAPI + React/Vite dashboard** that visualizes backend results without recalculating metrics

> **Paper-trading only. No broker API. No real-money execution. No investment advice.**

## Key Architecture

```
              REAL MARKET DATA (yfinance · NSE .NS · parquet cache)
                              ↓
                     RESEARCH AGENT (LLM synthesis)
                              ↓
                      DEBATE AGENT (bull/bear + biases)
                              ↓
                 DETERMINISTIC BACKTEST ENGINE
                 Moving Average Crossover 20/50 SMA
                 commission 0.1% · slippage 0.05%
                              ↓
                       RISK AGENT (simulation controls)
                              ↓
                    ┌─ HUMAN APPROVAL GATE ─┐
                    │  APPROVE → paper exec  │
                    │  REJECT  → stop        │
                    └────────────────────────┘
                              ↓
                    PAPER EXECUTION (PAPER_ONLY)
                              ↓
                       REVIEW AGENT (skeptical)
```

Cross-cutting: **SQLite audit trail** (`audit.db`) · **FastAPI** (`api/main.py`) · **React/Vite** (`frontend/`)

Architecture diagram: `docs/architecture.svg` (dark terminal, amber accents; AI vs deterministic clearly separated)

## AI vs Deterministic Computation

**AI proposes and interprets. Code calculates.**

| Layer | Used for |
|-------|----------|
| **LLM (AI)** | research synthesis, adversarial debate, bias detection, interpretation of backtest/risk, skeptical review |
| **Deterministic Python** | strategy execution, trade simulation, fees/slippage, P&L, win rate, avg win/loss, profit factor, max drawdown, equity curve |

The LLM never calculates quantitative metrics. The engine in `backtest_engine/` is the sole source of truth — same inputs → same outputs, no randomness, signal at bar close → execution at next bar open (no look-ahead).

## Agents

| Agent / Component | Responsibility | Output |
|-----------------|----------------|--------|
| **Research Agent** | Consume OHLC/fundamentals/news, produce trend, key levels, data quality | `trend`, `key_levels`, `data_sources_used`, `data_warnings` |
| **Debate Agent** | Bull/bear cases, failure/no-trade conditions, bias checklist | `bull_case`, `bear_case`, `biases_flagged` |
| **Backtest Agent** | Invoke deterministic engine, present real metrics (no fabrication) | `trades`, `win_rate`, `profit_factor`, `max_drawdown`, `is_mock` |
| **Risk Agent** | Position size, stop-loss, exposure/daily-loss limits, SEBI-informed simulation controls | `checks_passed`, `risk_warnings`, `sebi_aligned_controls` |
| **Paper Execution Engine** | Local simulation only (`PAPER_ONLY`), simulated qty/notional | `trade_id`, `execution_status`, `simulation_disclaimer` |
| **Review Agent** | Skeptical evaluation of full pipeline outcome | `should_have_traded`, `lessons` |

## Data Sources

- **Yahoo Finance via `yfinance`** — OHLC (Open/High/Low/Close/Volume), fundamentals, news
- **NSE resolution** — tickers normalized to `.NS` (e.g., `RELIANCE` → `RELIANCE.NS`); `BSE` via `.BO`
- **Local cache** — `data/cache/*.parquet`, TTL 24h OHLC / 1w fundamentals / 6h news, excluded from git
- **Current window** — validated 251 bars (1y daily) per ticker in smoke test; stored `data_start`/`data_end` per run

## Quantitative Engine

- **Strategy:** Moving Average Crossover — **only** strategy in this project
- **Fast SMA:** 20 · **Slow SMA:** 50 · **Direction:** long-only
- **Signal:** generated at **bar close** (using data up to t)
- **Execution:** **next bar open** (t+1) — prevents look-ahead bias
- **Initial capital:** ₹100,000 (demo config, configurable via API)
- **Commission:** 0.1% round-turn (simulation assumption)
- **Slippage:** 0.05% (simulation assumption)
- **Metrics (deterministic code):** `trades`, `win_rate`, `avg_win`, `avg_loss`, `profit_factor`, `max_drawdown`, `final_equity`, `total_return_pct`, `trade_count`, `winning/losing_trade_count`, `number_of_bars`

## Example Run — RELIANCE.NS

*Actual verified pipeline output — demonstration, not investment performance:*

| Field | Value |
|-------|-------|
| initial_capital | ₹100,000 |
| final_equity | ₹99,735.38 |
| total_return_pct | -0.26% |
| trade_count | 2 |
| win_rate | 0.0 |
| avg_win | 0.0 |
| avg_loss | 2.965 |
| profit_factor | 0.0 |
| max_drawdown | 0.2646 |
| number_of_bars | 251 |
| is_mock | false |
| data_status | success — deterministic backtest completed |

Not profitable — expected for a naïve demo strategy on a short window. Historical simulation does not predict future returns.

## Five-Ticker Validation

Each ticker fetched 251 OHLC records (1y daily) and completed `Research → Debate → Backtest → Risk` in smoke test:

- RELIANCE, TCS, INFY, HDFCBANK, ICICIBANK

Only RELIANCE metrics are documented above; other tickers validated for data availability and engine determinism (no invented returns).

## Human-in-the-Loop Approval

```
Research → Debate → Backtest → Risk → WAITING FOR HUMAN APPROVAL
                                         ├─ APPROVE → Paper Execution → Review (audit: approved)
                                         └─ REJECT  → Stop, no execution (audit: rejected)
```

- CLI: `[y/N]` prompt; API: `POST /runs/{id}/approve` / `POST /runs/{id}/reject` (explicit, no default)
- No AI approval, no implicit approval, no bypass. `skip_approval` only for tests.

## Auditability

Single `run_id` (UUID) links all stages in `audit.db` (`audit_log` table: `id, run_id, agent_name, timestamp, input_json, output_json, human_approval_status, approved_by, approved_at`). Every agent call is logged with full input/output JSON and approval metadata — inspectable via `/runs/{id}/audit`.

## Dashboard

- **Backend:** FastAPI `api/main.py` (port 8000) — CORS explicit `localhost:5173`
- **Frontend:** React + Vite `frontend/` (port 5173) — dark `#0a0f0a` + amber `#ffb000` + JetBrains Mono, high-density terminal aesthetic
- **Functionality:** health, run history, run detail, backtest/risk/review views, audit timeline, explicit approve/reject buttons, `PAPER TRADING ONLY` banners
- **Principle:** frontend only displays backend JSON; `val()` renders `UNAVAILABLE` for null, no JS financial calculations

## Quickstart (Windows PowerShell)

```powershell
cd equity-research-sim

# venv (optional)
python -m venv .venv
.\.venv\Scripts\Activate.ps1

pip install -r requirements.txt

# tests (76 = 61 Phase1-2 + 15 API)
python -m pytest tests/ -v

# backend
uvicorn api.main:app --reload --port 8000
# → http://localhost:8000/health, /docs

# frontend (new terminal)
cd frontend
npm install
npm run dev
# → http://localhost:5173
```

## NVIDIA NIM LLM Configuration (optional)

Research → Debate reasoning runs on **NVIDIA NIM** (OpenAI-compatible endpoint). Without configuration, agents use their honest mock output; financial metrics are always computed by the deterministic engine, never the LLM.

```powershell
# process environment only — set before starting the backend
$env:NVIDIA_API_KEY = "nvapi-..."        # your key from build.nvidia.com
$env:NVIDIA_MODEL   = "nvidia/nemotron-3.5-lightning-30b-a3b"   # optional (default)
$env:NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"    # optional (default)
```

- The key is supplied through the **process environment** (PowerShell `$env:`, system env vars, or your shell profile).
- **Never commit the key.** `.gitignore` excludes `.env`, `*.key`, `secrets.toml`; no `.env` file is required or created.
- **No API key is stored in SQLite** (audit records contain only agent inputs/outputs).
- **No API key is returned by FastAPI** or sent to React.
- **No broker credentials are involved** — paper trading only.
- Under pytest, LLM calls are always disabled so tests stay deterministic.

Without `NVIDIA_API_KEY`: Research returns its explicit "LLM not configured" mock and Debate returns explicit "Insufficient evidence" text — never fabricated AI output.

## Demo Workflow

1. Start backend & frontend as above
2. `POST /runs` → `{ticker:"RELIANCE"}` → returns `run_id` with `awaiting_approval`
3. `GET /runs/{id}` / `GET /runs/{id}/backtest` / `GET /runs/{id}/risk` — inspect real metrics
4. Approve: `POST /runs/{id}/approve` → runs paper execution + review
   or Reject: `POST /runs/{id}/reject` → blocks execution
5. `GET /runs/{id}/audit` — full trail; dashboard Audit Timeline shows each stage with input/output JSON

## API Documentation

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | `{status:"ok", paper_trading_only:true}` |
| GET | `/runs` | Recent runs (run_id, ticker, pipeline/approval/execution status, return, trades) |
| GET | `/runs/{id}` | Overview (stages, backtest/risk/paper/review summaries) |
| GET | `/runs/{id}/audit` | Full audit trail (all fields preserved) |
| GET | `/runs/{id}/backtest` | Deterministic backtest output |
| GET | `/runs/{id}/risk` | Risk Agent output |
| GET | `/runs/{id}/review` | Review Agent output |
| POST | `/runs` | Create run (ticker, exchange, capital/commission/slippage/periods); validates, runs to Risk, returns pending |
| POST | `/runs/{id}/approve` | Verify pending → record approved → paper_execution+review |
| POST | `/runs/{id}/reject` | Verify pending → record rejected → block execution |

Validation: ticker regex `^[A-Za-z0-9._-]{1,20}$`, capital>0, commission/slippage 0–5, fast<slow; unknown run_id → 404, double approve/reject → 409.

## Limitations

- One strategy only: 20/50 SMA long-only (demo, not optimal)
- Limited historical window in demo (251 bars / 1y daily)
- Simulated costs (0.1% commission, 0.05% slippage) — not broker-specific
- Paper execution only — no broker, no live market, no real money
- No claim of investment performance; past simulation ≠ future returns
- Survivorship bias not corrected; data quality depends on yfinance (delayed, may be incomplete)
- LLM reasoning is non-deterministic and may hallucinate — quantitative metrics are deterministic and audited
- Risk controls are educational simulation, not SEBI compliance

## Disclaimer

See `DISCLAIMER.md`. Educational/research only, not investment advice, not SEBI-registered.

## Repository Structure

```
README.md / DISCLAIMER.md / requirements.txt
api/  agents/  audit/  backtest_engine/  data/  orchestrator/  paper_execution/  tests/  frontend/  docs/
```

## Screenshot Checklist (capture manually)

1. Dashboard — RELIANCE run (₹100k → ₹99,735 / -0.26% / 2 trades)
2. Backtest + Risk panels (with UNAVAILABLE handling and SIMULATION CONTROL label)
3. Approval — WAITING / APPROVED / REJECTED states
4. Audit timeline — expand one stage showing input/output JSON
5. Architecture diagram (`docs/architecture.svg`)
