"""AlphaLens market-data providers, safe diagnostics, caching, and fallbacks."""
from __future__ import annotations

import asyncio
from email.utils import parsedate_to_datetime
import json
import logging
import math
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).with_name('.env'))
import re
import time
from datetime import datetime, timezone
from urllib.parse import urlsplit
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)

FMP_KEY = os.environ.get("FMP_API_KEY", "")
FINNHUB_KEY = os.environ.get("FINNHUB_API_KEY", "")
AV_KEY = os.environ.get("ALPHA_VANTAGE_API_KEY", "")
GNEWS_KEY = os.environ.get("GNEWS_API_KEY", "")

FMP = "https://financialmodelingprep.com/stable"
FINNHUB_BASE = "https://finnhub.io/api/v1"
AV_BASE = "https://www.alphavantage.co/query"
GNEWS_BASE = "https://gnews.io/api/v4"
YAHOO_BASE = "https://query1.finance.yahoo.com/v8/finance/chart"

TIMEOUT = httpx.Timeout(15.0, connect=8.0)
MAX_RETRIES = 2

# ---------------- TTL cache ----------------
_CACHE: Dict[str, tuple[float, Any]] = {}
_IN_FLIGHT: Dict[str, asyncio.Task] = {}
_HTTP_CLIENT: Optional[httpx.AsyncClient] = None
CACHE_TTL = 600  # 10 minutes
REQUEST_DIAGNOSTICS: Dict[str, Dict[str, Any]] = {}
_MAX_DIAGNOSTICS = 64
_TICKER_PATTERN = re.compile(r"^[A-Z0-9]+(?:[.-][A-Z0-9]+)*$")


def normalize_ticker(ticker: str) -> str:
    normalized = ticker.strip().upper()
    if len(normalized) > 15 or not _TICKER_PATTERN.fullmatch(normalized):
        raise ValueError("Invalid ticker symbol")
    return normalized


def _matches_ticker(value: Any, ticker: str) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        provider_ticker = normalize_ticker(value)
        return provider_ticker.replace(".", "-") == ticker.replace(".", "-")
    except ValueError:
        return False


def _safe_float(value: Any) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _safe_int(value: Any) -> Optional[int]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return int(number) if math.isfinite(number) else None


def _provider_endpoint(url: str) -> tuple[str, str]:
    parsed = urlsplit(url)
    host = parsed.hostname or "unknown"
    providers = {
        "financialmodelingprep.com": "fmp",
        "finnhub.io": "finnhub",
        "alphavantage.co": "alphavantage",
        "gnews.io": "gnews",
        "api.groq.com": "groq",
        "query1.finance.yahoo.com": "yahoo",
    }
    return providers.get(host, host), f"{host}{parsed.path}"


def redact_sensitive_text(body: str, params: Optional[Dict[str, Any]] = None,
                          headers: Optional[Dict[str, str]] = None) -> str:
    secrets = []
    for source in (params or {}, headers or {}):
        for key, value in source.items():
            if value and any(word in key.lower() for word in (
                "key", "token", "secret", "password", "authorization",
            )):
                secret = str(value)
                secrets.append(secret)
                if key.lower() == "authorization" and secret.lower().startswith("bearer "):
                    secrets.append(secret[7:])
    for secret in sorted(set(secrets), key=len, reverse=True):
        body = body.replace(secret, "[REDACTED]")
    body = re.sub(
        r"(?i)(authorization|api[\s_-]?key|access[_\s-]?token|token|secret|password)"
        r'(["\']?\s*[:=]\s*["\']?)[^"\'\s,;}]+',
        r"\1\2[REDACTED]",
        body,
    )
    body = re.sub(r"(?i)\bBearer\s+\S+", "Bearer [REDACTED]", body)
    return body[:500]


