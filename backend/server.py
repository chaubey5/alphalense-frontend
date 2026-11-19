"""
AlphaLens FastAPI backend.
Endpoints under /api: search, quote, profile, news, history, research, health.
"""
from __future__ import annotations

import asyncio
import json
import logging
import math
import os
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, AsyncGenerator, Callable, Dict, List, Optional

from dotenv import load_dotenv
from fastapi import APIRouter, FastAPI, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import StreamingResponse
from pymongo import AsyncMongoClient
from pymongo.errors import OperationFailure, PyMongoError
from bson import ObjectId
from starlette.middleware.cors import CORSMiddleware

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

from providers import (  # noqa: E402
    close_http_client, get_analyst, get_financials, get_history, get_news, get_peers,
    get_profile, get_quote, get_ratios, normalize_ticker, search_ticker,
)
from agents import run_pipeline_streaming  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logger = logging.getLogger("alphalens")

mongo_url = os.environ.get("MONGO_URL")
mongo_client = AsyncMongoClient(mongo_url) if mongo_url else None
if mongo_client and os.environ.get("DB_NAME"):
    db = mongo_client[os.environ["DB_NAME"]]
else:
    db = None
    logger.warning("MongoDB not configured; report persistence endpoints will be disabled.")


async def _backfill_agent_memory() -> int:
    """Create memory records for existing completed reports without overwriting them."""
    if db is None:
        return 0

    try:
        reports = await db.research_reports.find(
            {"id": {"$exists": True}},
            {"_id": 0},
        ).sort("generated_at", -1).limit(100).to_list(100)
    except PyMongoError as exc:
        logger.warning(
            "agent memory backfill report lookup failed: %s",
            type(exc).__name__,
        )
        return 0

    now = datetime.now(timezone.utc)
    created = 0
    for report in reports:
        report_id = report.get("id")
        ticker = str(report.get("ticker") or "").strip().upper()
        if not report_id or not ticker:
            continue

        moderator = (report.get("agents") or {}).get("moderator") or {}
        record = {
            "report_id": report_id,
            "ticker": ticker,
            "updated_at": now,
            "expires_at": now + timedelta(days=30),
            "recommendation": report.get("recommendation") or moderator.get("recommendation"),
            "confidence_score": report.get("confidence_score") or moderator.get("confidence_score"),
            "executive_summary": moderator.get("executive_summary"),
            "key_reasons": moderator.get("key_reasons") or [],
            "risks": moderator.get("risks") or [],
            "data_sources": moderator.get("data_sources") or [],
            "agent_outputs": {
                key: value
                for key, value in (report.get("agents") or {}).items()
                if value
            },
        }
        try:
            result = await db.agent_memory.update_one(
                {"report_id": report_id},
                {"$setOnInsert": record},
                upsert=True,
            )
            created += 1 if result.upserted_id is not None else 0
        except PyMongoError as exc:
            logger.warning(
                "agent memory backfill record failed: %s",
                type(exc).__name__,
            )
    return created


async def _ensure_agent_memory_indexes() -> None:
    collection = db.agent_memory
    try:
        await collection.create_index("expires_at", expireAfterSeconds=0)
    except OperationFailure as exc:
        if exc.code not in (85, 86):
            logger.warning(
                "agent memory TTL index unavailable: error_type=%s code=%s",
                type(exc).__name__, exc.code,
            )
        else:
            try:
                indexes = await collection.index_information()
                existing = next(
                    (
                        (name, index)
                        for name, index in indexes.items()
                        if index.get("key") == [("expires_at", 1)]
                    ),
                    None,
                )
                if existing is None:
                    logger.warning(
                        "agent memory TTL index conflict: no compatible expires_at index found"
                    )
                elif existing[1].get("expireAfterSeconds") == 0:
                    pass
                else:
                    expired = await collection.count_documents({
                        "expires_at": {"$lte": datetime.now(timezone.utc)}
                    })
                    if expired:
                        logger.warning(
                            "agent memory TTL index migration skipped to preserve "
                            "existing records past expiry count=%d",
                            expired,
                        )
                    else:
                        await db.command({
                            "collMod": collection.name,
                            "index": {
                                "name": existing[0],
                                "expireAfterSeconds": 0,
                            },
                        })
                        logger.info("Updated existing agent memory TTL index.")
            except PyMongoError as migration_error:
                logger.warning(
                    "agent memory TTL index migration unavailable: error_type=%s code=%s",
                    type(migration_error).__name__,
                    getattr(migration_error, "code", None),
                )
    except PyMongoError as exc:
        logger.warning(
            "agent memory TTL index unavailable: error_type=%s code=%s",
            type(exc).__name__, getattr(exc, "code", None),
        )

    try:
        await collection.create_index([("ticker", 1), ("updated_at", -1)])
    except PyMongoError as exc:
        logger.warning(
            "agent memory ticker index unavailable: error_type=%s code=%s",
            type(exc).__name__, getattr(exc, "code", None),
        )


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncGenerator[None, None]:
    if db is not None:
        await _ensure_agent_memory_indexes()
        await _backfill_agent_memory()
    try:
        yield
    finally:
        if mongo_client is not None:
            await mongo_client.close()
        await close_http_client()


