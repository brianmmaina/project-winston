# Project Winston

Winston is a trading research platform that combines a quantitative ML pipeline with a layer of AI agents that reason over those signals. The ML models handle the math — price patterns, regime detection, cross-sectional ranking. The agents handle the context — reading live news, checking macro conditions, understanding why something is moving, and deciding whether the model's signal holds up against what's actually happening in the world. An overseer agent reads all of that and issues the final recommendation.

The idea is to have something that works like a team of analysts running in the background — each one covering their domain, reporting up, and getting a final call from the head analyst. It covers 17 commodity futures and the full S&P 500.

---

## What's built

**ML pipeline — commodities**

Per-ticker stacked XGBoost + LightGBM classifiers across three horizons (5d, 10d, 21d). Hidden Markov Model for regime detection (bear / bull / high-volatility). Kelly criterion position sizing. Correlation filter to remove redundant signals. Walk-forward OOS validation. Vectorbt backtester per ticker.

**ML pipeline — stocks**

Global LightGBM cross-sectional ranker across ~503 S&P 500 names. Sector-relative z-score features. Top-25 portfolio with per-GICS-sector caps. Portfolio backtest benchmarked against SPY.

**Data ingestion**

Daily OHLCV from yfinance for commodities and stocks. Macro indicators from FRED (Fed rate, yield spread, VIX, CPI, breakeven inflation). RSS news feeds processed through FinBERT for per-ticker sentiment scores.

**Agent layer**

11 specialist agents run in parallel — 3 commodity domain agents (energy, metals, agriculture), 5 stock sector agents (tech/comms, healthcare, financials, cyclicals, defensives), and 3 cross-cutting agents (macro/rates, geopolitics, sentiment/news). Each has access to live web search via Tavily, the ML signals, price history, macro data, and sentiment scores. An overseer agent reads all 11 reports, cross-checks the ML signals independently, and issues STRONG_BUY / BUY / HOLD / AVOID with full reasoning.

**Backend**

FastAPI with async SQLAlchemy. Alembic migrations. APScheduler for daily data refresh and weekly retraining. Redis for signal caching. API key auth on write endpoints. Async job system so long-running tasks return a job_id and the client polls for completion.

**Frontend**

React + TypeScript + TailwindCSS. Pages for commodity signals, stock rankings, portfolio equity curve vs SPY, stock and commodity detail views, and backtest results.

---

## What's not built yet

