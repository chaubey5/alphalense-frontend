"""
Multi-agent AI orchestration for AlphaLens.
Converted to Groq (OpenAI-compatible API).
"""
import os
import json
import logging
import asyncio
import math
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Dict
from openai import AsyncOpenAI

from providers import redact_sensitive_text

logger = logging.getLogger(__name__)

# ---------------------------
# GROQ CONFIG
# ---------------------------
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
GROQ_MAX_RETRIES = 2
GROQ_MAX_COMPLETION_TOKENS = 1400
_GROQ_REQUEST_SEMAPHORE = asyncio.Semaphore(1)
_client: AsyncOpenAI | None = None


def _llm_client() -> AsyncOpenAI:
    global _client
    if not GROQ_API_KEY:
        raise RuntimeError("AI provider is not configured. Set GROQ_API_KEY.")
    if _client is None:
        _client = AsyncOpenAI(
            api_key=GROQ_API_KEY,
            base_url="https://api.groq.com/openai/v1",
            timeout=45.0,
            max_retries=0,
        )
    return _client


def _groq_retry_delay(error: Exception, attempt: int) -> float:
    response = getattr(error, "response", None)
    headers = getattr(response, "headers", {}) or {}
    retry_after_ms = headers.get("retry-after-ms")
    if retry_after_ms:
        try:
            return max(float(retry_after_ms) / 1000, 0)
        except (TypeError, ValueError):
            pass

    retry_after = headers.get("Retry-After")
    if retry_after:
        try:
            return max(float(retry_after), 0)
        except (TypeError, ValueError):
            try:
                retry_at = parsedate_to_datetime(retry_after)
                if retry_at.tzinfo is None:
                    retry_at = retry_at.replace(tzinfo=timezone.utc)
                return max((retry_at - datetime.now(timezone.utc)).total_seconds(), 0)
            except (TypeError, ValueError, OverflowError):
                pass
    return min(2 ** attempt, 8)


# ---------------------------
# JSON EXTRACTION
# ---------------------------
def _extract_json(text: str) -> Dict[str, Any]:
    if not text:
        return {}

    text = text.strip()

    m = re.search(r"```(?:json)?\s*(\{.*?\}|\[.*?\])\s*```", text, re.DOTALL)
    if m:
        text = m.group(1)

    start = text.find("{")
    if start == -1:
        return {}

    depth = 0
    end = -1

    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break

    if end == -1:
        return {}

    try:
        parsed = json.loads(text[start:end])
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError as e:
        logger.warning("Agent JSON parse failed: %s", e)
        return {}


# ---------------------------
# LLM CALL (GROQ)
# ---------------------------
async def _ask(system: str, user: str, session_id: str) -> str:
    if not GROQ_API_KEY:
        raise RuntimeError("AI provider is not configured. Set GROQ_API_KEY.")
    async with _GROQ_REQUEST_SEMAPHORE:
        for attempt in range(GROQ_MAX_RETRIES + 1):
            try:
                response = await _llm_client().chat.completions.create(
                    model=GROQ_MODEL,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user}
                    ],
                    temperature=0.7,
                    max_tokens=GROQ_MAX_COMPLETION_TOKENS,
                )
                break
            except Exception as e:
                status = getattr(e, "status_code", None)
                if status == 429 and attempt < GROQ_MAX_RETRIES:
                    delay = _groq_retry_delay(e, attempt)
                    logger.warning(
                        "Groq rate limited session=%s attempt=%d/%d retry_in=%.2fs",
                        session_id, attempt + 1, GROQ_MAX_RETRIES + 1, delay,
                    )
                    await asyncio.sleep(delay)
                    continue

                response = getattr(e, "response", None)
                body = getattr(response, "text", "") if response is not None else ""
                safe_body = redact_sensitive_text(
                    body,
                    headers={"Authorization": GROQ_API_KEY},
                ) if body else ""
                category = (
                    "rate_limit" if status == 429
                    else "timeout" if "timeout" in type(e).__name__.lower()
                    else "request_error"
                )
                logger.error(
                    "Groq %s session=%s status=%s error_type=%s body=%s",
                    category, session_id, status or "unavailable", type(e).__name__,
                    safe_body or "unavailable",
                )
                raise RuntimeError(
                    "The AI provider could not complete the research request."
                ) from e

    content = response.choices[0].message.content if response.choices else None
    if not content or not content.strip():
        raise RuntimeError("The AI provider returned an empty response.")
    return content