app = FastAPI(title="AlphaLens API", lifespan=lifespan)
api = APIRouter(prefix="/api")


def _normalize_ticker(ticker: str) -> str:
    try:
        return normalize_ticker(ticker)
    except ValueError as exc:
        raise HTTPException(
            422, "Ticker must be a valid symbol containing letters, digits, dots, or hyphens."
        ) from exc


def _has_market_data_credentials() -> bool:
    return any(os.environ.get(key) for key in (
        "FMP_API_KEY", "FINNHUB_API_KEY", "ALPHA_VANTAGE_API_KEY",
    ))


@app.get("/")
async def service_root() -> Dict[str, str]:
    return {"service": "AlphaLens", "status": "ok", "docs": "/docs"}


# ---------------- public read endpoints ----------------

@api.get("/")
async def root() -> Dict[str, str]:
    return {"service": "AlphaLens", "status": "ok"}


@api.get("/search")
async def search(q: str = Query(..., min_length=1)) -> Dict[str, List[Dict[str, Any]]]:
    return {"results": await search_ticker(q.strip())}


@api.get("/quote/{ticker}")
async def quote(ticker: str) -> Dict[str, Any]:
    data = await get_quote(_normalize_ticker(ticker))
    if not data:
        if not _has_market_data_credentials():
            raise HTTPException(503, "No quote provider is configured")
        raise HTTPException(404, "Quote not found")
    return data


@api.get("/profile/{ticker}")
async def profile(ticker: str) -> Dict[str, Any]:
    data = await get_profile(_normalize_ticker(ticker))
    if not data:
        if not _has_market_data_credentials():
            raise HTTPException(503, "No profile provider is configured")
        raise HTTPException(404, "Profile not found")
    return data


@api.get("/news/{ticker}")
async def news(ticker: str) -> Dict[str, List[Dict[str, Any]]]:
    return {"items": await get_news(_normalize_ticker(ticker))}


@api.get("/history/{ticker}")
async def history(ticker: str) -> Dict[str, List[Dict[str, Any]]]:
    return {"points": await get_history(_normalize_ticker(ticker))}


@api.get("/research/recent/list")
async def recent_reports() -> Dict[str, List[Dict[str, Any]]]:
    if db is None:
        raise HTTPException(503, "Report storage is not configured")
    try:
        docs = await db.research_reports.find({}, {"_id": 0}).sort(
            "generated_at", -1
        ).limit(8).to_list(8)
    except PyMongoError as exc:
        logger.warning("recent report query failed: %s", type(exc).__name__)
        raise HTTPException(503, "Report storage is unavailable") from exc
    keys = ("id", "ticker", "company_name", "recommendation", "confidence_score", "generated_at")
    return {"items": [{k: d.get(k) for k in keys} for d in docs]}


