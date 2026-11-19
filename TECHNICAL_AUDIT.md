# AlphaLens Technical Audit

## Audit baseline

This report records findings from the repository before implementation changes.
The worktree already contained edits to `backend/agents.py` and
`backend/server.py`, an untracked `backend/locustfile.py`, and an unrelated
untracked file at the repository root. Those files are pre-existing user
changes and are not part of this audit's implementation.

## Findings

### Critical: exposed credentials

- `backend/.env` contains populated credentials for the database, LLM and
  external data services. The same data-provider credentials were also pasted
  into the conversation.
- `.env` is ignored and not tracked by Git, but credentials have nevertheless
  been exposed. All affected credentials must be revoked/rotated. Do not reuse
  them. The file is not modified or copied by this audit.
- The frontend template embedded an analytics project token and loaded
  third-party telemetry scripts. Those scripts/token were removed because the
  template does not need them and they generated unauthorized requests.
- Neither backend nor frontend had a safe environment template. `.env.example`
  files now list variable names only. Wildcard CORS no longer enables
  credentials.

### Backend and provider layer

- The backend dependency file did not declare `openai`, which `agents.py`
  imports, and pinned old FastAPI/PyMongo/Motor versions. It now declares the
  direct application dependencies and PyMongo's async driver.
- Provider requests previously created a new `httpx.AsyncClient` per request,
  lacked retries/de-duplication, logged response bodies, and attempted
  authenticated calls with empty keys. The provider layer now reuses a client,
  applies bounded exponential retries, coalesces duplicate calls, redacts
  credentials from cache keys/logs, and skips calls without a key. HTTP errors,
  timeouts, invalid JSON, and provider-level errors returned with HTTP 200 are
  now distinguished in sanitized diagnostics.
- Quote and profile lookups now normalize symbols, validate returned ticker
  identity/data quality, and fall through FMP → Finnhub → Alpha Vantage. The
  Alpha Vantage fallback uses `GLOBAL_QUOTE` and `OVERVIEW`; it is still subject
  to the account's endpoint permissions and quota.
- `/api/health` previously performed external requests and mislabeled fallback
  results. It is now a quick liveness/configuration endpoint that separately
  lists FMP, Finnhub, Alpha Vantage, news, and Groq key configuration; it
  deliberately does not claim that credentials or MongoDB connections are live.
- MongoDB has moved from Motor to PyMongo Async. Report list/lookups now return
  explicit 503 responses when storage is unconfigured or unavailable. The
  connection is still optional.
- Report generation now marks persistence success explicitly, warns when the
  save fails, and does not emit a successful SSE `complete` event after an
  agent-pipeline error.
- The FMP stable endpoints are present in code, but the official docs page
  could not be fetched in this audit environment (HTTP 403). Existing API
  configuration and entitlements cannot be verified without a rotated key.
- Finnhub endpoints and Alpha Vantage's `OVERVIEW` query are still documented
  by their official documentation. Alpha Vantage's public API is quota-limited;
  fallback does not imply a paid tier or greater quota.
- Yahoo chart API is an undocumented provider endpoint. It should remain a
  best-effort chart fallback, not be treated as a contracted/guaranteed API.
- `MONGO_URL` is consumed by the server, but the configured Redis/Upstash,
  Supabase, Gemini, and Emergent variables are not integrated in the app.

### Agent workflow

- LangGraph now models all seven agents as a sequential state graph. The
  sequential edges and shared request semaphore prevent uncontrolled Groq
  concurrency while preserving per-agent SSE updates.
- A failed LLM call previously returned an empty string and could still emit
  successful `agent_done` events. Failures now create an explicit SSE error.
- Financial metrics were requested from the model with zero defaults. Numeric
  income-statement metrics are now calculated from provider statements, and
  unsupported valuation/upside/downside values remain null.
- Agent JSON is validated/normalized before events; the moderator accepts only
  INVEST/HOLD/PASS and a 0–100 confidence score. It attaches retrieved metrics,
  sources, and risks rather than trusting model-provided financial figures.
- The moderator now requires a matching normalized profile and quote plus
  retrieved financial statements or multiple ratios before generating a
  recommendation.
- Persistent agent memory is now implemented using MongoDB
  `agent_memory` records, with 30-day TTL, per-ticker history, and
  report/session lookup. Memory is supplied to the Moderator as historical
  context and is never counted as fresh financial evidence.
### Frontend

- Frontend API callers previously generated invalid URLs if the backend URL
  was missing. Production now fails over to the fixed Render URL and accepts
  only that URL from build-time configuration; development remains pinned to
  localhost:8001.
- SSE failures now stop the stream and appear in the dashboard. Empty cards
  display an explicit unavailable state after completion; missing chart values
  are no longer coerced to zero.
