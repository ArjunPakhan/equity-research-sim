# Contributing

## Setup expectations

- **Python 3.10+** — `pip install -r requirements.txt` (a virtual environment is recommended)
- **Node.js 20+** — `npm install` inside `frontend/`
- **No API keys are required to run the tests.** LLM calls are disabled under pytest, and paper execution is simulated locally — no broker connection, no real money.
- Optional: `NVIDIA_API_KEY` only enables real LLM research/debate reasoning at runtime. Placeholders are documented in `.env.example`; never commit a real key.

## Backend tests

```bash
python -m pytest tests/ --cache-clear
# 136 tests
```

## Frontend tests

Run from the repository root:

```bash
node --test frontend/src/components/pipelineState.test.js frontend/src/api.test.js
# 17 tests
```

## Frontend production build

From `frontend/`:

```bash
npm run build
# output: frontend/dist/ (git-ignored)
```

## Contribution workflow

1. Fork the repository and create a feature branch.
2. Keep changes scoped and minimal; preserve existing successful behavior.
3. If the change touches the backtest/risk engine, explain the financial reasoning in the PR — deterministic calculations are the source of truth.
4. Run all three commands above before opening a pull request.
5. Project constraints are non-negotiable: paper trading only, no broker integrations, no real-money execution, no weakening of the human approval gate, no fabricated metrics.
6. Do not commit secrets, `audit.db`, caches, `node_modules`, or build output (see `.gitignore`).
7. Open a PR with a short description of the change and how you verified it.