def _parse_agent(raw: str, agent: str) -> Dict[str, Any]:
    result = _extract_json(raw)
    if not result:
        raise RuntimeError(f"The {agent} agent returned invalid structured output.")
    return result


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _text_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _financial_metrics(state: Dict[str, Any]) -> Dict[str, Any]:
    financials = state.get("financials") or {}
    income = financials.get("income") or []
    balance = financials.get("balance") or []
    cashflow = financials.get("cashflow") or []
    latest = income[0] if income else {}
    previous = income[1] if len(income) > 1 else {}
    latest_balance = balance[0] if balance else {}
    latest_cashflow = cashflow[0] if cashflow else {}

    def growth(current: Any, prior: Any) -> float | None:
        current_value = _number(current)
        prior_value = _number(prior)
        if current_value is None or prior_value in (None, 0):
            return None
        return (current_value / prior_value - 1) * 100

    def margin(numerator: Any, denominator: Any) -> float | None:
        numerator_value = _number(numerator)
        denominator_value = _number(denominator)
        if numerator_value is None or denominator_value in (None, 0):
            return None
        return numerator_value / denominator_value * 100

    def ratio(numerator: Any, denominator: Any) -> float | None:
        numerator_value = _number(numerator)
        denominator_value = _number(denominator)
        if numerator_value is None or denominator_value in (None, 0):
            return None
        return numerator_value / denominator_value

    return {
        "revenue_growth_yoy_pct": growth(latest.get("revenue"), previous.get("revenue")),
        "net_income_growth_yoy_pct": growth(latest.get("netIncome"), previous.get("netIncome")),
        "gross_margin_pct": margin(latest.get("grossProfit"), latest.get("revenue")),
        "operating_margin_pct": margin(latest.get("operatingIncome"), latest.get("revenue")),
        "net_margin_pct": margin(latest.get("netIncome"), latest.get("revenue")),
        "fcf_latest": _number(latest_cashflow.get("freeCashFlow")),
        "roe_pct": margin(latest.get("netIncome"), latest_balance.get("totalStockholdersEquity")),
        "debt_to_equity": ratio(
            latest_balance.get("totalDebt"),
            latest_balance.get("totalStockholdersEquity"),
        ),
        "current_ratio": ratio(
            latest_balance.get("totalCurrentAssets"),
            latest_balance.get("totalCurrentLiabilities"),
        ),
    }


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def _has_recommendation_evidence(state: Dict[str, Any]) -> bool:
    ticker = str(state.get("ticker") or "").strip().upper()
    profile = state.get("profile") or {}
    quote = state.get("quote") or {}
    price = _number(quote.get("price"))
    if (
        not ticker
        or profile.get("ticker") != ticker
        or not profile.get("name")
        or quote.get("ticker") != ticker
        or price is None
        or price <= 0
    ):
        return False

    financials = state.get("financials") or {}
    financial_values = []
    for section in ("income", "balance", "cashflow"):
        rows = financials.get(section) or []
        if rows and isinstance(rows[0], dict):
            financial_values.extend(
                _number(value)
                for key, value in rows[0].items()
                if key != "date" and _number(value) is not None
            )
    ratios = state.get("ratios") or {}
    ratio_values = [
        _number(value)
        for key, value in ratios.items()
        if key != "source" and _number(value) is not None
    ]
    return len(financial_values) >= 2 or len(ratio_values) >= 2


