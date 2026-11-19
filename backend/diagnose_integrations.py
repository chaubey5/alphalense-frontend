"""Opt-in live diagnostics for provider APIs, Groq, MongoDB, and AAPL research."""
from __future__ import annotations

import argparse
import asyncio
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from dotenv import load_dotenv

load_dotenv(Path(__file__).with_name(".env"))

import httpx
from pymongo import AsyncMongoClient

import providers
from agents import GROQ_API_KEY, GROQ_MODEL, run_pipeline_streaming
import server


def _show_result(
    name: str,
    endpoint: str,
    payload: Optional[Any],
    valid: Callable[[Any], bool],
) -> bool:
    diagnostic = providers.REQUEST_DIAGNOSTICS.get(endpoint, {})
    status = diagnostic.get("status_code")
    passed = payload is not None and valid(payload)
    detail = diagnostic.get("outcome", "no response")
    status_text = str(status) if status is not None else "unavailable"
    print(f"{name}: {'PASS' if passed else 'FAIL'} status={status_text} detail={detail}")
    if diagnostic.get("body"):
        print(f"  provider_body={diagnostic['body']}")
    elif diagnostic.get("error_type"):
        print(f"  error_type={diagnostic['error_type']}")
    return passed


async def _check_provider(
    name: str,
    url: str,
    params: Optional[Dict[str, Any]],
    headers: Optional[Dict[str, str]],
    endpoint: str,
    valid: Callable[[Any], bool],
    configured: bool,
) -> bool:
    if not configured:
        print(f"{name}: SKIP status=unavailable detail=credential_not_configured")
        return False
    payload = await providers._request_json(url, params, headers)
    return _show_result(name, endpoint, payload, valid)


async def _check_apis() -> bool:
    checks = [
        _check_provider(
            "FMP",
            f"{providers.FMP}/quote",
            {"symbol": "AAPL", "apikey": os.environ.get("FMP_API_KEY", "")},
            None,
            "financialmodelingprep.com/stable/quote",
            lambda payload: isinstance(payload, list)
            and bool(payload)
            and bool(payload[0].get("symbol"))
            and payload[0].get("price") is not None,
            bool(os.environ.get("FMP_API_KEY")),
        ),
        _check_provider(
            "Finnhub",
            f"{providers.FINNHUB_BASE}/quote",
            {"symbol": "AAPL", "token": os.environ.get("FINNHUB_API_KEY", "")},
            None,
            "finnhub.io/api/v1/quote",
            lambda payload: isinstance(payload, dict) and payload.get("c") is not None,
            bool(os.environ.get("FINNHUB_API_KEY")),
        ),
        _check_provider(
            "Alpha Vantage",
            providers.AV_BASE,
            {
                "function": "GLOBAL_QUOTE",
                "symbol": "AAPL",
                "apikey": os.environ.get("ALPHA_VANTAGE_API_KEY", ""),
            },
            None,
            "www.alphavantage.co/query",
            lambda payload: isinstance(payload, dict)
            and bool((payload.get("Global Quote") or {}).get("05. price")),
            bool(os.environ.get("ALPHA_VANTAGE_API_KEY")),
        ),
        _check_provider(
            "GNews",
            f"{providers.GNEWS_BASE}/search",
            {
                "q": "Apple",
                "lang": "en",
                "max": 1,
                "token": os.environ.get("GNEWS_API_KEY", ""),
            },
            None,
            "gnews.io/api/v4/search",
            lambda payload: isinstance(payload, dict)
            and isinstance(payload.get("articles"), list),
            bool(os.environ.get("GNEWS_API_KEY")),
        ),
        _check_provider(
            "Groq",
            "https://api.groq.com/openai/v1/models",
            None,
            {"Authorization": f"Bearer {GROQ_API_KEY}"},
            "api.groq.com/openai/v1/models",
            lambda payload: isinstance(payload, dict)
            and any(
                model.get("id") == GROQ_MODEL
                for model in payload.get("data", [])
                if isinstance(model, dict)
            ),
            bool(GROQ_API_KEY),
        ),
    ]
    results = await asyncio.gather(*checks)
    return all(results)