def _safe_error_body(response: httpx.Response,
                     params: Optional[Dict[str, Any]] = None,
                     headers: Optional[Dict[str, str]] = None) -> str:
    try:
        payload = response.json()
    except ValueError:
        return redact_sensitive_text(response.text, params, headers)

    def redact(value: Any) -> Any:
        if isinstance(value, dict):
            return {
                key: (
                    "[REDACTED]"
                    if any(word in str(key).lower() for word in (
                        "key", "token", "secret", "password", "authorization",
                    ))
                    else redact(item)
                )
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [redact(item) for item in value[:10]]
        if isinstance(value, str):
            return redact_sensitive_text(value, params, headers)
        return value

    return redact_sensitive_text(json.dumps(redact(payload), ensure_ascii=True), params, headers)


def _api_error(payload: Any) -> bool:
    if not isinstance(payload, dict):
        return False
    return any(
        payload.get(key)
        for key in ("Error Message", "Note", "Information", "error", "errors")
    )


def _record_request(endpoint: str, details: Dict[str, Any]) -> None:
    REQUEST_DIAGNOSTICS[endpoint] = {
        **details,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }
    while len(REQUEST_DIAGNOSTICS) > _MAX_DIAGNOSTICS:
        REQUEST_DIAGNOSTICS.pop(next(iter(REQUEST_DIAGNOSTICS)))


def _retry_delay(value: Optional[str], attempt: int) -> float:
    if value:
        try:
            return min(max(float(value), 0.0), 4.0)
        except ValueError:
            try:
                date = parsedate_to_datetime(value)
                if date.tzinfo is None:
                    date = date.replace(tzinfo=timezone.utc)
                return min(max((date - datetime.now(timezone.utc)).total_seconds(), 0.0), 4.0)
            except (TypeError, ValueError, OverflowError):
                pass
    return 0.25 * (2 ** attempt)


def _http_client() -> httpx.AsyncClient:
    global _HTTP_CLIENT
    if _HTTP_CLIENT is None or _HTTP_CLIENT.is_closed:
        _HTTP_CLIENT = httpx.AsyncClient(timeout=TIMEOUT)
    return _HTTP_CLIENT


async def close_http_client() -> None:
    global _HTTP_CLIENT
    if _HTTP_CLIENT is not None and not _HTTP_CLIENT.is_closed:
        await _HTTP_CLIENT.aclose()
    _HTTP_CLIENT = None


def _cache_key(url: str, params: Optional[Dict[str, Any]]) -> str:
    if not params:
        return url
    cache_params = {
        key: "<redacted>" if key in {"apikey", "token"} else value
        for key, value in params.items()
    }
    return url + "?" + json.dumps(cache_params, sort_keys=True)


async def _request_json(
    url: str,
    params: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
) -> Optional[Any]:
    provider, endpoint = _provider_endpoint(url)
    for attempt in range(MAX_RETRIES + 1):
        try:
            response = await _http_client().get(url, params=params, headers=headers or {})
            if response.status_code == 429 or response.status_code >= 500:
                if attempt < MAX_RETRIES:
                    delay = _retry_delay(response.headers.get("Retry-After"), attempt)
                    logger.warning(
                        "%s request status=%d endpoint=%s attempt=%d/%d body=%s",
                        provider, response.status_code, endpoint, attempt + 1,
                        MAX_RETRIES + 1, _safe_error_body(response, params, headers),
                    )
                    await asyncio.sleep(delay)
                    continue
            response.raise_for_status()
            try:
                payload = response.json()
            except ValueError:
                body = _safe_error_body(response, params, headers)
                _record_request(endpoint, {
                    "provider": provider, "status_code": response.status_code,
                    "outcome": "invalid_json", "body": body,
                })
                logger.warning(
                    "%s request status=%d endpoint=%s returned invalid JSON body=%s",
                    provider, response.status_code, endpoint, body,
                )
                return None
            if _api_error(payload):
                body = _safe_error_body(response, params, headers)
                _record_request(endpoint, {
                    "provider": provider, "status_code": response.status_code,
                    "outcome": "api_error", "body": body,
                })
                logger.warning(
                    "%s API error status=%d endpoint=%s body=%s",
                    provider, response.status_code, endpoint, body,
                )
                return None
            _record_request(endpoint, {
                "provider": provider, "status_code": response.status_code,
                "outcome": "ok",
            })
            return payload
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            body = _safe_error_body(exc.response, params, headers)
            _record_request(endpoint, {
                "provider": provider, "status_code": status,
                "outcome": "http_error", "body": body,
            })
            logger.warning(
                "%s request status=%d endpoint=%s body=%s",
                provider, status, endpoint, body,
            )
            return None
        except httpx.TimeoutException as exc:
            if attempt < MAX_RETRIES:
                logger.warning(
                    "%s request timeout endpoint=%s attempt=%d/%d",
                    provider, endpoint, attempt + 1, MAX_RETRIES + 1,
                )
                await asyncio.sleep(0.25 * (2 ** attempt))
                continue
            _record_request(endpoint, {
                "provider": provider, "status_code": None,
                "outcome": "timeout", "error_type": type(exc).__name__,
            })
            logger.warning(
                "%s request timeout endpoint=%s error_type=%s",
                provider, endpoint, type(exc).__name__,
            )
            return None
        except httpx.RequestError as exc:
            if attempt < MAX_RETRIES:
                await asyncio.sleep(0.25 * (2 ** attempt))
                continue
            _record_request(endpoint, {
                "provider": provider, "status_code": None,
                "outcome": "request_error", "error_type": type(exc).__name__,
            })
            logger.warning(
                "%s request failed endpoint=%s error_type=%s",
                provider, endpoint, type(exc).__name__,
            )
            return None
    return None


async def _get(
    url: str,
    params: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
    ttl: int = CACHE_TTL,
) -> Optional[Any]:
    if params and any(
        name in params and not params[name]
        for name in ("apikey", "token")
    ):
        logger.warning("Skipping %s request because its API key is not configured", url)
        return None

    key = _cache_key(url, params)
    now = time.time()
    cached = _CACHE.get(key)
    if cached and now - cached[0] < ttl:
        return cached[1]

    task = _IN_FLIGHT.get(key)
    if task is None:
        async def fetch() -> Optional[Any]:
            data = await _request_json(url, params, headers)
            if data is not None:
                completed_at = time.time()
                if len(_CACHE) > 1024:
                    expired = [
                        cache_key for cache_key, (created_at, _) in _CACHE.items()
                        if completed_at - created_at >= CACHE_TTL
                    ]
                    for cache_key in expired:
                        _CACHE.pop(cache_key, None)
                _CACHE[key] = (completed_at, data)
            return data

        task = asyncio.create_task(fetch())
        _IN_FLIGHT[key] = task

        def remove_in_flight(completed: asyncio.Task) -> None:
            if _IN_FLIGHT.get(key) is completed:
                _IN_FLIGHT.pop(key, None)

        task.add_done_callback(remove_in_flight)

    return await asyncio.shield(task)


# ---------------- Search ----------------
def _is_tickerish(q: str) -> bool:
    try:
        normalize_ticker(q)
        return True
    except ValueError:
        return False


def _normalize_fmp_results(rows: List[Dict[str, Any]], skip: set) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for d in rows or []:
        sym = d.get("symbol")
        if not sym or sym in skip:
            continue
        out.append({
            "ticker": sym,
            "name": d.get("name"),
            "exchange": d.get("exchange") or d.get("exchangeFullName"),
            "currency": d.get("currency"),
        })
    return out


async def search_ticker(query: str) -> List[Dict[str, Any]]:
    q = (query or "").strip()
    if not q:
        return []

    seeded: List[Dict[str, Any]] = []
    if _is_tickerish(q):
        prof = await get_profile(q.upper())
        if prof and prof.get("ticker"):
            seeded.append({
                "ticker": prof["ticker"],
                "name": prof.get("name") or prof["ticker"],
                "exchange": prof.get("exchange"),
                "currency": prof.get("currency") or "USD",
            })

    fmp = await _get(f"{FMP}/search-name", {"query": q, "limit": 10, "apikey": FMP_KEY})
    if isinstance(fmp, list) and fmp:
        seen = {x["ticker"] for x in seeded}
        return (seeded + _normalize_fmp_results(fmp, seen))[:8]
    if seeded:
        return seeded

    fh = await _get(f"{FINNHUB_BASE}/search", {"q": q, "token": FINNHUB_KEY})
    if isinstance(fh, dict) and fh.get("result"):
        return [
            {"ticker": r.get("symbol"), "name": r.get("description"),
             "exchange": "", "currency": "USD"}
            for r in fh["result"][:8] if r.get("symbol")
        ]
    return []


# ---------------- Quote ----------------
async def get_quote(ticker: str) -> Optional[Dict[str, Any]]:
    ticker = normalize_ticker(ticker)
    data = await _get(f"{FMP}/quote", {"symbol": ticker, "apikey": FMP_KEY})
    if isinstance(data, list):
        quote = next(
            (row for row in data if isinstance(row, dict)
             and _matches_ticker(row.get("symbol"), ticker)),
            None,
        )
        price = _safe_float((quote or {}).get("price"))
        if quote and price is not None and price > 0:
            return {
                "ticker": ticker, "name": quote.get("name") or ticker,
                "price": price, "change": _safe_float(quote.get("change")),
                "changesPercentage": _safe_float(quote.get("changePercentage")),
                "dayLow": _safe_float(quote.get("dayLow")),
                "dayHigh": _safe_float(quote.get("dayHigh")),
                "yearLow": _safe_float(quote.get("yearLow")),
                "yearHigh": _safe_float(quote.get("yearHigh")),
                "marketCap": _safe_float(quote.get("marketCap")),
                "volume": _safe_int(quote.get("volume")),
                "avgVolume": _safe_float(quote.get("priceAvg50")),
                "exchange": quote.get("exchange"),
                "open": _safe_float(quote.get("open")),
                "previousClose": _safe_float(quote.get("previousClose")),
                "source": "fmp",
            }

    fh = await _get(f"{FINNHUB_BASE}/quote", {"symbol": ticker, "token": FINNHUB_KEY})
    fh_price = _safe_float((fh or {}).get("c")) if isinstance(fh, dict) else None
    if fh_price is not None and fh_price > 0:
        fhm = await _get(f"{FINNHUB_BASE}/stock/metric", {
            "symbol": ticker, "metric": "all", "token": FINNHUB_KEY,
        })
        metric = (fhm or {}).get("metric") or {}
        return {
            "ticker": ticker, "name": ticker, "price": fh_price,
            "change": _safe_float(fh.get("d")),
            "changesPercentage": _safe_float(fh.get("dp")),
            "dayLow": _safe_float(fh.get("l")),
            "dayHigh": _safe_float(fh.get("h")),
            "yearLow": _safe_float(metric.get("52WeekLow")),
            "yearHigh": _safe_float(metric.get("52WeekHigh")),
            "marketCap": (
                _safe_float(metric.get("marketCapitalization")) * 1_000_000
                if _safe_float(metric.get("marketCapitalization")) is not None
                else None
            ),
            "volume": None, "avgVolume": None, "exchange": "",
            "open": _safe_float(fh.get("o")),
            "previousClose": _safe_float(fh.get("pc")),
            "source": "finnhub",
        }

    av = await _get(AV_BASE, {
        "function": "GLOBAL_QUOTE",
        "symbol": ticker,
        "apikey": AV_KEY,
    })
    global_quote = (av or {}).get("Global Quote") if isinstance(av, dict) else None
    av_price = _safe_float((global_quote or {}).get("05. price"))
    if (
        isinstance(global_quote, dict)
        and _matches_ticker(global_quote.get("01. symbol"), ticker)
        and av_price is not None
        and av_price > 0
    ):
        return {
            "ticker": ticker,
            "name": ticker,
            "price": av_price,
            "change": _safe_float(global_quote.get("09. change")),
            "changesPercentage": _safe_float(
                str(global_quote.get("10. change percent", "")).rstrip("%")
            ),
            "dayLow": _safe_float(global_quote.get("04. low")),
            "dayHigh": _safe_float(global_quote.get("03. high")),
            "yearLow": None,
            "yearHigh": None,
            "marketCap": None,
            "volume": _safe_int(global_quote.get("06. volume")),
            "avgVolume": None,
            "exchange": "",
            "open": _safe_float(global_quote.get("02. open")),
            "previousClose": _safe_float(global_quote.get("08. previous close")),
            "source": "alphavantage",
        }
    return None


# ---------------- Profile ----------------
async def _av_overview(ticker: str) -> Dict[str, Any]:
    data = await _get(AV_BASE, {"function": "OVERVIEW", "symbol": ticker, "apikey": AV_KEY})
    if isinstance(data, dict) and data.get("Symbol"):
        return data
    return {}


def _av_profile(data: Dict[str, Any], ticker: str) -> Dict[str, Any]:
    if not data or not data.get("Symbol"):
        return {}
    return {
        "ticker": ticker,
        "name": data.get("Name") or ticker,
        "sector": (data.get("Sector") or "").title(),
        "industry": (data.get("Industry") or "").title(),
        "ceo": None,
        "country": data.get("Country"),
        "website": data.get("OfficialSite"),
        "description": data.get("Description"),
        "employees": _safe_int(data.get("FullTimeEmployees")),
        "ipoDate": None,
        "image": None,
        "marketCap": _safe_float(data.get("MarketCapitalization")),
        "beta": _safe_float(data.get("Beta")),
        "currency": data.get("Currency"),
        "exchange": data.get("Exchange"),
        "source": "alphavantage",
    }


def _merge_profile(base: Dict[str, Any], av: Dict[str, Any]) -> Dict[str, Any]:
    """Fill missing fields in `base` from Alpha Vantage OVERVIEW output."""
    if not av:
        return base
    out = dict(base)
    if not out.get("name"):
        out["name"] = av.get("Name")
    if not out.get("description"):
        out["description"] = av.get("Description") or out.get("description")
    if not out.get("sector"):
        out["sector"] = (av.get("Sector") or "").title() or out.get("sector")
    if not out.get("industry"):
        out["industry"] = (av.get("Industry") or "").title() or out.get("industry")
    if not out.get("country"):
        out["country"] = av.get("Country")
    if not out.get("website"):
        out["website"] = av.get("OfficialSite")
    if not out.get("employees"):
        out["employees"] = _safe_int(av.get("FullTimeEmployees"))
    if not out.get("beta"):
        out["beta"] = _safe_float(av.get("Beta"))
    if not out.get("marketCap"):
        out["marketCap"] = _safe_float(av.get("MarketCapitalization"))
    if not out.get("currency"):
        out["currency"] = av.get("Currency")
    if not out.get("exchange"):
        out["exchange"] = av.get("Exchange")
    if av:
        sources = [part for part in str(out.get("source") or "").split("+") if part]
        if "alphavantage" not in sources:
            sources.append("alphavantage")
        out["source"] = "+".join(sources)
    return out


def _profile_complete(p: Dict[str, Any]) -> bool:
    """A 'good enough' profile has CEO, employees, beta, and description."""
    return bool(p.get("ceo") and p.get("employees") and p.get("beta") and p.get("description"))


async def get_profile(ticker: str) -> Optional[Dict[str, Any]]:
    ticker = normalize_ticker(ticker)
    base: Dict[str, Any] = {}

    data = await _get(f"{FMP}/profile", {"symbol": ticker, "apikey": FMP_KEY})
    if isinstance(data, list):
        p = next(
            (row for row in data if isinstance(row, dict)
             and _matches_ticker(row.get("symbol"), ticker)
             and row.get("companyName")),
            None,
        )
        if p:
            base = {
                "ticker": ticker, "name": p.get("companyName"),
                "sector": p.get("sector"), "industry": p.get("industry"),
                "ceo": p.get("ceo"), "country": p.get("country"),
                "website": p.get("website"), "description": p.get("description"),
                "employees": _safe_int(p.get("fullTimeEmployees")),
                "ipoDate": p.get("ipoDate"), "image": p.get("image"),
                "marketCap": _safe_float(p.get("marketCap")),
                "beta": _safe_float(p.get("beta")),
                "currency": p.get("currency"), "exchange": p.get("exchange"),
                "source": "fmp",
            }

    if not base or not _profile_complete(base):
        fh = await _get(f"{FINNHUB_BASE}/stock/profile2", {
            "symbol": ticker, "token": FINNHUB_KEY,
        })
        if isinstance(fh, dict) and fh.get("name"):
            fh_profile = {
                "ticker": ticker, "name": fh.get("name"),
                "sector": fh.get("finnhubIndustry"),
                "industry": fh.get("finnhubIndustry"),
                "ceo": None, "country": fh.get("country"),
                "website": fh.get("weburl"), "description": None,
                "employees": None, "ipoDate": fh.get("ipo"),
                "image": fh.get("logo"),
                "marketCap": (
                    _safe_float(fh.get("marketCapitalization")) * 1_000_000
                    if _safe_float(fh.get("marketCapitalization")) is not None
                    else None
                ),
                "beta": None, "currency": fh.get("currency"),
                "exchange": fh.get("exchange"), "source": "finnhub",
            }
            if not base:
                base = fh_profile
            else:
                base = _merge_normalized_profiles(base, fh_profile)

    if not base or not _profile_complete(base):
        av = await _av_overview(ticker)
        if _matches_ticker(av.get("Symbol"), ticker):
            av_profile = _av_profile(av, ticker)
            if not base:
                base = av_profile
            else:
                base = _merge_profile(base, av)

    return base or None


def _merge_normalized_profiles(
    primary: Dict[str, Any],
    fallback: Dict[str, Any],
) -> Dict[str, Any]:
    merged = dict(primary)
    for key, value in fallback.items():
        if key == "source":
            continue
        if merged.get(key) in (None, "") and value not in (None, ""):
            merged[key] = value
    sources = []
    for source in (primary.get("source"), fallback.get("source")):
        sources.extend(part for part in str(source or "").split("+") if part)
    merged["source"] = "+".join(dict.fromkeys(sources))
    return merged


# ---------------- Financials ----------------
_REVENUE_CONCEPTS = (
    "us-gaap_Revenues",
    "us-gaap_RevenueFromContractWithCustomerExcludingAssessedTax",
    "us-gaap_RevenueFromContractWithCustomerIncludingAssessedTax",
    "us-gaap_SalesRevenueNet",
)
_NET_INCOME_CONCEPTS = ("us-gaap_NetIncomeLoss",)
_GROSS_PROFIT_CONCEPTS = ("us-gaap_GrossProfit",)
_OPERATING_INCOME_CONCEPTS = (
    "us-gaap_OperatingIncomeLoss",
)
_TOTAL_ASSETS_CONCEPTS = ("us-gaap_Assets",)
_TOTAL_LIABILITIES_CONCEPTS = ("us-gaap_Liabilities",)
_EQUITY_CONCEPTS = ("us-gaap_StockholdersEquity",)
_OPER_CF_CONCEPTS = ("us-gaap_NetCashProvidedByUsedInOperatingActivities",)
_CAPEX_CONCEPTS = ("us-gaap_PaymentsToAcquirePropertyPlantAndEquipment",)


def _pick(concepts_block: List[Dict[str, Any]], targets: tuple) -> Optional[float]:
    if not concepts_block:
        return None
    for row in concepts_block:
        if row.get("concept") in targets:
            return row.get("value")
    return None


async def _fmp_financials(ticker: str) -> Dict[str, Any]:
    income = await _get(f"{FMP}/income-statement",
                        {"symbol": ticker, "limit": 4, "apikey": FMP_KEY})
    balance = await _get(f"{FMP}/balance-sheet-statement",
                         {"symbol": ticker, "limit": 4, "apikey": FMP_KEY})
    cashflow = await _get(f"{FMP}/cash-flow-statement",
                          {"symbol": ticker, "limit": 4, "apikey": FMP_KEY})

    def slim(rows, fields):
        return [{k: r.get(k) for k in fields} for r in (rows or [])[:4]]

    if not isinstance(income, list) or not income:
        return {}
    return {
        "income": slim(income, ["date", "revenue", "grossProfit", "operatingIncome",
                                "netIncome", "eps", "ebitda"]),
        "balance": slim(balance, ["date", "totalAssets", "totalLiabilities",
                                  "totalStockholdersEquity", "totalDebt",
                                  "cashAndCashEquivalents", "totalCurrentAssets",
                                  "totalCurrentLiabilities"]),
        "cashflow": slim(cashflow, ["date", "operatingCashFlow", "capitalExpenditure",
                                    "freeCashFlow", "netIncome"]),
        "source": "fmp",
    }


async def _finnhub_financials(ticker: str) -> Dict[str, Any]:
    fh = await _get(f"{FINNHUB_BASE}/stock/financials-reported",
                    {"symbol": ticker, "freq": "annual", "token": FINNHUB_KEY})
    if not isinstance(fh, dict) or not fh.get("data"):
        return {}
    income: List[Dict[str, Any]] = []
    balance: List[Dict[str, Any]] = []
    cashflow: List[Dict[str, Any]] = []
    for filing in (fh.get("data") or [])[:4]:
        report = filing.get("report") or {}
        date = (filing.get("endDate") or "")[:10]
        ic = report.get("ic") or []
        bs = report.get("bs") or []
        cf = report.get("cf") or []
        rev = _pick(ic, _REVENUE_CONCEPTS)
        ni = _pick(ic, _NET_INCOME_CONCEPTS)
        income.append({
            "date": date,
            "revenue": rev,
            "grossProfit": _pick(ic, _GROSS_PROFIT_CONCEPTS),
            "operatingIncome": _pick(ic, _OPERATING_INCOME_CONCEPTS),
            "netIncome": ni,
            "eps": None, "ebitda": None,
        })
        balance.append({
            "date": date,
            "totalAssets": _pick(bs, _TOTAL_ASSETS_CONCEPTS),
            "totalLiabilities": _pick(bs, _TOTAL_LIABILITIES_CONCEPTS),
            "totalStockholdersEquity": _pick(bs, _EQUITY_CONCEPTS),
            "totalDebt": None, "cashAndCashEquivalents": None,
            "totalCurrentAssets": None, "totalCurrentLiabilities": None,
        })
        op_cf = _pick(cf, _OPER_CF_CONCEPTS)
        capex = _pick(cf, _CAPEX_CONCEPTS)
        fcf = (op_cf - capex) if (op_cf is not None and capex is not None) else None
        cashflow.append({
            "date": date,
            "operatingCashFlow": op_cf,
            "capitalExpenditure": -capex if capex is not None else None,
            "freeCashFlow": fcf,
            "netIncome": ni,
        })
    return {"income": income, "balance": balance, "cashflow": cashflow, "source": "finnhub"}


async def get_financials(ticker: str) -> Dict[str, Any]:
    primary = await _fmp_financials(ticker)
    if primary:
        return primary
    return await _finnhub_financials(ticker)


# ---------------- Ratios / Valuation ----------------
async def _fmp_ratios(ticker: str) -> Dict[str, Any]:
    ratios = await _get(f"{FMP}/ratios-ttm", {"symbol": ticker, "apikey": FMP_KEY})
    metrics = await _get(f"{FMP}/key-metrics-ttm", {"symbol": ticker, "apikey": FMP_KEY})
    dcf = await _get(f"{FMP}/discounted-cash-flow", {"symbol": ticker, "apikey": FMP_KEY})

    r = (ratios or [{}])[0] if isinstance(ratios, list) else {}
    m = (metrics or [{}])[0] if isinstance(metrics, list) else {}
    d = (dcf or [{}])[0] if isinstance(dcf, list) else {}

    pe = r.get("priceToEarningsRatioTTM") or m.get("peRatioTTM")
    if pe is None:
        return {}
    return {
        "peTTM": pe,
        "pegTTM": r.get("priceToEarningsGrowthRatioTTM"),
        "pbTTM": r.get("priceToBookRatioTTM"),
        "psTTM": r.get("priceToSalesRatioTTM"),
        "evToEbitda": m.get("evToEBITDATTM"),
        "roeTTM": r.get("returnOnEquityTTM"),
        "roaTTM": r.get("returnOnAssetsTTM"),
        "debtToEquityTTM": r.get("debtToEquityRatioTTM"),
        "currentRatioTTM": r.get("currentRatioTTM") or m.get("currentRatioTTM"),
        "grossMarginTTM": r.get("grossProfitMarginTTM"),
        "operatingMarginTTM": r.get("operatingProfitMarginTTM"),
        "netMarginTTM": r.get("netProfitMarginTTM"),
        "dividendYieldTTM": r.get("dividendYieldTTM"),
        "dcfFairValue": d.get("dcf"),
        "currentPrice": d.get("Stock Price"),
        "source": "fmp",
    }


async def _finnhub_ratios(ticker: str) -> Dict[str, Any]:
    fh = await _get(f"{FINNHUB_BASE}/stock/metric",
                    {"symbol": ticker, "metric": "all", "token": FINNHUB_KEY})
    if not isinstance(fh, dict):
        return {}
    m = fh.get("metric") or {}

    def pct(v):
        return (v / 100.0) if v is not None else None

    return {
        "peTTM": m.get("peTTM") or m.get("peNormalizedAnnual"),
        "pegTTM": m.get("pegRatioTTM") or m.get("pegRatio5Y"),
        "pbTTM": m.get("pbAnnual") or m.get("pbQuarterly"),
        "psTTM": m.get("psTTM"),
        "evToEbitda": m.get("evEbitdaTTM") or m.get("currentEv/freeCashFlowTTM"),
        "roeTTM": pct(m.get("roeTTM") or m.get("roeRfy")),
        "roaTTM": pct(m.get("roaTTM") or m.get("roaRfy")),
        "debtToEquityTTM": m.get("totalDebt/totalEquityAnnual"),
        "currentRatioTTM": m.get("currentRatioAnnual") or m.get("currentRatioQuarterly"),
        "grossMarginTTM": pct(m.get("grossMarginTTM") or m.get("grossMarginAnnual")),
        "operatingMarginTTM": pct(m.get("operatingMarginTTM") or m.get("operatingMarginAnnual")),
        "netMarginTTM": pct(m.get("netProfitMarginTTM") or m.get("netProfitMarginAnnual")),
        "dividendYieldTTM": pct(m.get("currentDividendYieldTTM")),
        "dcfFairValue": None,
        "currentPrice": None,
        "source": "finnhub",
    }


async def get_ratios(ticker: str) -> Dict[str, Any]:
    primary = await _fmp_ratios(ticker)
    if primary:
        return primary
    return await _finnhub_ratios(ticker)


# ---------------- Peers ----------------
async def get_peers(ticker: str) -> List[Dict[str, Any]]:
    data = await _get(f"{FMP}/stock-peers", {"symbol": ticker, "apikey": FMP_KEY})
    if isinstance(data, list) and data:
        return [
            {"ticker": p.get("symbol"), "name": p.get("companyName"),
             "price": p.get("price"), "marketCap": p.get("mktCap")}
            for p in data[:6]
        ]
    fh = await _get(f"{FINNHUB_BASE}/stock/peers",
                    {"symbol": ticker, "token": FINNHUB_KEY})
    if isinstance(fh, list) and fh:
        return [{"ticker": p, "name": p, "price": None, "marketCap": None}
                for p in fh if p and p != ticker][:6]
    return []


# ---------------- Analyst ratings ----------------
async def get_analyst(ticker: str) -> Optional[Dict[str, Any]]:
    out: Dict[str, Any] = {}

    pt = await _get(f"{FMP}/price-target-consensus",
                    {"symbol": ticker, "apikey": FMP_KEY})
    if isinstance(pt, list) and pt:
        p = pt[0]
        out.update({
            "targetHigh": p.get("targetHigh"),
            "targetLow": p.get("targetLow"),
            "targetConsensus": p.get("targetConsensus"),
            "targetMedian": p.get("targetMedian"),
        })

    rec = await _get(f"{FMP}/grades-consensus",
                     {"symbol": ticker, "apikey": FMP_KEY})
    if isinstance(rec, list) and rec:
        r0 = rec[0]
        out.update({k: r0.get(k) for k in
                    ("strongBuy", "buy", "hold", "sell", "strongSell", "consensus")})
    else:
        fh = await _get(f"{FINNHUB_BASE}/stock/recommendation",
                        {"symbol": ticker, "token": FINNHUB_KEY})
        if isinstance(fh, list) and fh:
            r0 = fh[0]
            out.update({k: r0.get(k) for k in
                        ("strongBuy", "buy", "hold", "sell", "strongSell")})

    return out or None


# ---------------- News ----------------
async def get_news(ticker: str, name: Optional[str] = None) -> List[Dict[str, Any]]:
    q = name or ticker
    g = await _get(f"{GNEWS_BASE}/search",
                   {"q": q, "lang": "en", "max": 10, "token": GNEWS_KEY})
    items: List[Dict[str, Any]] = []
    if isinstance(g, dict) and g.get("articles"):
        for n in g["articles"][:10]:
            items.append({
                "title": n.get("title"),
                "url": n.get("url"),
                "site": (n.get("source") or {}).get("name"),
                "publishedAt": n.get("publishedAt"),
                "image": n.get("image"),
                "snippet": n.get("description") or "",
                "source": "gnews",
            })
        return items
    today = time.strftime("%Y-%m-%d", time.gmtime())
    month_ago = time.strftime("%Y-%m-%d", time.gmtime(time.time() - 30 * 24 * 60 * 60))
    fh = await _get(f"{FINNHUB_BASE}/company-news", {
        "symbol": ticker, "from": month_ago, "to": today,
        "token": FINNHUB_KEY,
    })
    if isinstance(fh, list):
        for n in fh[:10]:
            items.append({
                "title": n.get("headline"), "url": n.get("url"),
                "site": n.get("source"), "publishedAt": n.get("datetime"),
                "image": n.get("image"), "snippet": n.get("summary") or "",
                "source": "finnhub",
            })
    return items


# ---------------- Historical price ----------------
async def _fmp_history(ticker: str) -> List[Dict[str, Any]]:
    data = await _get(f"{FMP}/historical-price-eod/light",
                      {"symbol": ticker, "apikey": FMP_KEY})
    if isinstance(data, list) and data:
        rows = list(reversed(data[:180]))
        return [{"date": r.get("date"), "close": r.get("price")} for r in rows]
    return []


async def _yahoo_history(ticker: str) -> List[Dict[str, Any]]:
    headers = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"}
    data = await _get(f"{YAHOO_BASE}/{ticker}",
                      {"interval": "1d", "range": "6mo"}, headers=headers)
    try:
        result = ((data or {}).get("chart") or {}).get("result") or []
        if not result:
            return []
        r0 = result[0]
        ts = r0.get("timestamp") or []
        closes = (((r0.get("indicators") or {}).get("quote") or [{}])[0]).get("close") or []
        out: List[Dict[str, Any]] = []
        for t, c in zip(ts, closes):
            if c is None:
                continue
            out.append({
                "date": time.strftime("%Y-%m-%d", time.gmtime(t)),
                "close": float(c),
            })
        return out[-180:]
    except Exception as exc:
        logger.warning(f"yahoo parse failed for {ticker}: {exc}")
        return []


async def get_history(ticker: str) -> List[Dict[str, Any]]:
    points = await _fmp_history(ticker)
    if points:
        return points
    return await _yahoo_history(ticker)