def _memory_context(state: Dict[str, Any]) -> Dict[str, Any]:
    memory = state.get("memory_context") or {}
    if not memory.get("available"):
        return {"available": False}

    session = memory.get("session")
    session_summary = None
    if isinstance(session, dict):
        session_summary = {
            "report_id": session.get("report_id"),
            "updated_at": session.get("updated_at"),
            "recommendation": session.get("recommendation"),
            "confidence_score": session.get("confidence_score"),
            "executive_summary": session.get("executive_summary"),
            "key_reasons": session.get("key_reasons") or [],
            "risks": session.get("risks") or [],
            "data_sources": session.get("data_sources") or [],
        }

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
        for record in (memory.get("prior_research") or [])
        if isinstance(record, dict)
    ]
    return {
        "available": True,
        "session": session_summary,
        "prior_research": prior_research,
    }


# ---------------------------
# AGENTS
# ---------------------------

print("Research Agent Started")

async def research_agent(state: Dict[str, Any]) -> Dict[str, Any]:
    profile = state.get("profile") or {}
    peers = state.get("peers") or []

    peer_str = ", ".join(
        [p.get("ticker", "") if isinstance(p, dict) else str(p) for p in peers]
    ) or "n/a"

    system = (
        "You are a senior equity research analyst. Use only facts supported by "
        "the supplied company profile. Do not invent company details; mark "
        "unsupported items as null or empty arrays. Respond ONLY with valid JSON."
    )

    user = f"""
Company: {profile.get('name')} ({state.get('ticker')})
Sector: {profile.get('sector')} | Industry: {profile.get('industry')}
Description: {profile.get('description','')[:1500]}
Peers: {peer_str}

Return JSON:
{{
  "business_summary": "",
  "moat": "",
  "moat_strength": "",
  "revenue_streams": [],
  "growth_drivers": [],
  "market_position": "",
  "key_risks": []
}}
"""

    raw = await _ask(system, user, f"research-{state.get('ticker')}")
    result = _parse_agent(raw, "research")
    for key in ("business_summary", "moat", "moat_strength", "market_position"):
        result[key] = _text(result.get(key))
    for key in ("revenue_streams", "growth_drivers", "key_risks"):
        result[key] = _text_list(result.get(key))
    return result


print("Financial Agent Started")

async def financial_agent(state: Dict[str, Any]) -> Dict[str, Any]:
    fin = state.get("financials") or {}
    ratios = state.get("ratios") or {}

    def compact_rows(rows, fields):
        return [
            {field: row.get(field) for field in fields if field in row}
            for row in (rows or [])[:2]
            if isinstance(row, dict)
        ]

    income = compact_rows(
        fin.get("income"),
        ("date", "revenue", "grossProfit", "operatingIncome", "netIncome", "eps", "ebitda"),
    )
    balance = compact_rows(
        fin.get("balance"),
        (
            "date", "totalAssets", "totalLiabilities", "totalStockholdersEquity",
            "totalDebt", "cashAndCashEquivalents", "totalCurrentAssets",
            "totalCurrentLiabilities",
        ),
    )
    cashflow = compact_rows(
        fin.get("cashflow"),
        ("date", "operatingCashFlow", "capitalExpenditure", "freeCashFlow", "netIncome"),
    )
    ratio_fields = (
        "peTTM", "pegTTM", "pbTTM", "psTTM", "evToEbitda", "roeTTM",
        "roaTTM", "debtToEquityTTM", "currentRatioTTM", "grossMarginTTM",
        "operatingMarginTTM", "netMarginTTM", "dividendYieldTTM",
        "dcfFairValue", "currentPrice",
    )
    relevant_ratios = {
        key: ratios[key] for key in ratio_fields if key in ratios
    }

    system = (
        "You are a financial analyst. Use only the supplied financial statements "
        "and ratios. Do not estimate or infer missing financial values. Return "
        "null for unavailable numeric fields and empty arrays for unsupported "
        "observations. Respond ONLY with valid JSON."
    )

    user = f"""
Ticker: {state.get('ticker')}
Income: {json.dumps(income, separators=(",", ":"))}
Balance: {json.dumps(balance, separators=(",", ":"))}
Cashflow: {json.dumps(cashflow, separators=(",", ":"))}
Ratios: {json.dumps(relevant_ratios, separators=(",", ":"))}

Return JSON:
{{
  "revenue_growth_yoy_pct": null,
  "net_income_growth_yoy_pct": null,
  "gross_margin_pct": null,
  "operating_margin_pct": null,
  "net_margin_pct": null,
  "fcf_latest": null,
  "roe_pct": null,
  "debt_to_equity": null,
  "current_ratio": null,
  "financial_health": "",
  "key_observations": []
}}
"""

    raw = await _ask(system, user, f"fin-{state.get('ticker')}")
    result = _parse_agent(raw, "financial")
    result["financial_health"] = _text(result.get("financial_health"))
    result["key_observations"] = _text_list(result.get("key_observations"))
    result.update(_financial_metrics(state))
    return result