@api.get("/research/{report_id}/memory")
async def get_agent_memory(report_id: str) -> Dict[str, Any]:
    if db is None:
        raise HTTPException(503, "Agent memory storage is not configured")
    memory_collection = getattr(db, "agent_memory", None)
    if memory_collection is None:
        raise HTTPException(503, "Agent memory storage is not configured")
    try:
        doc = await memory_collection.find_one(
            {"report_id": report_id},
            {"_id": 0},
        )
    except PyMongoError as exc:
        logger.warning(
            "agent memory lookup failed: %s",
            type(exc).__name__,
        )
        raise HTTPException(503, "Agent memory storage is unavailable") from exc
    if not doc:
        raise HTTPException(404, "Agent memory not found")
    return jsonable_encoder(doc, custom_encoder={ObjectId: str})


@api.post("/research/memory/backfill")
async def backfill_agent_memory() -> Dict[str, int]:
    if db is None:
        raise HTTPException(503, "Agent memory storage is not configured")
    created = await _backfill_agent_memory()
    return {"memory_records_created": created}


@api.get("/health")
async def health() -> Dict[str, Any]:
    database_connected = False
    database_error = None
    if db is not None:
        try:
            await mongo_client.admin.command("ping")
            database_connected = True
        except Exception as exc:
            database_error = type(exc).__name__
            logger.warning(
                "MongoDB health ping failed: %s",
                database_error,
            )
    return {
        "status": "ok",
        "providers": [
            {"name": "fmp", "configured": bool(os.environ.get("FMP_API_KEY"))},
            {"name": "finnhub", "configured": bool(os.environ.get("FINNHUB_API_KEY"))},
            {
                "name": "alphavantage",
                "configured": bool(os.environ.get("ALPHA_VANTAGE_API_KEY")),
            },
            {
                "name": "news",
                "configured": bool(
                    os.environ.get("GNEWS_API_KEY") or os.environ.get("FINNHUB_API_KEY")
                ),
            },
            {"name": "gnews", "configured": bool(os.environ.get("GNEWS_API_KEY"))},
            {
                "name": "groq",
                "configured": bool(os.environ.get("GROQ_API_KEY")),
            },
        ],
        "database": {
            "configured": db is not None,
            "connected": database_connected,
            "error": database_error,
        },
        "time": datetime.now(timezone.utc).isoformat(),
    }


# ---------------- SSE: research pipeline ----------------

def _sse(event: str, data: Any) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


async def _fetch_market_data(ticker: str) -> Dict[str, Any]:
    """Fetch every market-data slice in parallel."""
    ticker = normalize_ticker(ticker)
    names = (
        "profile", "quote", "financials", "ratios",
        "peers", "analyst", "news", "history",
    )
    defaults = (None, None, {}, {}, [], None, [], [])
    results = await asyncio.gather(
        get_profile(ticker),
        get_quote(ticker),
        get_financials(ticker),
        get_ratios(ticker),
        get_peers(ticker),
        get_analyst(ticker),
        get_news(ticker),
        get_history(ticker),
        return_exceptions=True,
    )
    market = {}
    for name, result, default in zip(names, results, defaults):
        if isinstance(result, asyncio.CancelledError):
            raise result
        if isinstance(result, Exception):
            logger.error(
                "market-data component %s failed: %s",
                name, type(result).__name__,
            )
            market[name] = default
        else:
            market[name] = result

    profile = market["profile"]
    if profile and (
        not isinstance(profile, dict)
        or not profile.get("name")
        or profile.get("ticker") != ticker
    ):
        logger.warning("discarding unverified profile for ticker %s", ticker)
        market["profile"] = None

    quote = market["quote"]
    if quote and (
        not isinstance(quote, dict)
        or quote.get("ticker") != ticker
        or isinstance(quote.get("price"), bool)
        or not isinstance(quote.get("price"), (int, float))
        or not math.isfinite(quote.get("price"))
        or quote.get("price") <= 0
    ):
        logger.warning("discarding unverified quote for ticker %s", ticker)
        market["quote"] = None

    return market


def _build_report(report_id: str, ticker: str, market: Dict[str, Any],
                  state: Dict[str, Any]) -> Dict[str, Any]:
    profile_name = (market.get("profile") or {}).get("name") or ticker
    return {
        "id": report_id,
        "ticker": ticker,
        "company_name": profile_name,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "market_data": market,
        "agents": {k: state.get(k) for k in
                   ("research", "financial", "valuation", "macro", "bull", "bear", "moderator")},
        "recommendation": (state.get("moderator") or {}).get("recommendation"),
        "confidence_score": (state.get("moderator") or {}).get("confidence_score"),
    }