- Agent analysis UI (the backend works, there's no way to use it from the app)
- Agent scheduling (currently manual trigger only)
- Agent memory (agents don't remember past runs)
- Vector DB for knowledge retrieval
- COT, EIA, USDA data sources
- Event-driven triggering (currently scheduled, not reactive)
- Debate layer for high-stakes calls
- Outcome tracking and agent calibration
- Risk layer combining ML sizing with agent conviction
- Alerts

---

## Build plan

### Phase 1 — Agent UI (2-3 weeks)

The backend is complete. The gap is a frontend to actually use it.

Build an `/agent-analysis` page with a button to trigger a run, live job progress polling, and a results view. The results view needs two components: an `OverseerCard` that shows the final verified trades table (ticker, recommendation, conviction, supporting themes, risk factors, suggested action) and a `SubAgentAccordion` that lets you drill into each agent's reasoning, see which ML signals they agreed or disagreed with, and read their news highlights. Add the page to the nav.

Endpoints:
```
POST /api/agent-analysis        trigger a run, get job_id
GET  /api/jobs/{job_id}         poll until completed or failed
GET  /api/agent-analysis/latest full result
GET  /api/agent-analysis/meta   run timestamp and success counts
```

### Phase 2 — Memory and scheduling (2-3 weeks)

Two things that change the quality of every run from here on.

Agent scheduling: add `agent_analysis_daily` to APScheduler, running Mon-Fri at 08:00 NY after the ML refresh at 07:15. Persist overseer recommendations to a new `agent_recommendations` DB table so there's a permanent record.

Vector DB memory: add Chroma to the stack. Embed every agent analysis on completion. Give agents a `search_memory` tool so they can query their own history — what did the energy agent conclude the last three times OPEC met, what happened to copper when Chinese PMI came in below 50. This is the single highest-leverage improvement to recommendation quality.

### Phase 3 — Better data sources (2-3 weeks)

Free, high-signal data that directly improves what agents can reason about.

CFTC Commitment of Traders data: weekly positioning for every major futures market, showing whether large speculators and commercials are long or short. One of the most predictive inputs for commodity signals and completely free. EIA weekly inventory reports for crude and natural gas storage. USDA crop reports for agricultural commodities. Earnings calendar so stock agents know what's reporting before each run. Economic calendar (FOMC dates, CPI, NFP, PCE) for the macro agent.

### Phase 4 — Event-driven triggering (3-4 weeks)

Move from scheduled to reactive.

Build a lightweight event bus. Define trigger rules: price move exceeds threshold, news volume spikes, scheduled data release fires. Agents subscribe to events relevant to their domain. A crude oil spike triggers the energy agent and the geopolitics agent immediately, not at the next scheduled run. The overseer re-evaluates affected positions. An alert system sends a notification when STRONG_BUY or AVOID is issued.

### Phase 5 — Debate layer and calibration (3-4 weeks)

Quality control on high-stakes calls and a feedback loop that makes the system improve over time.

For any STRONG_BUY or AVOID, spawn a bull case agent and a bear case agent for that specific ticker. Each argues its position with evidence. The overseer reads both and makes the final call, with the full debate visible. This catches blind spots that a single agent writing up a BUY case will miss.

Outcome tracking: nightly job that checks the price at T+5d, T+10d, and T+21d against each recommendation. Per-agent accuracy dashboard: win rate by conviction level, by asset class, over time. The overseer dynamically weights agents based on calibrated accuracy. Agents that are consistently right get more weight.

### Phase 6 — ML improvements (ongoing)

Can be worked on alongside any other phase.

Replace the binary BUY/HOLD classifier with probabilistic outputs: expected return, confidence interval, downside risk. Regime-conditional models: train separate models for bear, bull, and high-volatility regimes. Cross-asset features: copper into industrials, oil into airlines and consumer spending, yield curve shape into financials. Factor decomposition for stocks so agents understand whether a high-ranked stock is a momentum trade or a quality defensive. COT data as ML features once Phase 3 data is in.

### Phase 7 — Risk layer (when signals are trusted)

Turn recommendations into a coherent portfolio.

Unified position sizing that combines the ML expected return with the overseer conviction level. Portfolio-level exposure limits: max percentage per sector, max percentage in commodities versus equities. Correlation-aware allocation so the portfolio isn't five things that move together. Stop-loss tracking that flags positions moving against the recommendation.

---

## Architecture

```
                    EVENTS
                    price thresholds / scheduled releases / news spikes
                           |
               AGENT MEMORY (vector DB)
               past analyses / market events / outcomes
                           |
                    SPECIALIST AGENTS (x11, parallel)
                    domain tools + memory retrieval
                           |
                    DEBATE LAYER
                    bull vs bear for strong calls
                           |
                    OVERSEER
                    synthesis + calibrated weighting
                           |
                    RISK LAYER
                    position sizing + portfolio limits
                           |
                    RECOMMENDATION
                    ticker / size / horizon / conviction / reasoning
                           |
                    OUTCOME TRACKER
                    feeds back to calibration
```

Current agent roster:

```
Commodity               Stocks (top-N per sector)       Cross-cutting
---------               -------------------------       -------------
energy_commodities      tech_comms_stocks               macro_rates
metals                  healthcare_stocks               geopolitics
agriculture             financials_stocks               sentiment_news
                        cyclicals_stocks
                        defensives_stocks
```

---

## Running it

Prerequisites: Docker Desktop, an `.env` copied from `.env.example`.

```bash
docker compose up -d --build
docker compose exec backend alembic upgrade head
docker compose exec backend python -m app.scripts.initial_data_load
docker compose exec backend python -m scripts.refresh_sp500_universe
docker compose exec backend python -m app.scripts.initial_stocks_load
curl -X POST http://localhost:8000/api/stocks/retrain
```

Open http://localhost:5173.

To run an agent analysis once `ANTHROPIC_API_KEY` is set:

```bash
curl -X POST http://localhost:8000/api/agent-analysis -H "X-API-Key: $API_KEY"
curl http://localhost:8000/api/jobs/{job_id}
curl http://localhost:8000/api/agent-analysis/latest
```

---

## Environment variables

```
DATABASE_URL            postgresql+asyncpg connection string
REDIS_URL               redis connection string
FRED_API_KEY            free at fred.stlouisfed.org
ANTHROPIC_API_KEY       required for agent analysis
TAVILY_API_KEY          optional, enables live web search in agents
API_KEY                 protects write endpoints, leave empty for local dev
AGENT_TOP_N_PER_SECTOR  stocks per sector group shown to agents, default 10
AGENT_MODEL             claude-sonnet-4-6
AGENT_OVERSEER_MODEL    claude-sonnet-4-6
SCHEDULER_ENABLED       true
TIMEZONE                America/New_York
```

---

## Stack

```
Backend         Python 3.12, FastAPI, SQLAlchemy async, Alembic
ML              XGBoost, LightGBM, scikit-learn, hmmlearn, vectorbt, SHAP
Agents          Claude via Anthropic async SDK
Search          Tavily
Sentiment       FinBERT (HuggingFace)
Database        PostgreSQL 16
Cache           Redis
Frontend        React 18, TypeScript, TailwindCSS, Vite
Infra           Docker Compose, GitHub Actions CI
```

---

## Tests

```bash
docker compose exec backend pytest tests/ -v
```

19 tests covering data quality guards, feature shape and targets, walk-forward fold integrity, sector cap behaviour, and the portfolio backtester end-to-end.