async def valuation_agent(state: Dict[str, Any]) -> Dict[str, Any]:
    ratios = state.get("ratios") or {}
    quote = state.get("quote") or {}

    system = (
        "You are a valuation analyst. Do not invent fair values, price targets, "
        "or unsupported financial assumptions. Return null for values that "
        "cannot be calculated from the supplied data. Respond ONLY with valid JSON."
    )

    user = f"""
Ticker: {state.get('ticker')}
Price: {quote.get('price')}
PE: {ratios.get('peTTM')}
PEG: {ratios.get('pegTTM')}
PB: {ratios.get('pbTTM')}
EV/EBITDA: {ratios.get('evToEbitda')}

Return JSON:
{{
  "dcf_fair_value": null,
  "pe_based_fair_value": null,
  "ev_ebitda_based_fair_value": null,
  "fair_value_low": null,
  "fair_value_mid": null,
  "fair_value_high": null,
  "upside_pct": null,
  "valuation_verdict": "",
  "reasoning": ""
}}
"""

    raw = await _ask(system, user, f"val-{state.get('ticker')}")
    result = _parse_agent(raw, "valuation")
    result["valuation_verdict"] = _text(result.get("valuation_verdict"))
    result["reasoning"] = _text(result.get("reasoning"))
    fair_value = _number(ratios.get("dcfFairValue"))
    price = _number(quote.get("price"))
    result.update({
        "dcf_fair_value": fair_value,
        "pe_based_fair_value": None,
        "ev_ebitda_based_fair_value": None,
        "fair_value_low": None,
        "fair_value_mid": None,
        "fair_value_high": None,
        "upside_pct": (
            (fair_value / price - 1) * 100
            if fair_value is not None and price not in (None, 0)
            else None
        ),
    })
    return result


async def bull_agent(state: Dict[str, Any]) -> Dict[str, Any]:
    system = (
        "You are a bullish investor. Support each point with supplied evidence. "
        "Do not invent numeric return targets. Respond ONLY with valid JSON."
    )

    user = f"""
Research: {json.dumps(state.get('research', {}))[:1200]}
Financial: {json.dumps(state.get('financial', {}))[:1200]}
Valuation: {json.dumps(state.get('valuation', {}))[:1200]}

Return JSON:
{{
  "thesis_points": [],
  "catalysts": [],
  "target_upside_pct": null
}}
"""

    raw = await _ask(system, user, f"bull-{state.get('ticker')}")
    result = _parse_agent(raw, "bull")
    result["thesis_points"] = _text_list(result.get("thesis_points"))
    result["catalysts"] = _text_list(result.get("catalysts"))
    result["target_upside_pct"] = None
    return result


