"""
Data Provider Chain for AlphaLens.
Multi-provider fetching with failover.
Primary: FMP (stable). Fallbacks: Finnhub, Alpha Vantage. News: GNews.
"""
import os
import logging
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

TIMEOUT = httpx.Timeout(15.0, connect=8.0)


async def _get(url: str, params: Dict[str, Any] | None = None) -> Optional[Any]:
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            r = await client.get(url, params=params)
            if r.status_code == 200:
                return r.json()
            logger.warning(f"GET {url} -> {r.status_code}: {r.text[:160]}")
    except Exception as e:
        logger.warning(f"GET {url} failed: {e}")
    return None


# ---- Search ----
async def search_ticker(query: str) -> List[Dict[str, Any]]:
    q = (query or "").strip()
    out: List[Dict[str, Any]] = []

    # If query looks like a ticker (<=5 alphanum), first try to fetch its profile
    if 1 <= len(q) <= 5 and q.replace(".", "").replace("-", "").isalnum():
        prof = await get_profile(q.upper())
        if prof and prof.get("ticker"):
            out.append({
                "ticker": prof["ticker"],
                "name": prof.get("name") or prof["ticker"],
                "exchange": prof.get("exchange"),
                "currency": prof.get("currency") or "USD",
            })

    data = await _get(f"{FMP}/search-name", {"query": q, "limit": 10, "apikey": FMP_KEY})
    if data and isinstance(data, list):
        for d in data:
            sym = d.get("symbol")
            if not sym or any(o["ticker"] == sym for o in out):
                continue
            out.append({
                "ticker": sym,
                "name": d.get("name"),
                "exchange": d.get("exchange") or d.get("exchangeFullName"),
                "currency": d.get("currency"),
            })
    if out:
        return out[:8]
    fh = await _get(f"{FINNHUB_BASE}/search", {"q": q, "token": FINNHUB_KEY})
    if fh and isinstance(fh, dict) and fh.get("result"):
        return [
            {"ticker": r.get("symbol"), "name": r.get("description"),
             "exchange": "", "currency": "USD"}
            for r in fh["result"][:8] if r.get("symbol")
        ]
    return []


# ---- Quote ----
async def get_quote(ticker: str) -> Optional[Dict[str, Any]]:
    data = await _get(f"{FMP}/quote", {"symbol": ticker, "apikey": FMP_KEY})
    if data and isinstance(data, list) and data:
        q = data[0]
        return {
            "ticker": q.get("symbol"),
            "name": q.get("name"),
            "price": q.get("price"),
            "change": q.get("change"),
            "changesPercentage": q.get("changePercentage"),
            "dayLow": q.get("dayLow"),
            "dayHigh": q.get("dayHigh"),
            "yearLow": q.get("yearLow"),
            "yearHigh": q.get("yearHigh"),
            "marketCap": q.get("marketCap"),
            "volume": q.get("volume"),
            "avgVolume": q.get("priceAvg50"),
            "exchange": q.get("exchange"),
            "open": q.get("open"),
            "previousClose": q.get("previousClose"),
            "source": "fmp",
        }
    fh = await _get(f"{FINNHUB_BASE}/quote", {"symbol": ticker, "token": FINNHUB_KEY})
    if fh and isinstance(fh, dict) and fh.get("c"):
        return {
            "ticker": ticker, "name": ticker, "price": fh.get("c"),
            "change": fh.get("d"), "changesPercentage": fh.get("dp"),
            "dayLow": fh.get("l"), "dayHigh": fh.get("h"),
            "yearLow": None, "yearHigh": None, "marketCap": None,
            "volume": None, "avgVolume": None, "exchange": "",
            "open": fh.get("o"), "previousClose": fh.get("pc"),
            "source": "finnhub",
        }
    return None


# ---- Profile ----
async def get_profile(ticker: str) -> Optional[Dict[str, Any]]:
    data = await _get(f"{FMP}/profile", {"symbol": ticker, "apikey": FMP_KEY})
    if data and isinstance(data, list) and data:
        p = data[0]
        return {
            "ticker": p.get("symbol"),
            "name": p.get("companyName"),
            "sector": p.get("sector"),
            "industry": p.get("industry"),
            "ceo": p.get("ceo"),
            "country": p.get("country"),
            "website": p.get("website"),
            "description": p.get("description"),
            "employees": p.get("fullTimeEmployees"),
            "ipoDate": p.get("ipoDate"),
            "image": p.get("image"),
            "marketCap": p.get("marketCap"),
            "beta": p.get("beta"),
            "currency": p.get("currency"),
            "exchange": p.get("exchange"),
            "source": "fmp",
        }
    fh = await _get(f"{FINNHUB_BASE}/stock/profile2", {"symbol": ticker, "token": FINNHUB_KEY})
    if fh and isinstance(fh, dict) and fh.get("name"):
        return {
            "ticker": ticker, "name": fh.get("name"),
            "sector": fh.get("finnhubIndustry"),
            "industry": fh.get("finnhubIndustry"),
            "ceo": "", "country": fh.get("country"),
            "website": fh.get("weburl"), "description": "",
            "employees": None, "ipoDate": fh.get("ipo"),
            "image": fh.get("logo"),
            "marketCap": fh.get("marketCapitalization"),
            "beta": None, "currency": fh.get("currency"),
            "exchange": fh.get("exchange"), "source": "finnhub",
        }
    return None