async def _load_agent_memory(ticker: str, report_id: str) -> Dict[str, Any]:
    if db is None:
        return {"available": False, "reason": "storage_unconfigured"}
    memory_collection = getattr(db, "agent_memory", None)
    if memory_collection is None:
        return {"available": False, "reason": "storage_unconfigured"}

    try:
        session = await memory_collection.find_one(
            {"report_id": report_id},
            {"_id": 0},
        )
        prior = await memory_collection.find(
            {
                "ticker": ticker,
                "expires_at": {"$gt": datetime.now(timezone.utc)},
            },
            {"_id": 0},
        ).sort("updated_at", -1).limit(3).to_list(3)
    except PyMongoError as exc:
        logger.warning(
            "agent memory lookup failed: %s",
            type(exc).__name__,
        )
        return {"available": False, "reason": "storage_unavailable"}

    records = []
    if session:
        records.append(session)
    for record in prior:
        if record.get("report_id") != report_id:
            records.append(record)

    if not records:
        return {"available": True, "session": None, "prior_research": []}
    session_record = session
    prior_research = [
        {
            "report_id": record.get("report_id"),
            "updated_at": record.get("updated_at"),
            "recommendation": record.get("recommendation"),
            "confidence_score": record.get("confidence_score"),
            "executive_summary": record.get("executive_summary"),
            "key_reasons": record.get("key_reasons") or [],
            "risks": record.get("risks") or [],
            "data_sources": record.get("data_sources") or [],
        }
        for record in records
        if record is not session_record
    ]
    return {
        "available": True,
        "session": session_record,
        "prior_research": prior_research,
    }


async def _save_agent_memory(
    report_id: str,
    ticker: str,
    state: Dict[str, Any],
) -> bool:
    if db is None:
        return False
    memory_collection = getattr(db, "agent_memory", None)
    if memory_collection is None:
        return False

    moderator = state.get("moderator") or {}
    now = datetime.now(timezone.utc)
    memory_record = {
        "report_id": report_id,
        "ticker": ticker,
        "updated_at": now,
        "expires_at": now + timedelta(days=30),
        "recommendation": moderator.get("recommendation"),
        "confidence_score": moderator.get("confidence_score"),
        "executive_summary": moderator.get("executive_summary"),
        "key_reasons": moderator.get("key_reasons") or [],
        "risks": moderator.get("risks") or [],
        "data_sources": moderator.get("data_sources") or [],
        "agent_outputs": {
            key: state.get(key)
            for key in (
                "research", "financial", "valuation", "macro",
                "bull", "bear", "moderator",
            )
            if state.get(key)
        },
    }

    try:
        await memory_collection.update_one(
            {"report_id": report_id},
            {"$set": memory_record},
            upsert=True,
        )
        return True
    except PyMongoError as exc:
        logger.warning(
            "agent memory save failed: %s",
            type(exc).__name__,
        )
        return False

async def _drain_pipeline(state: Dict[str, Any]) -> AsyncGenerator[str, None]:
    """Run the multi-agent pipeline and translate emitter callbacks into SSE chunks."""
    queue: asyncio.Queue = asyncio.Queue()

    async def emit(evt: str, data: Any) -> None:
        await queue.put((evt, data))

    async def runner() -> None:
        try:
            await run_pipeline_streaming(state, emit)
        except Exception as exc:
            logger.exception("research pipeline failed")
            message = str(exc) if isinstance(exc, RuntimeError) else (
                "The research pipeline failed. Check backend logs and try again."
            )
            await queue.put(("error", {"message": message}))
        finally:
            await queue.put(("__done__", None))

    task = asyncio.create_task(runner())
    pipeline_error: Optional[str] = None
    try:
        while True:
            try:
                evt, data = await asyncio.wait_for(queue.get(), timeout=15)
            except asyncio.TimeoutError:
                yield ": keep-alive\n\n"
                continue
            if evt == "__done__":
                break
            if evt == "error":
                pipeline_error = (data or {}).get("message") or (
                    "The research pipeline failed. Check backend logs and try again."
                )
            yield _sse(evt, data)
        await task
        if pipeline_error:
            raise RuntimeError(pipeline_error)
    finally:
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)