async def bear_agent(state: Dict[str, Any]) -> Dict[str, Any]:
    system = (
        "You are a bearish investor. Support each point with supplied evidence. "
        "Do not invent numeric return targets. Respond ONLY with valid JSON."
    )

    user = f"""
Research: {json.dumps(state.get('research', {}))[:1200]}
Financial: {json.dumps(state.get('financial', {}))[:1200]}
Valuation: {json.dumps(state.get('valuation', {}))[:1200]}

Return JSON:
{{
  "thesis_points": [],
  "risks": [],
  "target_downside_pct": null
}}
"""

    raw = await _ask(system, user, f"bear-{state.get('ticker')}")
    result = _parse_agent(raw, "bear")
    result["thesis_points"] = _text_list(result.get("thesis_points"))
    result["risks"] = _text_list(result.get("risks"))
    result["target_downside_pct"] = None
    return result


async def macro_agent(state: Dict[str, Any]) -> Dict[str, Any]:
    profile = state.get("profile") or {}

    system = (
        "You are a macroeconomic analyst. Only describe general sector exposure "
        "from the supplied profile. No current macroeconomic indicators or data "
        "were supplied, so do not claim current rates, inflation, or market "
        "conditions. Respond ONLY with valid JSON."
    )

    user = f"""
Sector: {profile.get('sector')}
Industry: {profile.get('industry')}

Return JSON where ALL values must be plain strings or numbers (no nested objects):
{{
  "rate_sensitivity": "short plain text",
  "inflation_impact": "short plain text",
  "sector_cycle_phase": "short plain text",
  "fx_exposure": "short plain text",
  "macro_tailwinds": ["plain string 1", "plain string 2"],
  "macro_headwinds": ["plain string 1", "plain string 2"],
  "overall_macro_score": 0
}}
"""

    raw = await _ask(system, user, f"macro-{state.get('ticker')}")
    result = _parse_agent(raw, "macro")

    # Normalize: if LLM returned objects instead of strings, extract a usable string
    for key in ["rate_sensitivity", "inflation_impact", "sector_cycle_phase", "fx_exposure"]:
        val = result.get(key)
        if isinstance(val, dict):
            result[key] = val.get("impact") or val.get("factor") or str(val)
        elif not isinstance(val, str):
            result[key] = str(val) if val is not None else "—"

    for key in ["macro_tailwinds", "macro_headwinds"]:
        val = result.get(key)
        if isinstance(val, list):
            result[key] = [
                (item.get("impact") or item.get("factor") or str(item)) if isinstance(item, dict) else str(item)
                for item in val
            ]
        else:
            result[key] = []

    result["data_limitations"] = [
        "No current macroeconomic indicators were retrieved for this report."
    ]
    return result