# ---- Financials ----
async def get_financials(ticker: str) -> Dict[str, Any]:
    income = await _get(f"{FMP}/income-statement", {"symbol": ticker, "limit": 4, "apikey": FMP_KEY})
    balance = await _get(f"{FMP}/balance-sheet-statement", {"symbol": ticker, "limit": 4, "apikey": FMP_KEY})
    cashflow = await _get(f"{FMP}/cash-flow-statement", {"symbol": ticker, "limit": 4, "apikey": FMP_KEY})

    def slim(rows, fields):
        out = []
        for r in (rows or [])[:4]:
            out.append({k: r.get(k) for k in fields})
        return out

    return {
        "income": slim(income, ["date", "revenue", "grossProfit", "operatingIncome",
                                "netIncome", "eps", "ebitda"]),
        "balance": slim(balance, ["date", "totalAssets", "totalLiabilities",
                                  "totalStockholdersEquity", "totalDebt",
                                  "cashAndCashEquivalents", "totalCurrentAssets",
                                  "totalCurrentLiabilities"]),
        "cashflow": slim(cashflow, ["date", "operatingCashFlow", "capitalExpenditure",
                                    "freeCashFlow", "netIncome"]),
    }


# ---- Ratios / Valuation ----
async def get_ratios(ticker: str) -> Dict[str, Any]:
    ratios = await _get(f"{FMP}/ratios-ttm", {"symbol": ticker, "apikey": FMP_KEY})
    metrics = await _get(f"{FMP}/key-metrics-ttm", {"symbol": ticker, "apikey": FMP_KEY})
    dcf = await _get(f"{FMP}/discounted-cash-flow", {"symbol": ticker, "apikey": FMP_KEY})

    r = (ratios or [{}])[0] if isinstance(ratios, list) else {}
    m = (metrics or [{}])[0] if isinstance(metrics, list) else {}
    d = (dcf or [{}])[0] if isinstance(dcf, list) else {}

    return {
        "peTTM": r.get("priceToEarningsRatioTTM") or m.get("peRatioTTM"),
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
    }


# ---- Peers ----
async def get_peers(ticker: str) -> List[Dict[str, Any]]:
    data = await _get(f"{FMP}/stock-peers", {"symbol": ticker, "apikey": FMP_KEY})
    out: List[Dict[str, Any]] = []
    if data and isinstance(data, list):
        for p in data[:6]:
            out.append({
                "ticker": p.get("symbol"),
                "name": p.get("companyName"),
                "price": p.get("price"),
                "marketCap": p.get("mktCap"),
            })
    return out


# ---- Analyst ratings ----
async def get_analyst(ticker: str) -> Optional[Dict[str, Any]]:
    pt = await _get(f"{FMP}/price-target-consensus", {"symbol": ticker, "apikey": FMP_KEY})
    rec = await _get(f"{FMP}/grades-consensus", {"symbol": ticker, "apikey": FMP_KEY})
    out: Dict[str, Any] = {}
    if pt and isinstance(pt, list) and pt:
        p = pt[0]
        out.update({
            "targetHigh": p.get("targetHigh"),
            "targetLow": p.get("targetLow"),
            "targetConsensus": p.get("targetConsensus"),
            "targetMedian": p.get("targetMedian"),
        })
    if rec and isinstance(rec, list) and rec:
        r0 = rec[0]
        out.update({
            "strongBuy": r0.get("strongBuy"),
            "buy": r0.get("buy"),
            "hold": r0.get("hold"),
            "sell": r0.get("sell"),
            "strongSell": r0.get("strongSell"),
            "consensus": r0.get("consensus"),
        })
    return out or None


# ---- News ----
async def get_news(ticker: str, name: str | None = None) -> List[Dict[str, Any]]:
    q = name or ticker
    g = await _get(f"{GNEWS_BASE}/search",
                   {"q": q, "lang": "en", "max": 10, "token": GNEWS_KEY})
    items: List[Dict[str, Any]] = []
    if g and isinstance(g, dict) and g.get("articles"):
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
    fh = await _get(f"{FINNHUB_BASE}/company-news", {
        "symbol": ticker, "from": "2024-01-01", "to": "2030-12-31", "token": FINNHUB_KEY
    })
    if fh and isinstance(fh, list):
        for n in fh[:10]:
            items.append({
                "title": n.get("headline"),
                "url": n.get("url"),
                "site": n.get("source"),
                "publishedAt": n.get("datetime"),
                "image": n.get("image"),
                "snippet": n.get("summary") or "",
                "source": "finnhub",
            })
    return items


# ---- Historical price for chart ----
async def get_history(ticker: str) -> List[Dict[str, Any]]:
    data = await _get(f"{FMP}/historical-price-eod/light",
                      {"symbol": ticker, "apikey": FMP_KEY})
    if data and isinstance(data, list):
        # FMP returns newest first; flip to oldest first; cap at 180 points
        rows = list(reversed(data[:180]))
        return [{"date": r.get("date"), "close": r.get("price")} for r in rows]
    return []
