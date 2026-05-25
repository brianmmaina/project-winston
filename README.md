# Project Winston

An AI-powered multi-agent trading research platform. Multiple specialist Claude agents analyze different market sectors in parallel, validate ML-generated signals with live news and data, and a Chief Analyst (overseer) agent synthesizes their findings into final trade recommendations — across both commodity futures and S&P 500 equities.

---

## Current status

| Layer | Status |
|---|---|
| ML pipeline — commodities (17 futures) | ✅ Complete |
| ML pipeline — stocks (S&P 500 ~503 names) | ✅ Complete |
| Data ingestion (yfinance, FRED, RSS + FinBERT) | ✅ Complete |
| FastAPI backend + Docker | ✅ Complete |
| React/TypeScript frontend (commodities + stocks) | ✅ Complete |
| Multi-agent layer — backend (11 sub-agents + overseer) | ✅ Complete |
| Agent analysis UI | 🔲 Not started |
| Agent scheduling | 🔲 Not started |
| Agent feedback / performance tracking | 🔲 Not started |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                          Browser                                 │
│  /commodities  /stocks  /stocks/portfolio  /agent-analysis      │
└──────────────────────────┬──────────────────────────────────────┘
                           │ HTTPS / JSON
┌──────────────────────────▼──────────────────────────────────────┐
│                       FastAPI backend                            │
│                                                                  │
│  /api/signals          /api/stocks/*       /api/agent-analysis  │
│  /api/refresh-async    /api/retrain        /api/jobs/{job_id}   │
└───────┬──────────────────────┬────────────────────┬─────────────┘
        │                      │                    │
        │  ┌── ML Pipeline ────┤                    │
        │  │  features.py      │              ┌─────▼──────────────┐
        │  │  trainer.py       │              │   Agent Pipeline   │
        │  │  predictor.py     │              │                    │
        │  │  stocks_ranker.py │              │  11 sub-agents     │
        │  │  regime.py        │              │  (run in parallel) │
        │  │  backtester.py    │              │        ↓           │
        │  └───────────────────┘              │   1 overseer       │
        │                                     └──────────┬─────────┘
        ▼                                                │
  ┌─────────────┐   ┌──────────────┐                    │
  │  PostgreSQL  │   │    Redis     │◄───────────────────┘
  │  prices      │   │  signals     │
  │  signals     │   │  agent cache │
  │  rankings    │   └──────────────┘
  │  macro data  │
  └──────────────┘
        ▲
        │
  yfinance · FRED · RSS feeds · Tavily (live search)
```

### Agent system

```
  Commodity agents (×3)          Stock sector agents (×5)         Cross-cutting (×3)
  ─────────────────────          ─────────────────────────         ──────────────────
  energy_commodities             tech_comms_stocks                 macro_rates
  metals                         healthcare_stocks                 geopolitics
  agriculture                    financials_stocks                 sentiment_news
                                 cyclicals_stocks
                                 defensives_stocks

                        all 11 run in parallel
                                 │
                                 ▼
                    ┌────────────────────────┐
                    │      Overseer Agent     │
                    │  reads all 11 reports   │
                    │  cross-checks ML signals│
                    │  STRONG_BUY/BUY/HOLD/   │
                    │  AVOID + reasoning      │
                    └────────────────────────┘
```

Each agent has 6 tools: `web_search` (Tavily), `get_commodity_signals`, `get_stock_rankings`, `get_macro_indicators`, `get_price_history`, `get_sentiment_scores`.

---

## Build plan

### Phase 1 — Agent Analysis UI

**What:** A dedicated page where you trigger an agent analysis run, watch job progress, and read the overseer's recommendations and each sub-agent's reasoning.

**Why this is next:** The entire agent backend is built and working. The only missing piece is a way to actually use it without curling an API.

**What to build:**

1. `AgentAnalysisPage` at `/agent-analysis`
   - "Run Analysis" button → `POST /api/agent-analysis` → get `job_id`
   - Live polling via `useJob` hook (already exists) → progress bar
   - On completion: render results

2. `OverseerCard` component
   - Market overview text
   - `verified_trades` list: recommendation badge (`STRONG_BUY` / `BUY` / `HOLD` / `AVOID`), conviction level, supporting themes, risk factors, suggested action
   - `top_risks` and `cross_asset_themes` sections

3. `SubAgentAccordion` component
   - Collapsible panel per sub-agent (11 total)
   - Shows: summary, signals reviewed (ticker + ML signal + agent view + conviction), news highlights
   - Visual indicator: agree/cautious/disagree vs ML signal

4. Navigation: add "Agent Analysis" to the top nav in `App.tsx`

**Endpoints to consume:**
```
POST /api/agent-analysis              → { job_id, status, name }
GET  /api/jobs/{job_id}               → poll until completed/failed
GET  /api/agent-analysis/latest       → full result (sub_reports + overseer.parsed)
GET  /api/agent-analysis/meta         → { generated_at, success counts }
```

**Estimated effort:** 2–3 days for both components and the page wiring.

---

### Phase 2 — Agent Scheduling + Outcome Tracking

**What:** Run agents automatically every day after the ML refresh, and track whether their recommendations were correct.

**Why:** Right now you have to manually trigger it. Once you trust the system, you want it running without thought. Outcome tracking is what lets you improve and calibrate it.

**What to build:**

1. Add `agent_analysis_daily` to APScheduler in `scheduler.py`
   - Mon–Fri 08:00 NY (after stock refresh at 07:15)
   - Calls the same `run_agent_pipeline` function

2. New DB table `agent_recommendations` to persist overseer output:
   ```sql
   CREATE TABLE agent_recommendations (
       id          SERIAL PRIMARY KEY,
       ticker      VARCHAR(16),
       asset_class VARCHAR(16),
       recommendation VARCHAR(16),
       conviction  VARCHAR(8),
       generated_at TIMESTAMPTZ,
       run_id      VARCHAR(64)
   );
   ```

3. Outcome tracker: nightly job that looks up price at T+5d, T+10d, T+21d for each recommendation and computes win/loss

4. Agent performance widget on the analysis page: rolling win rate, average conviction accuracy

**Estimated effort:** 3–4 days split across backend (scheduler + DB) and frontend (performance widget).

---

### Phase 3 — Portfolio & Risk Management

**What:** Turn overseer recommendations into an actual managed portfolio with position sizing and risk guardrails.

**What to build:**

- Combine Kelly fraction (existing ML output) with overseer conviction level for final position size
- Portfolio-level limits: max % per sector, max % commodities vs equities
- Stop-loss logic: flag a position if price moves against recommendation by a configurable threshold
- New page: `/portfolio-combined` showing the agent-recommended portfolio vs current ML-only portfolio

---

### Phase 4 — Agent Intelligence Improvements

Things that will meaningfully improve recommendation quality:

- **Earnings calendar**: feed upcoming earnings dates to stock agents before each run
- **Economic calendar**: give `macro_rates` agent scheduled release dates (FOMC, CPI, NFP)
- **Sector ETF momentum**: give each stock agent their benchmark ETF (XLK, XLF, etc.) as baseline context
- **Agent memory**: persist each agent's past assessments so the overseer can reference their track record
- **Options data**: IV surface and put/call ratios as additional context for `sentiment_news`

---

### Phase 5 — Production Hardening

Before sharing with anyone outside the two of you:

- Per-user API keys + rate limiting
- Alerts: Slack/email when overseer issues STRONG_BUY or AVOID
- Cost monitoring: track Anthropic + Tavily API spend
- Commodity model performance page (backtests exist in DB, no UI yet)

---

## Quick start

**Prerequisites:** Docker Desktop, Node 18+, an `.env` (copy from `.env.example`).

```bash
# 1. Start Postgres, Redis, backend, frontend
docker compose up -d --build

# 2. Apply database schema
docker compose exec backend alembic upgrade head

# 3. Bootstrap commodity data
docker compose exec backend python -m app.scripts.initial_data_load

# 4. Bootstrap stock data
docker compose exec backend python -m scripts.refresh_sp500_universe
docker compose exec backend python -m app.scripts.initial_stocks_load

# 5. Train the stock ranker
curl -X POST http://localhost:8000/api/stocks/retrain
```

Open http://localhost:5173.

**To run an agent analysis** (set `ANTHROPIC_API_KEY` in `.env` first):

```bash
# Trigger (returns immediately with a job_id)
curl -X POST http://localhost:8000/api/agent-analysis -H "X-API-Key: $API_KEY"

# Poll until completed
curl http://localhost:8000/api/jobs/{job_id}

# Read the result
curl http://localhost:8000/api/agent-analysis/latest
```

---

## Environment variables

```bash
# Infrastructure
DATABASE_URL=postgresql+asyncpg://advisor:password@postgres:5432/advisor
REDIS_URL=redis://redis:6379

# External data APIs
FRED_API_KEY=...               # free at fred.stlouisfed.org

# Agent pipeline
ANTHROPIC_API_KEY=...          # required for /api/agent-analysis
TAVILY_API_KEY=...             # optional — enables live web search in agents

# Security (leave empty for local dev, set a long random string in production)
API_KEY=...

# Tuning
AGENT_TOP_N_PER_SECTOR=10     # stocks per sector group surfaced to agents
AGENT_MODEL=claude-sonnet-4-6
AGENT_OVERSEER_MODEL=claude-sonnet-4-6
SCHEDULER_ENABLED=true
TIMEZONE=America/New_York
```

---

## Repository layout

```
project-winston/
├── backend/
│   ├── alembic/              database migrations
│   ├── app/
│   │   ├── agents/           multi-agent layer
│   │   │   ├── tools.py        tool schemas + implementations (DB, Redis, Tavily)
│   │   │   ├── base.py         shared agentic loop with tool_use handling
│   │   │   ├── sub_agents.py   11 sub-agent definitions + parallel runner
│   │   │   ├── overseer.py     overseer agent
│   │   │   └── pipeline.py     orchestration → Redis cache
│   │   ├── api/
│   │   │   ├── agent_analysis.py  POST/GET agent analysis endpoints
│   │   │   ├── jobs.py            job status polling
│   │   │   └── stocks.py          stock rankings/portfolio endpoints
│   │   ├── constants.py      commodity tickers + Redis key names
│   │   ├── constants_stocks.py
│   │   ├── core/             config, Redis client, API key security
│   │   ├── data/             yfinance fetchers, FRED loader, RSS/FinBERT sentiment
│   │   ├── db/               SQLAlchemy models + upsert operations
│   │   ├── ml/               features, trainers, ranker, backtests, HMM regime
│   │   ├── scripts/          bootstrap scripts
│   │   ├── services/         signals_service, stocks_service
│   │   └── main.py           FastAPI app + commodity routes
│   └── tests/
├── frontend/
│   └── src/
│       ├── api/              axios client + TypeScript types
│       ├── components/       SignalCard, PageState
│       ├── pages/            Dashboard, StocksDashboard, StocksPortfolio, etc.
│       └── App.tsx           routes + navigation
└── docker-compose.yml
```

---

## Tech stack

| Layer | Technology |
|---|---|
| Backend | Python 3.12, FastAPI, SQLAlchemy (async), Alembic |
| ML models | XGBoost, LightGBM, scikit-learn, hmmlearn, vectorbt, SHAP |
| Agents | Claude (claude-sonnet-4-6) via Anthropic SDK (async) |
| Live search | Tavily |
| Sentiment NLP | FinBERT (HuggingFace transformers) |
| Database | PostgreSQL 16 |
| Cache | Redis |
| Frontend | React 18, TypeScript, TailwindCSS, Vite |
| Deployment | Docker Compose |

---

## Tests

```bash
docker compose exec backend pytest tests/ -v
```

19 tests covering: data quality guards, panel feature shape/targets/sector z-scores, walk-forward fold integrity, sector-cap behaviour, portfolio backtester end-to-end.
