# AlphaLens

AlphaLens is a React dashboard and FastAPI service for market data retrieval and
AI-assisted equity research. It presents source-backed financial metrics and
streams agent progress to the dashboard. It is a research aid, not investment
advice.

## Architecture

```text
React Dashboard
    │ REST search + Server-Sent Events (SSE)
    ▼
FastAPI API
    ├── Provider layer: FMP → Finnhub → Alpha Vantage quote/profile fallbacks,
    │   GNews/Finnhub news, FMP/Yahoo chart history
    ├── Asyncio research coordinator with serialized Groq requests
    │   ├── Research, Financial, Valuation, Macro
    │   ├── Bull and Bear debate
    │   └── Moderator: INVEST / HOLD / PASS
    └── Optional PyMongo Async report persistence
```

## Agent memory

Completed research can be retained in MongoDB for 30 days. The
`agent_memory` collection stores a bounded report summary, recommendation,
confidence, reasons, risks, data sources, and agent outputs for the current
report. The MongoDB TTL index expires records using `expires_at`.

Each research run also loads up to three recent summaries for the same ticker.
The Moderator receives this history only as historical context; fresh market
and financial data still determines whether a recommendation is allowed and
which evidence supports it. Memory is unavailable silently or with an explicit
SSE warning, and it never blocks fresh analysis.

The project currently uses `asyncio` orchestration; it does not use LangGraph.
Provider requests are cached in-process, coalesced when identical requests are
concurrent, and retried with bounded exponential backoff on transient errors.
Numeric financial metrics are derived from retrieved statements where
available. Missing values are left unavailable rather than replaced with
estimates.

## Requirements

- Python 3.11 or newer
- Node.js 18 or newer
- A Groq API key for AI research
- At least one data provider key for market data
- Optional MongoDB connection for report persistence

FMP/Finnhub/Alpha Vantage/GNews access, quotas, and plan entitlements depend on
the provider account. No paid plan or provider key is bundled with AlphaLens.

## Local development (Windows PowerShell)

Backend:

```powershell
.\start_alphalens.ps1
```

The script checks runtimes, dependencies, and port ownership, then starts the
backend at `http://127.0.0.1:8001` and frontend at `http://localhost:3000`.
Backend API documentation is at `http://127.0.0.1:8001/docs`. It will not stop
or replace a listener it cannot verify as belonging to this project.

Stop only processes launched by the startup script with:

```powershell
.\stop_alphalens.ps1
```

The development frontend always targets `http://localhost:8001`, regardless of
stale `REACT_APP_BACKEND_URL` overrides. Its local env files use the same URL.

## Environment

`backend/.env.example` lists supported server settings:

- `GROQ_API_KEY` and optional `GROQ_MODEL`
- `FMP_API_KEY`, `FINNHUB_API_KEY`, `ALPHA_VANTAGE_API_KEY`, `GNEWS_API_KEY`
- Optional `MONGO_URL` and `DB_NAME`
- `CORS_ORIGINS`, a comma-separated list of allowed frontend origins

`frontend/.env.example` lists `REACT_APP_BACKEND_URL`. For production, configure
these values in the hosting provider's secret/environment settings rather than
committing `.env` files. Set `CORS_ORIGINS` to the deployed frontend origin(s);
do not use `*` with credentialed CORS.

## API routes

- `GET /api/health` — process and configuration status (not an external
  provider connectivity check)
- `GET /api/search?q={query}`
- `GET /api/quote/{ticker}`
- `GET /api/profile/{ticker}`
- `GET /api/news/{ticker}`
- `GET /api/history/{ticker}`
- `GET /api/research/start?ticker={ticker}` — SSE research workflow
- `GET /api/research/{report_id}` — saved report; requires MongoDB
- `GET /api/research/recent/list` — recent saved reports

## Tests and builds

From `backend`:

```powershell
python -m pytest tests/test_local_api.py -q
```

From `frontend`:

```powershell
npm test -- --watchAll=false
npm run build
```

The separate `test_alphalens_api.py` suite exercises a deployed service and
requires live data-provider credentials and MongoDB. Do not treat it as an
offline unit test.

Run the local and live integration diagnostics from the project root:

```powershell
.\diagnose_alphalens.ps1
```

The script checks local API health, the AAPL quote, frontend URL configuration,
port ownership, provider and Groq connectivity, MongoDB, and a temporary
agent-memory write/read/delete probe. It does not run a full AI research
workflow; use the optional `--research` diagnostics only when willing to use
Groq quota. Diagnostic probes use unique IDs and remove only their own records.

## Deployment

The repository includes `render.yaml` for the backend and `frontend/vercel.json`
for the React single-page app. Configure provider credentials, MongoDB (if
needed), and `CORS_ORIGINS` in Render's environment settings. Configure
`REACT_APP_BACKEND_URL` in Vercel before the frontend build. These manifests
contain environment variable names only; they do not contain secrets.
