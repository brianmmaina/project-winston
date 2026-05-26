# Commodity Advisor — manual E2E notes

Commands assume repository root `/commodity-advisor`.

## Automated checks executed in-agent

| Step | Status |
|------|--------|
| `python3 -m py_compile` on modified backend modules | OK |
| `npm run build` (frontend strict TS + Vite prod build) | OK |
| Docker Compose `up` / full ingest + bootstrap | Not run here (heavy / network-bound) |

## Recommended host sequence

1. `docker compose up --build`
2. Ensure Alembic migrates (`backend` Dockerfile CMD already runs `alembic upgrade head`).
3. Optional heavy bootstrap inside backend container:\
   `docker compose exec backend python -m app.scripts.initial_data_load`
4. Persistence smoke:\
   `docker compose exec backend python scripts/verify_persistence.py`
5. API smoke: `/health`, `POST /api/refresh`, `GET /api/signals`, detail URL for ticker (e.g. `GC=F` URL-encoded).

## Frontend

1. `cd frontend && npm install`
2. With backend reachable: `npm run generate-types`
3. `npm run dev` → verify dashboard/detail/backtest pages.

## Failures logged here (explicit)

- **Docker stack not executed** in this environment: Compose health, Postgres seed timings, RSS/FRED/Yahoo rate limits may require retries on first boot.
- **Initial data load** can take a long time and may OOM below ~8GB RAM for simultaneous FinBERT + full training fan-out — reduce tickers offline if needed.

If any step fails locally, paste the traceback + service logs so we can adjust timeouts or scope.