@api.get("/research/start")
async def research_start(ticker: str = Query(..., min_length=1)) -> StreamingResponse:
    ticker = _normalize_ticker(ticker)
    report_id = str(uuid.uuid4())

    async def gen() -> AsyncGenerator[str, None]:
        yield _sse("init", {"report_id": report_id, "ticker": ticker})
        yield _sse("step", {"label": "Fetching market data…"})

        try:
            memory_context = await _load_agent_memory(ticker, report_id)
        except Exception:
            logger.exception("agent memory lookup failed for %s", ticker)
            memory_context = {"available": False, "reason": "unexpected_error"}
        if not memory_context.get("available"):
            yield _sse("warning", {
                "message": "Prior agent memory is unavailable; fresh market data will still be analyzed.",
            })

        try:
            market = await _fetch_market_data(ticker)
        except Exception:
            logger.exception("market data request failed for %s", ticker)
            yield _sse("error", {
                "message": "Market data providers could not complete this request."
            })
            return
        if not market["profile"] or not market["quote"]:
            if market["profile"] and not market["quote"]:
                message = (
                    f"{ticker} was identified, but no provider returned a valid quote. "
                    "Check backend provider status logs."
                )
            elif market["quote"] and not market["profile"]:
                message = (
                    f"A quote was returned for {ticker}, but no matching company profile "
                    "was verified. Research was stopped to avoid analyzing the wrong company."
                )
            elif not _has_market_data_credentials():
                message = (
                    "No stock-data provider is configured. Set FMP_API_KEY, "
                    "FINNHUB_API_KEY, or ALPHA_VANTAGE_API_KEY in the backend environment."
                )
            else:
                message = (
                    f"No configured provider returned a valid profile or quote for {ticker}. "
                    "Check backend provider status logs for authentication, access, or rate-limit errors."
                )
            yield _sse("market_data", market)
            yield _sse("error", {"message": message})
            return

        yield _sse("market_data", market)

        state: Dict[str, Any] = {
            "ticker": ticker,
            "profile": market["profile"] or {},
            "quote": market["quote"] or {},
            "financials": market["financials"] or {},
            "ratios": market["ratios"] or {},
            "peers": market["peers"] or [],
            "analyst": market["analyst"] or {},
            "news": market["news"] or [],
            "memory_context": memory_context,
        }

        try:
            async for chunk in _drain_pipeline(state):
                yield chunk
        except RuntimeError:
            return

        report = _build_report(report_id, ticker, market, state)
        persisted = False
        if db is not None:
            try:
                await db.research_reports.insert_one(report)
                persisted = True
            except PyMongoError as exc:
                logger.warning("save report failed: %s", type(exc).__name__)
                yield _sse("warning", {
                    "message": "Report generated, but could not be saved to report storage."
                })
        else:
            logger.info("Report persistence skipped because MongoDB is not configured.")

        memory_persisted = await _save_agent_memory(report_id, ticker, state)
        yield _sse("complete", {
            "report_id": report_id,
            "persisted": persisted,
            "memory_persisted": memory_persisted,
        })

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
async def get_report(report_id: str) -> Dict[str, Any]:
    if db is None:
        raise HTTPException(503, "Report storage is not configured")
    try:
        doc = await db.research_reports.find_one({"id": report_id}, {"_id": 0})
    except PyMongoError as exc:
        logger.warning("report lookup failed: %s", type(exc).__name__)
        raise HTTPException(503, "Report storage is unavailable") from exc
    if not doc:
        raise HTTPException(404, "Report not found")
    return jsonable_encoder(doc, custom_encoder={ObjectId: str})


app.include_router(api)

cors_origins = [
    origin.strip()
    for origin in os.environ.get(
        "CORS_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000",
    ).split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_credentials="*" not in cors_origins,
    allow_origins=cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)