async def _check_mongodb() -> bool:
    url = os.environ.get("MONGO_URL")
    db_name = os.environ.get("DB_NAME")
    if not url or not db_name:
        print("MongoDB: SKIP status=unavailable detail=MONGO_URL_or_DB_NAME_missing")
        return False

    probe_id = f"alphalens-diagnostic-{uuid.uuid4()}"
    client = None
    inserted = False
    try:
        client = AsyncMongoClient(url, serverSelectionTimeoutMS=5000)
        collection = client[db_name]["_alphalens_diagnostics"]
        await client.admin.command("ping")
        await collection.insert_one({
            "_id": probe_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        inserted = True
        found = await collection.find_one({"_id": probe_id}, {"_id": 1})
        if not found:
            print("MongoDB: FAIL detail=read_after_write_not_found")
            return False
        deleted = await collection.delete_one({"_id": probe_id})
        inserted = deleted.deleted_count != 1
        passed = deleted.deleted_count == 1
        print(
            "MongoDB: "
            + ("PASS" if passed else "FAIL")
            + " detail=ping_read_write_delete"
        )
        return passed
    except Exception as exc:
        print(f"MongoDB: FAIL detail=operation_failed error_type={type(exc).__name__}")
        return False
    finally:
        if inserted:
            try:
                await collection.delete_one({"_id": probe_id})
            except Exception:
                print("MongoDB: WARNING detail=diagnostic_probe_cleanup_failed")
        if client is not None:
            await client.close()


async def _check_agent_memory() -> bool:
    if server.db is None:
        print("Agent memory: SKIP status=unavailable detail=storage_not_configured")
        return False

    report_id = f"alphalens-diagnostic-{uuid.uuid4()}"
    ticker = "ALPHALENS_DIAGNOSTIC"
    collection = server.db.agent_memory
    try:
        saved = await server._save_agent_memory(
            report_id,
            ticker,
            {
                "moderator": {
                    "recommendation": "HOLD",
                    "confidence_score": 50,
                    "executive_summary": "Temporary diagnostic record.",
                },
            },
        )
        loaded = await server._load_agent_memory(ticker, report_id)
        record = loaded.get("session") if loaded.get("available") else None
        passed = bool(
            saved
            and record
            and record.get("report_id") == report_id
            and record.get("recommendation") == "HOLD"
        )
        print(
            "Agent memory: "
            + ("PASS" if passed else "FAIL")
            + " detail=write_read"
        )
        return passed
    except Exception as exc:
        print(
            "Agent memory: FAIL "
            f"detail=operation_failed error_type={type(exc).__name__}"
        )
        return False
    finally:
        try:
            await collection.delete_one({"report_id": report_id})
        except Exception:
            print("Agent memory: WARNING detail=diagnostic_probe_cleanup_failed")


async def _check_research(ticker: str) -> bool:
    ticker = providers.normalize_ticker(ticker)
    market = await server._fetch_market_data(ticker)
    if not market.get("profile") or not market.get("quote"):
        print(f"{ticker} research: FAIL detail=profile_or_quote_unavailable")
        return False

    state = {
        "ticker": ticker,
        "profile": market["profile"] or {},
        "quote": market["quote"] or {},
        "financials": market["financials"] or {},
        "ratios": market["ratios"] or {},
        "peers": market["peers"] or [],
        "analyst": market["analyst"] or {},
        "news": market["news"] or [],
    }
    completed = set()

    async def emit(event: str, data: Dict[str, Any]) -> None:
        if event == "agent_done":
            completed.add(data.get("agent"))
            print(f"Agent {data.get('agent')}: PASS")

    try:
        await run_pipeline_streaming(state, emit)
    except Exception as exc:
        print(f"{ticker} research: FAIL error_type={type(exc).__name__}")
        return False
    expected = {"research", "financial", "valuation", "macro", "bull", "bear", "moderator"}
    moderator = state.get("moderator") or {}
    passed = expected <= completed and moderator.get("recommendation") in {
        "INVEST", "HOLD", "PASS",
    }
    print(
        f"{ticker} research: "
        + ("PASS" if passed else "FAIL")
        + f" agents={len(completed)}/7 recommendation="
        + ("present" if moderator.get("recommendation") else "missing")
    )
    return passed


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--live",
        action="store_true",
        help="Send authenticated requests to the configured external APIs.",
    )
    parser.add_argument(
        "--mongo",
        action="store_true",
        help="Perform a ping and temporary read/write/delete probe in MongoDB.",
    )
    parser.add_argument(
        "--research",
        action="store_true",
        help="Run provider + Groq research workflows for --tickers (uses API quota).",
    )
    parser.add_argument(
        "--tickers",
        nargs="+",
        default=["AAPL"],
        help="Symbols to use with --research (defaults to AAPL).",
    )
    args = parser.parse_args()
    if not args.live:
        parser.error("--live is required to send external API requests")

    results = [await _check_apis()]
    if args.mongo:
        results.append(await _check_mongodb())
        results.append(await _check_agent_memory())
    if args.research:
        for ticker in args.tickers:
            results.append(await _check_research(ticker))
    await providers.close_http_client()
    return 0 if all(results) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
