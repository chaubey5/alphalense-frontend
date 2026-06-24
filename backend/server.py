"""
AlphaLens FastAPI backend.
- /api/search          : ticker search/resolve
- /api/quote/{ticker}  : quick quote
- /api/research/start  : SSE stream multi-agent research
- /api/research/{id}   : get cached report
- /api/health          : provider health
"""
from fastapi import FastAPI, APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import json
import uuid
import logging
import asyncio
from pathlib import Path
from datetime import datetime, timezone

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

from providers import (
    search_ticker, get_quote, get_profile, get_financials,
    get_ratios, get_peers, get_analyst, get_news, get_history,
)
from agents import run_pipeline_streaming

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("alphalens")

mongo_url = os.environ["MONGO_URL"]
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ["DB_NAME"]]

app = FastAPI(title="AlphaLens API")
api = APIRouter(prefix="/api")


@api.get("/")
async def root():
    return {"service": "AlphaLens", "status": "ok"}


@api.get("/search")
async def search(q: str = Query(..., min_length=1)):
    results = await search_ticker(q.strip())
    return {"results": results}


@api.get("/quote/{ticker}")
async def quote(ticker: str):
    data = await get_quote(ticker.upper())
    if not data:
        raise HTTPException(404, "Quote not found")
    return data


@api.get("/profile/{ticker}")
async def profile(ticker: str):
    data = await get_profile(ticker.upper())
    if not data:
        raise HTTPException(404, "Profile not found")
    return data


@api.get("/news/{ticker}")
async def news(ticker: str):
    return {"items": await get_news(ticker.upper())}


@api.get("/history/{ticker}")
async def history(ticker: str):
    return {"points": await get_history(ticker.upper())}


@api.get("/research/recent/list")
async def recent_reports():
    docs = await db.research_reports.find({}, {"_id": 0}).sort("generated_at", -1).limit(8).to_list(8)
    # Slim down
    out = []
    for d in docs:
        out.append({
            "id": d.get("id"),
            "ticker": d.get("ticker"),
            "company_name": d.get("company_name"),
            "recommendation": d.get("recommendation"),
            "confidence_score": d.get("confidence_score"),
            "generated_at": d.get("generated_at"),
        })
    return {"items": out}


@api.get("/health")
async def health():
    """Quick provider health check using a known ticker."""
    async def _check(name, coro):
        try:
            r = await asyncio.wait_for(coro, timeout=6)
            return {"name": name, "ok": r is not None}
        except Exception as e:
            return {"name": name, "ok": False, "error": str(e)[:120]}

    results = await asyncio.gather(
        _check("fmp", get_quote("AAPL")),
        _check("news", get_news("AAPL")),
    )
    return {"providers": results, "time": datetime.now(timezone.utc).isoformat()}


# ----------------- SSE: research pipeline -----------------

def _sse(event: str, data) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


@api.get("/research/start")
async def research_start(ticker: str = Query(..., min_length=1)):
    ticker = ticker.upper().strip()
    report_id = str(uuid.uuid4())

    async def gen():
        # Send start
        yield _sse("init", {"report_id": report_id, "ticker": ticker})

        # Fetch base data in parallel
        yield _sse("step", {"label": "Fetching market data…"})
        profile_t = asyncio.create_task(get_profile(ticker))
        quote_t = asyncio.create_task(get_quote(ticker))
        financials_t = asyncio.create_task(get_financials(ticker))
        ratios_t = asyncio.create_task(get_ratios(ticker))
        peers_t = asyncio.create_task(get_peers(ticker))
        analyst_t = asyncio.create_task(get_analyst(ticker))
        news_t = asyncio.create_task(get_news(ticker))
        history_t = asyncio.create_task(get_history(ticker))

        profile, quote, financials, ratios, peers, analyst, news_items, history = await asyncio.gather(
            profile_t, quote_t, financials_t, ratios_t, peers_t, analyst_t, news_t, history_t
        )

        if not profile and not quote:
            yield _sse("error", {"message": f"Ticker '{ticker}' not found at any data provider."})
            return

        # Send market data immediately so UI hydrates
        yield _sse("market_data", {
            "profile": profile, "quote": quote, "peers": peers,
            "analyst": analyst, "news": news_items, "history": history,
            "ratios": ratios, "financials": financials,
        })

        state = {
            "ticker": ticker, "profile": profile or {}, "quote": quote or {},
            "financials": financials or {}, "ratios": ratios or {}, "peers": peers or [],
            "analyst": analyst or {}, "news": news_items or [],
        }

        # Queue-based emitter so the orchestrator can push events while we yield
        queue: asyncio.Queue = asyncio.Queue()

        async def emit(evt: str, data):
            await queue.put((evt, data))

        async def runner():
            try:
                await run_pipeline_streaming(state, emit)
            except Exception as e:
                logger.exception("pipeline error")
                await queue.put(("error", {"message": str(e)}))
            finally:
                await queue.put(("__done__", None))

        task = asyncio.create_task(runner())

        while True:
            evt, data = await queue.get()
            if evt == "__done__":
                break
            yield _sse(evt, data)

        await task

        # Persist final report
        report = {
            "id": report_id,
            "ticker": ticker,
            "company_name": (profile or {}).get("name") or ticker,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "market_data": {
                "profile": profile, "quote": quote, "peers": peers,
                "analyst": analyst, "news": news_items, "history": history,
                "ratios": ratios, "financials": financials,
            },
            "agents": {
                "research": state.get("research"),
                "financial": state.get("financial"),
                "valuation": state.get("valuation"),
                "macro": state.get("macro"),
                "bull": state.get("bull"),
                "bear": state.get("bear"),
                "moderator": state.get("moderator"),
            },
            "recommendation": (state.get("moderator") or {}).get("recommendation"),
            "confidence_score": (state.get("moderator") or {}).get("confidence_score"),
        }
        try:
            await db.research_reports.insert_one(report)
        except Exception as e:
            logger.warning(f"save report failed: {e}")

        yield _sse("complete", {"report_id": report_id})

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@api.get("/research/{report_id}")
async def get_report(report_id: str):
    doc = await db.research_reports.find_one({"id": report_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Report not found")
    return doc


app.include_router(api)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
