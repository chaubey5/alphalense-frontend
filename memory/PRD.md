# AlphaLens — Product Requirements Document

## Original problem statement
Build an AI-powered investment research platform per the `AlphaLens_Engineering_Spec_v1.docx`.
User-provided integrations: FMP (primary), Finnhub (backup), Alpha Vantage, GNews,
OpenRouter, Google AI Studio, Sentry, Grafana, Supabase, Upstash Redis.

## User choices (Jan 2026)
- Tech stack: **Next.js-like, fulfilled with React + FastAPI** (closest to spec within env)
- LLM: **Emergent Universal Key with Claude Sonnet 4.5**
- Scope: **Core MVP** — search ticker → 6-agent analysis → recommendation dashboard
- Auth: **None** (public app, no accounts in MVP)
- UI: **Premium 3D glassmorphism, dark Bloomberg/Vision-Pro style**

## Architecture (delivered)
- **Frontend:** React 19 + Tailwind + Framer Motion + Recharts + react-router-dom
- **Backend:** FastAPI + httpx async data chain + emergentintegrations LlmChat
- **AI Orchestration:** Python orchestrator equivalent to LangGraph supervisor-worker
  pattern (Phase 1: Research+Financial+Valuation+Macro parallel; Phase 2: Bull+Bear parallel;
  Phase 3: Moderator). Streamed to client via Server-Sent Events.
- **Data layer:** FMP `stable/*` endpoints (search-name, quote, profile, financials,
  ratios-ttm, key-metrics-ttm, DCF, peers, price-target, grades-consensus, historical-EOD)
  with Finnhub and GNews fallbacks.
- **Persistence:** MongoDB (research_reports collection).
- **Cache layer:** Upstash Redis keys present in env; in-app caching deferred to v1.1.

## User personas
1. **Retail investor** running ad-hoc due-diligence before buying a stock.
2. **Junior analyst** preparing a first-cut research memo for review.
3. **Finance learner** exploring how DCF / multiples / bull-bear thinking work.

## Core requirements (static)
- Sub-90s research report from a single ticker input.
- Six specialist AI agents + one moderator producing INVEST/HOLD/PASS + confidence (0-100).
- Multi-provider data with graceful fallback.
- Transparent reasoning trace; every claim backed by data shown on the dashboard.
- Premium glassmorphism dark UI with motion, charts, and live streaming agent statuses.

## What's been implemented (2026-06-24, iter 1)
- [x] `/api/search` — ticker resolution (handles exact-ticker queries like TSLA)
- [x] `/api/quote/{ticker}`, `/api/profile/{ticker}`, `/api/news/{ticker}`, `/api/history/{ticker}`
- [x] `/api/research/start?ticker=...` — full SSE pipeline with 7 agents
- [x] `/api/research/{report_id}` + `/api/research/recent/list` — persisted reports
- [x] `/api/health` — provider health
- [x] Landing page with hero, search, suggestion pills, features grid, agent showcase
- [x] Research dashboard: agent pipeline strip (live status), verdict card with gauge,
  overview, 6-month price chart, revenue/net income bars, valuation panel, bull/bear cards,
  research+macro cards, analyst consensus, peers, news, reasoning log
- [x] data-testid coverage for all interactive + critical elements
- [x] Backend test suite (16/16 passing); E2E frontend SSE verified

## Backlog
### P0 (next session)
- Watchlist (add/remove + comparison view) — requires lightweight auth or anonymous local-storage variant
- PDF export of the report
- Redis caching with tiered TTL (30 min reports, 5 min quotes)

### P1
- Backtesting engine: "How would past INVEST/PASS verdicts have performed?"
- Compare page (side-by-side analysis of 2-3 tickers)
- Cross-provider data validation for critical metrics (trust-weighted merge)
- Sentry + Grafana wiring (keys provided)

### P2
- Supabase persistence layer + Google OAuth (Emergent-managed)
- Real-time pricing via Finnhub websocket
- Light theme + custom dashboards
- Rate limiting per IP via Upstash

## Smart enhancement (potential)
**Watchlist + email digests** — let users save 5-10 tickers and email them a one-paragraph
weekly delta ("AAPL — INVEST verdict held, fair value moved $211 → $218"). This is the highest-conversion
feature for habitual retail-investor use.