async def moderator_agent(state: Dict[str, Any]) -> Dict[str, Any]:
    if not _has_recommendation_evidence(state):
        raise RuntimeError(
            "Insufficient verified stock and financial data for an investment recommendation."
        )

    memory = _memory_context(state)
    system = (
        "You are a CIO. Make a cautious INVEST/HOLD/PASS decision using only "
        "the supplied agent evidence. Do not invent financial metrics, target "
        "prices, upside, or downside. Do not produce a confident recommendation "
        "if the evidence is insufficient. Historical memory is contextual only; "
        "use it only to detect prior rationale or risks, never as fresh financial "
        "data or to replace current retrieved evidence. Return JSON only."
    )

    user = f"""
Ticker: {state.get('ticker')}
Price: {state.get('quote', {}).get('price')}

Research: {json.dumps(state.get('research', {}))[:1000]}
Financial: {json.dumps(state.get('financial', {}))[:1000]}
Valuation: {json.dumps(state.get('valuation', {}))[:1000]}
Bull: {json.dumps(state.get('bull', {}))[:800]}
Bear: {json.dumps(state.get('bear', {}))[:800]}
Macro: {json.dumps(state.get('macro', {}))[:800]}
Historical agent memory (not current market data):
{json.dumps(memory, default=str)[:1600]}

Return JSON:
{{
  "recommendation": "",
  "confidence_score": 0,
  "expected_upside_pct": null,
  "expected_downside_pct": null,
  "time_horizon": "",
  "executive_summary": "",
  "key_reasons": [],
  "what_would_change_view": [],
  "risks": [],
  "financial_metrics": {{}},
  "data_sources": []
}}
"""

    raw = await _ask(system, user, f"mod-{state.get('ticker')}")
    result = _parse_agent(raw, "moderator")
    recommendation = str(result.get("recommendation") or "").upper()
    if recommendation not in {"INVEST", "HOLD", "PASS"}:
        raise RuntimeError("The moderator returned an unsupported recommendation.")

    confidence = _number(result.get("confidence_score"))
    if confidence is None or not 0 <= confidence <= 100:
        raise RuntimeError("The moderator returned an invalid confidence score.")

    quote = state.get("quote") or {}
    ratios = state.get("ratios") or {}
    price = _number(quote.get("price"))
    dcf_value = _number(ratios.get("dcfFairValue"))
    source_values = [
        (state.get("profile") or {}).get("source"),
        quote.get("source"),
        ratios.get("source"),
        (state.get("financials") or {}).get("source"),
    ]
    for item in state.get("news") or []:
        source_values.append(item.get("source") if isinstance(item, dict) else None)

    risks = []
    for agent_key, field in (("bear", "risks"), ("research", "key_risks")):
        agent_result = state.get(agent_key) or {}
        values = agent_result.get(field) or []
        if isinstance(values, list):
            risks.extend(str(value) for value in values if value)

    result.update({
        "recommendation": recommendation,
        "confidence_score": confidence,
        "expected_upside_pct": (
            (dcf_value / price - 1) * 100
            if dcf_value is not None and price not in (None, 0)
            else None
        ),
        "expected_downside_pct": None,
        "risks": _unique(risks),
        "executive_summary": _text(result.get("executive_summary")),
        "time_horizon": _text(result.get("time_horizon")),
        "key_reasons": _text_list(result.get("key_reasons")),
        "what_would_change_view": _text_list(result.get("what_would_change_view")),
        "financial_metrics": {
            key: value for key, value in ratios.items()
            if key != "source" and _number(value) is not None
        },
        "data_sources": _unique([
            str(source) for source in source_values if source
        ]),
    })
    return result


# ---------------------------
# PIPELINE
# ---------------------------
print("Pipeline Started")
async def run_pipeline_streaming(state: Dict[str, Any], emit):
    failures = []

    async def execute(name, agent):
        await emit("agent_start", {"agent": name})
        try:
            result = await agent(state)
        except Exception as exc:
            failures.append(name)
            logger.warning(
                "Research agent failed agent=%s error_type=%s",
                name, type(exc).__name__,
            )
            await emit("agent_error", {
                "agent": name,
                "message": f"The {name} agent could not complete.",
            })
            return
        state[name] = result
        await emit("agent_done", {"agent": name, "data": result})

    for name, agent in (
        ("research", research_agent),
        ("financial", financial_agent),
        ("valuation", valuation_agent),
        ("macro", macro_agent),
    ):
        await execute(name, agent)

    if failures:
        raise RuntimeError(
            "Research pipeline incomplete; required agents failed: "
            + ", ".join(failures)
        )

    await execute("bull", bull_agent)
    await execute("bear", bear_agent)
    if failures:
        raise RuntimeError(
            "Research pipeline incomplete; required agents failed: "
            + ", ".join(failures)
        )

    await execute("moderator", moderator_agent)
    if failures:
        raise RuntimeError(
            "Research pipeline incomplete; moderator could not produce a report."
        )

    return state