- CEO/profile fields, data-source labels, moderator risks/metrics, and
  unavailable-result states are rendered. Unsupported static homepage claims
  were removed.
- The frontend production build passes with React 19 and Create React App 5.
  Both npm and Yarn lockfiles remain; the existing deployment builds
  successfully, so package-manager standardization is deferred rather than
  risk changing its dependency resolution in this deployment update.

### Tests, configuration, and deployment

- `backend/tests/test_alphalens_api.py` was tied to a remote backend and an
  absolute `/app/frontend/.env` path. It now has an explicit opt-in flag and a
  workspace-relative fallback. Local route/SSE/provider/agent tests were added.
- `backend/test_backend.py` is a print-only script; its values are labeled as
  examples and still does not provide assertions or prove service functionality.
- `backend/diagnose_integrations.py` provides explicitly opt-in live probes for
  FMP, Finnhub, Alpha Vantage, GNews, Groq, optional MongoDB read/write/delete,
  and selected ticker workflows. Live probes were not run because credentials
  were exposed in chat and must be rotated.
- Render and Vercel manifests are now present. Local setup uses
  `frontend/.env.local`; ignored frontend env files point to the local backend.
  The deployed production bundle was verified to use the Render backend URL.
- Removed the unused root `requirements.txt` environment snapshot and the
  unused Node manifests from the Python backend; `backend/requirements.txt`
  is the service dependency source.
- No application authentication exists. Report endpoints are public when
  MongoDB is configured; production use with sensitive or user-specific reports
  needs an access-control design.

## API status checked

- **FMP:** Existing code uses `/stable` endpoints. Official docs returned HTTP
  403 during this audit, so endpoint access/plan availability remains
  unverified. No new subscription or key is assumed.
- **Finnhub:** Official API docs remain available; the code uses documented
  REST endpoint patterns. Key scope and endpoint quota remain unverified.
- **Alpha Vantage:** Official documentation still lists the `OVERVIEW` query
  and existing API format. Availability and quota depend on the account.
- **Groq:** Official model documentation currently lists
  `openai/gpt-oss-120b` as a production model, so the existing model ID is not
  replaced. The integration uses Groq's OpenAI-compatible API.
- No replacement data provider is added; no provider integration is removed.
  Motor was removed in favor of PyMongo Async.

## Implementation and verification

- Corrected `backend/requirements.txt`, added backend/frontend environment
  examples, repaired `.gitignore`, and documented the actual architecture and
  launch steps in `README.md`.
- Added Render and Vercel configuration. Added provider retry/backoff,
  duplicate-request coalescing, ticker validation, SSE keepalives/cancellation,
  DB error reporting, and accurate liveness health output.
- Made LLM client creation lazy, removed response-content logging, stopped
  success-shaped fallbacks, validated agent outputs, and constrained numeric
  output to retrieved or deterministically derived values.
- Removed unused embedded telemetry from the frontend HTML. A browser smoke
  test verified the landing page and the dashboard's visible provider-error
  state; no HTTP failures or console errors were captured after removal.
- `python -m pytest tests -q` from `backend`: 69 passed, 16 live integration
  tests skipped by default. Offline cases cover ticker normalization, provider
  fallback/identity/empty data, 401/403/404/429/5xx, rate limits, timeouts,
  Alpha Vantage response shapes, SSE failures, and insufficient agent evidence.
- `npm test -- --watchAll=false --passWithNoTests`: exits successfully, but the
  frontend currently contains no automated test files.
- `npm run build`: succeeds. Node reports an upstream `fs.F_OK` deprecation
  warning during the build.
- Local FastAPI startup, `/api/health`, invalid ticker validation, route tests,
  and mocked SSE completion/error paths were exercised without provider calls.
- Missing profile/quote is now reported as provider failure/configuration
  detail, not a symbol-not-found conclusion; agents require both a verified
  profile and quote before starting.
- Latest backend suite: 69 passed, 16 live integration tests skipped;
  `pip check`, Python compilation, `git diff --check`, and deployment manifest
  parsing passed. Frontend production build passed; frontend test command found
  no test files.
- The production Vercel page and its compiled Render API destination were
  checked. Render `/api/health` returned HTTP 200, but MongoDB reported
  `connected=false` with a server-selection timeout. `/api/quote/AAPL`
  returned HTTP 404 (`Quote not found`); the AAPL SSE flow stopped at market
  data, before any agents or report persistence ran. No live research report
  or memory write is claimed as verified on Render.
- The production CORS preflight previously returned a wildcard origin. The
  current backend configuration now rejects wildcard origins and explicitly
  allows the verified stable Vercel production domain; this requires the
  Render service to deploy the current commit.
- Git history scans found no credential-like values in tracked blobs or
  historical environment files. Live provider/Groq/Mongo probes should be
  rerun only after exposed credentials have been rotated and reconfigured.
