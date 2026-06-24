"""
Multi-agent AI orchestration for AlphaLens.
Implements 6 worker agents + 1 moderator, equivalent to LangGraph supervisor-worker.
Uses Claude Sonnet 4.5 via the Emergent universal key.
"""
import os
import json
import logging
import asyncio
import re
from typing import Any, Dict, List, Optional
from emergentintegrations.llm.chat import LlmChat, UserMessage

logger = logging.getLogger(__name__)

EMERGENT_KEY = os.environ.get("EMERGENT_LLM_KEY", "")
MODEL_PROVIDER = "anthropic"
MODEL_NAME = "claude-sonnet-4-5-20250929"


def _extract_json(text: str) -> Dict[str, Any]:
    """Best-effort JSON extraction from an LLM response."""
    if not text:
        return {}
    # Strip code fences
    text = text.strip()
    m = re.search(r"```(?:json)?\s*(\{.*?\}|\[.*?\])\s*```", text, re.DOTALL)
    if m:
        text = m.group(1)
    # Find first { ... } block
    start = text.find("{")
    if start == -1:
        return {}
    depth = 0
    end = -1
    for i in range(start, len(text)):
        c = text[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    if end == -1:
        return {}
    try:
        return json.loads(text[start:end])
    except Exception as e:
        logger.warning(f"JSON extract failed: {e}")
        return {}


async def _ask(system: str, user: str, session_id: str) -> str:
    chat = LlmChat(
        api_key=EMERGENT_KEY,
        session_id=session_id,
        system_message=system,
    ).with_model(MODEL_PROVIDER, MODEL_NAME)
    msg = UserMessage(text=user)
    try:
        resp = await chat.send_message(msg)
        return resp if isinstance(resp, str) else str(resp)
    except Exception as e:
        logger.error(f"LLM call failed ({session_id}): {e}")
        return ""


# ---------- AGENTS ----------

async def research_agent(state: Dict[str, Any]) -> Dict[str, Any]:
    profile = state.get("profile") or {}
    peers = state.get("peers") or []
    peer_str = ", ".join([p.get("ticker", "") if isinstance(p, dict) else str(p) for p in peers]) or "n/a"
    system = (
        "You are a senior equity research analyst. Analyze the company's business model, "
        "competitive moat, market position, and growth drivers. Respond ONLY with valid JSON."
    )
    user = f"""Company: {profile.get('name')} ({state.get('ticker')})
Sector: {profile.get('sector')} | Industry: {profile.get('industry')}
Description: {profile.get('description','')[:1500]}
Peers: {peer_str}

Return JSON with keys:
{{
  "business_summary": "2-3 sentence overview of what the company does",
  "moat": "competitive advantage (1-2 sentences)",
  "moat_strength": "Wide|Narrow|None",
  "revenue_streams": ["..."],
  "growth_drivers": ["..."],
  "market_position": "Leader|Challenger|Niche|Laggard",
  "key_risks": ["..."]
}}"""
    raw = await _ask(system, user, f"research-{state.get('ticker')}")
    return _extract_json(raw)


async def financial_agent(state: Dict[str, Any]) -> Dict[str, Any]:
    fin = state.get("financials") or {}
    ratios = state.get("ratios") or {}
    system = (
        "You are a CFA-level financial analyst. Analyze fundamentals quantitatively. "
        "Respond ONLY with valid JSON."
    )
    user = f"""Ticker: {state.get('ticker')}
Income (latest 4y): {json.dumps(fin.get('income', []))[:2000]}
Balance: {json.dumps(fin.get('balance', []))[:1500]}
Cashflow: {json.dumps(fin.get('cashflow', []))[:1500]}
Ratios TTM: {json.dumps(ratios)[:1500]}

Return JSON:
{{
  "revenue_growth_yoy_pct": <number>,
  "net_income_growth_yoy_pct": <number>,
  "gross_margin_pct": <number>,
  "operating_margin_pct": <number>,
  "net_margin_pct": <number>,
  "fcf_latest": <number>,
  "roe_pct": <number>,
  "debt_to_equity": <number>,
  "current_ratio": <number>,
  "financial_health": "Strong|Moderate|Weak",
  "key_observations": ["3-5 short observations"]
}}"""
    raw = await _ask(system, user, f"fin-{state.get('ticker')}")
    return _extract_json(raw)


async def valuation_agent(state: Dict[str, Any]) -> Dict[str, Any]:
    ratios = state.get("ratios") or {}
    quote = state.get("quote") or {}
    system = (
        "You are a valuation expert. Compute fair value using multiple methods. "
        "Respond ONLY with valid JSON."
    )
    user = f"""Ticker: {state.get('ticker')}
Current price: {quote.get('price')}
PE TTM: {ratios.get('peTTM')} | PEG: {ratios.get('pegTTM')} | P/B: {ratios.get('pbTTM')}
EV/EBITDA: {ratios.get('evToEbitda')} | DCF (FMP): {ratios.get('dcfFairValue')}
ROE: {ratios.get('roeTTM')} | Net margin: {ratios.get('netMarginTTM')}

Return JSON:
{{
  "dcf_fair_value": <number>,
  "pe_based_fair_value": <number>,
  "ev_ebitda_based_fair_value": <number>,
  "fair_value_low": <number>,
  "fair_value_mid": <number>,
  "fair_value_high": <number>,
  "upside_pct": <number>,
  "valuation_verdict": "Undervalued|Fairly Valued|Overvalued",
  "reasoning": "1-2 sentences"
}}"""
    raw = await _ask(system, user, f"val-{state.get('ticker')}")
    return _extract_json(raw)


async def bull_agent(state: Dict[str, Any]) -> Dict[str, Any]:
    system = (
        "You are a bullish investor building the strongest possible case for buying this stock. "
        "Respond ONLY with valid JSON."
    )
    user = f"""Ticker: {state.get('ticker')}
Research: {json.dumps(state.get('research', {}))[:1200]}
Financial: {json.dumps(state.get('financial', {}))[:1200]}
Valuation: {json.dumps(state.get('valuation', {}))[:1200]}

Return JSON:
{{
  "thesis_points": ["4-6 strong, quantified bullish arguments"],
  "catalysts": ["2-4 near-term catalysts"],
  "target_upside_pct": <number>
}}"""
    raw = await _ask(system, user, f"bull-{state.get('ticker')}")
    return _extract_json(raw)


async def bear_agent(state: Dict[str, Any]) -> Dict[str, Any]:
    system = (
        "You are a bearish short-seller building the strongest possible case against this stock. "
        "Respond ONLY with valid JSON."
    )
    user = f"""Ticker: {state.get('ticker')}
Research: {json.dumps(state.get('research', {}))[:1200]}
Financial: {json.dumps(state.get('financial', {}))[:1200]}
Valuation: {json.dumps(state.get('valuation', {}))[:1200]}

Return JSON:
{{
  "thesis_points": ["4-6 strong, quantified bearish arguments"],
  "risks": ["2-4 specific risks"],
  "target_downside_pct": <number>
}}"""
    raw = await _ask(system, user, f"bear-{state.get('ticker')}")
    return _extract_json(raw)


async def macro_agent(state: Dict[str, Any]) -> Dict[str, Any]:
    profile = state.get("profile") or {}
    system = (
        "You are a macroeconomic analyst. Assess the macro and sector backdrop for this stock. "
        "Respond ONLY with valid JSON."
    )
    user = f"""Ticker: {state.get('ticker')}
Sector: {profile.get('sector')} | Industry: {profile.get('industry')} | Country: {profile.get('country')}

Return JSON:
{{
  "rate_sensitivity": "High|Medium|Low",
  "inflation_impact": "Positive|Neutral|Negative",
  "sector_cycle_phase": "Early|Mid|Late|Recession",
  "fx_exposure": "High|Medium|Low",
  "macro_tailwinds": ["..."],
  "macro_headwinds": ["..."],
  "overall_macro_score": <number 0-100>
}}"""
    raw = await _ask(system, user, f"macro-{state.get('ticker')}")
    return _extract_json(raw)


async def moderator_agent(state: Dict[str, Any]) -> Dict[str, Any]:
    system = (
        "You are the chief investment officer. Synthesize all analyst inputs into a final "
        "INVEST / HOLD / PASS recommendation with confidence (0-100). Respond ONLY with valid JSON."
    )
    user = f"""Ticker: {state.get('ticker')} - {state.get('profile', {}).get('name')}
Current price: {state.get('quote', {}).get('price')}

Research summary: {json.dumps(state.get('research', {}))[:1000]}
Financial analysis: {json.dumps(state.get('financial', {}))[:1000]}
Valuation: {json.dumps(state.get('valuation', {}))[:1000]}
Bull case: {json.dumps(state.get('bull', {}))[:800]}
Bear case: {json.dumps(state.get('bear', {}))[:800]}
Macro: {json.dumps(state.get('macro', {}))[:800]}

Return JSON:
{{
  "recommendation": "INVEST|HOLD|PASS",
  "confidence_score": <0-100>,
  "expected_upside_pct": <number>,
  "expected_downside_pct": <number>,
  "time_horizon": "Short-term|6-12 months|1-3 years|3+ years",
  "executive_summary": "3-4 sentence final synthesis",
  "key_reasons": ["3-5 bullet reasons for the recommendation"],
  "what_would_change_view": ["2-3 conditions that would flip our view"]
}}"""
    raw = await _ask(system, user, f"mod-{state.get('ticker')}")
    return _extract_json(raw)


# ---------- ORCHESTRATOR ----------

AGENT_STEPS = [
    ("research", "Research Agent — business & moat analysis"),
    ("financial", "Financial Agent — fundamentals deep-dive"),
    ("valuation", "Valuation Agent — fair value modeling"),
    ("macro", "Macro Agent — sector & economic context"),
    ("bull", "Bull Agent — building the case to buy"),
    ("bear", "Bear Agent — building the case to avoid"),
    ("moderator", "Moderator — final synthesis & verdict"),
]


async def run_pipeline_streaming(state: Dict[str, Any], emit):
    """
    Run the multi-agent pipeline. `emit` is an async callable that yields SSE events.
    Phase 1: Research, Financial, Valuation, Macro in parallel.
    Phase 2: Bull and Bear in parallel (need phase 1 output).
    Phase 3: Moderator.
    """
    # Phase 1 — parallel
    await emit("agent_start", {"agent": "research", "label": "Research Agent — business & moat analysis"})
    await emit("agent_start", {"agent": "financial", "label": "Financial Agent — fundamentals deep-dive"})
    await emit("agent_start", {"agent": "valuation", "label": "Valuation Agent — fair value modeling"})
    await emit("agent_start", {"agent": "macro", "label": "Macro Agent — sector & economic context"})

    r, f, v, m = await asyncio.gather(
        research_agent(state),
        financial_agent(state),
        valuation_agent(state),
        macro_agent(state),
        return_exceptions=False,
    )
    state["research"] = r
    state["financial"] = f
    state["valuation"] = v
    state["macro"] = m
    await emit("agent_done", {"agent": "research", "data": r})
    await emit("agent_done", {"agent": "financial", "data": f})
    await emit("agent_done", {"agent": "valuation", "data": v})
    await emit("agent_done", {"agent": "macro", "data": m})

    # Phase 2 — parallel bull/bear
    await emit("agent_start", {"agent": "bull", "label": "Bull Agent — building the case to buy"})
    await emit("agent_start", {"agent": "bear", "label": "Bear Agent — building the case to avoid"})
    bull, bear = await asyncio.gather(bull_agent(state), bear_agent(state))
    state["bull"] = bull
    state["bear"] = bear
    await emit("agent_done", {"agent": "bull", "data": bull})
    await emit("agent_done", {"agent": "bear", "data": bear})

    # Phase 3 — moderator
    await emit("agent_start", {"agent": "moderator", "label": "Moderator — final synthesis & verdict"})
    mod = await moderator_agent(state)
    state["moderator"] = mod
    await emit("agent_done", {"agent": "moderator", "data": mod})

    return state
