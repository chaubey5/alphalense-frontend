import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

import httpx
import pytest
from bson import ObjectId
from pymongo.errors import OperationFailure, PyMongoError

import agents
import providers
import server


def test_identical_provider_requests_share_one_in_flight_call(monkeypatch):
    calls = 0

    async def fake_request(url, params, headers):
        nonlocal calls
        calls += 1
        await asyncio.sleep(0)
        return {"value": 1}

    monkeypatch.setattr(providers, "_request_json", fake_request)
    providers._CACHE.clear()
    providers._IN_FLIGHT.clear()

    async def run():
        return await asyncio.gather(
            providers._get("https://provider.test/quote", {"symbol": "AAPL"}),
            providers._get("https://provider.test/quote", {"symbol": "AAPL"}),
        )

    try:
        results = asyncio.run(run())
        assert results == [{"value": 1}, {"value": 1}]
        assert calls == 1
    finally:
        providers._CACHE.clear()
        providers._IN_FLIGHT.clear()


def test_provider_request_retries_rate_limit(monkeypatch):
    request = httpx.Request("GET", "https://provider.test/quote")

    class FakeClient:
        def __init__(self):
            self.responses = [
                httpx.Response(429, headers={"Retry-After": "0"}, request=request),
                httpx.Response(200, json={"price": 42}, request=request),
            ]

        async def get(self, *args, **kwargs):
            return self.responses.pop(0)

    sleeps = []

    async def fake_sleep(delay):
        sleeps.append(delay)

    fake_client = FakeClient()
    monkeypatch.setattr(providers, "_http_client", lambda: fake_client)
    monkeypatch.setattr(providers.asyncio, "sleep", fake_sleep)
    result = asyncio.run(providers._request_json("https://provider.test/quote"))

    assert result == {"price": 42}
    assert sleeps == [0.0]


def test_provider_http_failures_record_status_and_redact_secrets(caplog, monkeypatch):
    request = httpx.Request("GET", "https://provider.test/quote")

    class FakeClient:
        async def get(self, *args, **kwargs):
            return httpx.Response(
                403,
                json={
                    "message": "Access denied for key secret-value",
                    "apiKey": "secret-value",
                },
                request=request,
            )

    monkeypatch.setattr(providers, "_http_client", lambda: FakeClient())
    providers.REQUEST_DIAGNOSTICS.clear()

    result = asyncio.run(providers._request_json(
        "https://provider.test/quote",
        params={"apikey": "secret-value"},
    ))

    assert result is None
    assert "status=403" in caplog.text
    assert "Access denied" in caplog.text
    assert "secret-value" not in caplog.text
    diagnostic = providers.REQUEST_DIAGNOSTICS["provider.test/quote"]
    assert diagnostic["status_code"] == 403
    assert diagnostic["outcome"] == "http_error"


@pytest.mark.parametrize("status", [401, 403, 404, 429, 500, 503])
def test_provider_status_failures_are_reported_and_bounded(status, caplog, monkeypatch):
    request = httpx.Request("GET", "https://provider.test/quote")
    calls = 0

    class FakeClient:
        async def get(self, *args, **kwargs):
            nonlocal calls
            calls += 1
            return httpx.Response(status, json={"message": "provider failure"}, request=request)

    async def no_wait(_):
        return None

    monkeypatch.setattr(providers, "_http_client", lambda: FakeClient())
    monkeypatch.setattr(providers.asyncio, "sleep", no_wait)
    providers.REQUEST_DIAGNOSTICS.clear()

    assert asyncio.run(providers._request_json("https://provider.test/quote")) is None

    assert f"status={status}" in caplog.text
    expected_calls = providers.MAX_RETRIES + 1 if status == 429 or status >= 500 else 1
    assert calls == expected_calls
    assert providers.REQUEST_DIAGNOSTICS["provider.test/quote"]["status_code"] == status


def test_provider_api_level_error_is_not_treated_as_success(caplog, monkeypatch):
    request = httpx.Request("GET", "https://www.alphavantage.co/query")

    class FakeClient:
        async def get(self, *args, **kwargs):
            return httpx.Response(
                200,
                json={"Note": "API call frequency limit reached; token=secret-value"},
                request=request,
            )

    monkeypatch.setattr(providers, "_http_client", lambda: FakeClient())
    providers.REQUEST_DIAGNOSTICS.clear()

    result = asyncio.run(providers._request_json(
        "https://www.alphavantage.co/query",
        params={"apikey": "secret-value"},
    ))

    assert result is None
    assert "status=200" in caplog.text
    assert "API call frequency limit" in caplog.text
    assert "secret-value" not in caplog.text
    assert providers.REQUEST_DIAGNOSTICS["www.alphavantage.co/query"]["outcome"] == "api_error"


def test_provider_timeout_is_captured_without_exception_details(monkeypatch):
    request = httpx.Request("GET", "https://provider.test/quote")
    sleeps = []

    class FakeClient:
        async def get(self, *args, **kwargs):
            raise httpx.ReadTimeout("secret-value", request=request)

    async def fake_sleep(delay):
        sleeps.append(delay)

    monkeypatch.setattr(providers, "_http_client", lambda: FakeClient())
    monkeypatch.setattr(providers.asyncio, "sleep", fake_sleep)
    providers.REQUEST_DIAGNOSTICS.clear()

    result = asyncio.run(providers._request_json(
        "https://provider.test/quote",
        params={"token": "secret-value"},
    ))

    assert result is None
    assert len(sleeps) == providers.MAX_RETRIES
    assert providers.REQUEST_DIAGNOSTICS["provider.test/quote"]["outcome"] == "timeout"
    assert providers.REQUEST_DIAGNOSTICS["provider.test/quote"]["error_type"] == "ReadTimeout"


def test_alphavantage_profile_falls_back_when_other_profiles_missing(monkeypatch):
    monkeypatch.setattr(providers, "FMP_KEY", "configured-test-key")
    monkeypatch.setattr(providers, "FINNHUB_KEY", "configured-test-key")
    monkeypatch.setattr(providers, "AV_KEY", "configured-test-key")

    async def fake_get(url, params=None, **kwargs):
        if "financialmodelingprep.com" in url or "finnhub.io" in url:
            return None
        return {
            "Symbol": "AAPL",
            "Name": "Apple Inc.",
            "Sector": "Technology",
            "Description": "Company description",
            "Beta": "1.2",
            "FullTimeEmployees": "1000",
        }

    monkeypatch.setattr(providers, "_get", fake_get)

    result = asyncio.run(providers.get_profile("AAPL"))

    assert result["name"] == "Apple Inc."
    assert result["source"] == "alphavantage"
    assert result["beta"] == 1.2


def test_alphavantage_global_quote_fallback_when_other_quotes_missing(monkeypatch):
    monkeypatch.setattr(providers, "FMP_KEY", "configured-test-key")
    monkeypatch.setattr(providers, "FINNHUB_KEY", "configured-test-key")
    monkeypatch.setattr(providers, "AV_KEY", "configured-test-key")

    async def fake_get(url, params=None, **kwargs):
        if "financialmodelingprep.com" in url or "finnhub.io" in url:
            return None
        return {
            "Global Quote": {
                "01. symbol": "AAPL",
                "02. open": "190.00",
                "03. high": "195.00",
                "04. low": "189.00",
                "05. price": "192.50",
                "06. volume": "1000",
                "08. previous close": "191.00",
                "09. change": "1.50",
                "10. change percent": "0.78%",
            }
        }

    monkeypatch.setattr(providers, "_get", fake_get)

    result = asyncio.run(providers.get_quote("AAPL"))

    assert result["ticker"] == "AAPL"
    assert result["price"] == 192.5
    assert result["changesPercentage"] == 0.78
    assert result["source"] == "alphavantage"


@pytest.mark.parametrize(
    "ticker",
    [
        "AAPL", "NVDA", "TSLA", "MSFT", "AMZN", "GOOGL", "META",
        "NFLX", "AMD", "INTC", "ORCL", "JPM", "WMT", "BRK.B", "BF-B",
    ],
)
def test_fmp_quotes_normalize_all_valid_supported_symbols(monkeypatch, ticker):
    async def fake_get(url, params=None, **kwargs):
        assert params["symbol"] == ticker
        return [{"symbol": ticker, "price": "123.45", "name": "Company"}]

    monkeypatch.setattr(providers, "_get", fake_get)

    result = asyncio.run(providers.get_quote(f" {ticker.lower()} "))

    assert result["ticker"] == ticker
    assert result["price"] == 123.45


def test_invalid_ticker_is_rejected_by_provider_normalizer():
    with pytest.raises(ValueError, match="Invalid ticker"):
        providers.normalize_ticker("AAPL..BAD")


def test_finnhub_quote_is_used_when_fmp_returns_invalid_symbol(monkeypatch):
    calls = []

    async def fake_get(url, params=None, **kwargs):
        calls.append(url)
        if "financialmodelingprep.com" in url:
            return [{"symbol": "MSFT", "price": 100}]
        if "finnhub.io" in url and url.endswith("/quote"):
            return {"c": 50, "d": 1, "dp": 2}
        if "finnhub.io" in url:
            return {}
        raise AssertionError("AV should not be requested after valid Finnhub quote")

    monkeypatch.setattr(providers, "_get", fake_get)

    result = asyncio.run(providers.get_quote("NVDA"))

    assert result["ticker"] == "NVDA"
    assert result["price"] == 50
    assert result["source"] == "finnhub"
    assert len(calls) == 3


def test_finnhub_quote_is_used_when_fmp_returns_incomplete_data(monkeypatch):
    async def fake_get(url, params=None, **kwargs):
        if "financialmodelingprep.com" in url:
            return [{"symbol": "NVDA", "price": None}]
        if "finnhub.io" in url and url.endswith("/quote"):
            return {"c": 900}
        return {}

    monkeypatch.setattr(providers, "_get", fake_get)

    result = asyncio.run(providers.get_quote("NVDA"))

    assert result["price"] == 900
    assert result["source"] == "finnhub"


def test_all_quote_providers_unavailable_returns_no_fabricated_quote(monkeypatch):
    calls = []

    async def no_data(*args, **kwargs):
        calls.append(args[0])
        return None

    monkeypatch.setattr(providers, "_get", no_data)

    assert asyncio.run(providers.get_quote("NVDA")) is None
    assert any("financialmodelingprep.com" in url for url in calls)
    assert any("finnhub.io" in url for url in calls)
    assert any("alphavantage.co" in url for url in calls)


def test_all_profile_providers_unavailable_returns_none_and_tries_each(monkeypatch):
    calls = []

    async def no_data(url, params=None, **kwargs):
        calls.append(url)
        return None

    monkeypatch.setattr(providers, "_get", no_data)

    assert asyncio.run(providers.get_profile("NVDA")) is None
    assert any("financialmodelingprep.com" in url for url in calls)
    assert any("finnhub.io" in url for url in calls)
    assert any("alphavantage.co" in url for url in calls)


def test_incomplete_fmp_profile_merges_finnhub_and_alphavantage(monkeypatch):
    async def fake_get(url, params=None, **kwargs):
        if "financialmodelingprep.com" in url:
            return [{
                "symbol": "NVDA", "companyName": "NVIDIA Corporation",
                "sector": "Technology", "description": "",
            }]
        if "finnhub.io" in url:
            return {
                "name": "NVIDIA Corporation", "weburl": "https://example.test",
                "finnhubIndustry": "Semiconductors",
            }
        return {
            "Symbol": "NVDA", "Name": "NVIDIA Corporation",
            "Description": "Provider description", "Beta": "1.5",
            "FullTimeEmployees": "100",
        }

    monkeypatch.setattr(providers, "_get", fake_get)

    result = asyncio.run(providers.get_profile("nvda"))

    assert result["ticker"] == "NVDA"
    assert result["description"] == "Provider description"
    assert result["website"] == "https://example.test"
    assert result["source"] == "fmp+finnhub+alphavantage"


def test_wrong_ticker_profile_is_rejected_and_fallback_continues(monkeypatch):
    async def fake_get(url, params=None, **kwargs):
        if "financialmodelingprep.com" in url:
            return [{"symbol": "AAPL", "companyName": "Wrong Company"}]
        if "finnhub.io" in url:
            return {"name": "NVIDIA Corporation", "finnhubIndustry": "Technology"}
        return {}

    monkeypatch.setattr(providers, "_get", fake_get)

    result = asyncio.run(providers.get_profile("NVDA"))

    assert result["ticker"] == "NVDA"
    assert result["name"] == "NVIDIA Corporation"
    assert result["source"] == "finnhub"


def test_missing_provider_key_skips_network(monkeypatch):
    async def unexpected_request(*args, **kwargs):
        raise AssertionError("request must not be sent without a key")

    monkeypatch.setattr(providers, "_request_json", unexpected_request)
    assert asyncio.run(
        providers._get("https://provider.test/quote", {"token": ""})
    ) is None


def test_missing_financials_remain_unavailable(monkeypatch):
    async def fake_ask(*args, **kwargs):
        return '{"financial_health":"Insufficient data","key_observations":[]}'

    monkeypatch.setattr(agents, "_ask", fake_ask)
    result = asyncio.run(agents.financial_agent({
        "ticker": "AAPL",
        "financials": {"income": [], "balance": [], "cashflow": []},
    }))

    assert result["revenue_growth_yoy_pct"] is None
    assert result["fcf_latest"] is None
    assert result["roe_pct"] is None


def test_financial_agent_prompt_keeps_recent_statement_values(monkeypatch):
    received = {}

    async def fake_ask(system, user, session_id):
        received["user"] = user
        return '{"financial_health":"healthy","key_observations":[]}'

    monkeypatch.setattr(agents, "_ask", fake_ask)
    asyncio.run(agents.financial_agent({
        "ticker": "AAPL",
        "financials": {
            "income": [
                {"date": "2025", "revenue": 12345, "netIncome": 2345},
                {"date": "2024", "revenue": 11000, "netIncome": 2100},
            ],
            "balance": [{"date": "2025", "totalDebt": 500}],
            "cashflow": [{"date": "2025", "freeCashFlow": 900}],
        },
        "ratios": {"peTTM": 25, "dcfFairValue": 150, "source": "fmp"},
    }))

    assert '"revenue":12345' in received["user"]
    assert '"revenue":11000' in received["user"]
    assert '"totalDebt":500' in received["user"]
    assert '"freeCashFlow":900' in received["user"]
    assert '"dcfFairValue":150' in received["user"]
    assert '"source": "fmp"' not in received["user"]


def test_missing_groq_key_is_reported_explicitly(monkeypatch):
    monkeypatch.setattr(agents, "GROQ_API_KEY", "")
    with pytest.raises(RuntimeError, match="GROQ_API_KEY"):
        asyncio.run(agents._ask("system", "question", "test"))


def test_groq_http_error_logs_status_without_exposing_key(caplog, monkeypatch):
    secret = "groq-test-secret"
    request = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")
    response = httpx.Response(
        401,
        text=f"Invalid API key: {secret}",
        request=request,
    )

    class FakeAPIError(Exception):
        status_code = 401

        def __init__(self):
            self.response = response

    class FakeCompletions:
        async def create(self, **kwargs):
            raise FakeAPIError()

    client = SimpleNamespace(
        chat=SimpleNamespace(completions=FakeCompletions())
    )
    monkeypatch.setattr(agents, "GROQ_API_KEY", secret)
    monkeypatch.setattr(agents, "_llm_client", lambda: client)

    with pytest.raises(RuntimeError, match="AI provider"):
        asyncio.run(agents._ask("system", "question", "test"))

    assert "status=401" in caplog.text
    assert "Invalid API key" in caplog.text
    assert secret not in caplog.text


def test_groq_rate_limit_retries_using_retry_after(monkeypatch, caplog):
    request = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")
    class FakeRateLimitError(Exception):
        status_code = 429
        response = httpx.Response(
            429,
            headers={"Retry-After": "2"},
            request=request,
        )
    calls = 0
    sleeps = []

    class FakeCompletions:
        async def create(self, **kwargs):
            nonlocal calls
            calls += 1
            assert kwargs["max_tokens"] == agents.GROQ_MAX_COMPLETION_TOKENS
            if calls == 1:
                raise FakeRateLimitError()
            return SimpleNamespace(
                choices=[SimpleNamespace(
                    message=SimpleNamespace(content='{"ok":true}')
                )]
            )

    async def fake_sleep(delay):
        sleeps.append(delay)

    monkeypatch.setattr(agents, "GROQ_API_KEY", "test-key")
    monkeypatch.setattr(agents, "_llm_client", lambda: SimpleNamespace(
        chat=SimpleNamespace(completions=FakeCompletions())
    ))
    monkeypatch.setattr(agents.asyncio, "sleep", fake_sleep)

    result = asyncio.run(agents._ask("system", "question", "test"))

    assert result == '{"ok":true}'
    assert calls == 2
    assert sleeps == [2.0]
    assert "Groq rate limited" in caplog.text


def test_groq_requests_are_serialized(monkeypatch):
    active = 0
    max_active = 0

    class FakeCompletions:
        async def create(self, **kwargs):
            nonlocal active, max_active
            active += 1
            max_active = max(max_active, active)
            await asyncio.sleep(0)
            active -= 1
            return SimpleNamespace(
                choices=[SimpleNamespace(
                    message=SimpleNamespace(content='{"ok":true}')
                )]
            )

    monkeypatch.setattr(agents, "GROQ_API_KEY", "test-key")
    monkeypatch.setattr(agents, "_llm_client", lambda: SimpleNamespace(
        chat=SimpleNamespace(completions=FakeCompletions())
    ))

    async def run():
        return await asyncio.gather(*[
            agents._ask("system", "question", f"test-{index}")
            for index in range(3)
        ])

    assert asyncio.run(run()) == ['{"ok":true}'] * 3
    assert max_active == 1


def test_moderator_uses_retrieved_metrics_and_supported_recommendation(monkeypatch):
    async def fake_ask(*args, **kwargs):
        return (
            '{"recommendation":"invest","confidence_score":72,'
            '"expected_upside_pct":999,"expected_downside_pct":88,'
            '"financial_metrics":{"peTTM":999},"risks":[]}'
        )

    monkeypatch.setattr(agents, "_ask", fake_ask)
    state = {
        "ticker": "AAPL",
        "quote": {"ticker": "AAPL", "price": 100, "source": "finnhub"},
        "profile": {"ticker": "AAPL", "name": "Apple Inc.", "source": "fmp"},
        "financials": {"source": "fmp"},
        "ratios": {"dcfFairValue": 120, "peTTM": 22, "source": "fmp"},
        "bear": {"risks": ["Provider-supported risk"]},
    }

    result = asyncio.run(agents.moderator_agent(state))

    assert result["recommendation"] == "INVEST"
    assert result["expected_upside_pct"] == pytest.approx(20)
    assert result["expected_downside_pct"] is None
    assert result["financial_metrics"] == {"dcfFairValue": 120, "peTTM": 22}
    assert result["risks"] == ["Provider-supported risk"]
    assert set(result["data_sources"]) == {"fmp", "finnhub"}


def test_moderator_refuses_recommendation_without_sufficient_financial_data(monkeypatch):
    async def unexpected_ask(*args, **kwargs):
        raise AssertionError("moderator must not run on insufficient evidence")

    monkeypatch.setattr(agents, "_ask", unexpected_ask)

    with pytest.raises(RuntimeError, match="Insufficient verified stock and financial data"):
        asyncio.run(agents.moderator_agent({
            "ticker": "NVDA",
            "profile": {"ticker": "NVDA", "name": "NVIDIA"},
            "quote": {"ticker": "NVDA", "price": 100},
            "financials": {},
            "ratios": {},
        }))


def test_moderator_receives_memory_as_historical_context(monkeypatch):
    received = {}

    async def fake_ask(system, user, session_id):
        received["system"] = system
        received["user"] = user
        return (
            '{"recommendation":"HOLD","confidence_score":55,'
            '"executive_summary":"Current evidence remains mixed.",'
            '"key_reasons":[],"what_would_change_view":[],"risks":[]}'
        )

    monkeypatch.setattr(agents, "_ask", fake_ask)
    state = {
        "ticker": "AAPL",
        "profile": {"ticker": "AAPL", "name": "Apple Inc."},
        "quote": {"ticker": "AAPL", "price": 100},
        "financials": {
            "income": [{"revenue": 100, "netIncome": 20}],
            "balance": [],
            "cashflow": [],
        },
        "ratios": {"peTTM": 20, "pbTTM": 5},
        "memory_context": {
            "available": True,
            "session": {"report_id": "old-session", "recommendation": "INVEST"},
            "prior_research": [
                {"report_id": "older", "recommendation": "PASS"},
            ],
        },
    }

    result = asyncio.run(agents.moderator_agent(state))

    assert result["recommendation"] == "HOLD"
    assert "Historical agent memory" in received["user"]
    assert "Historical memory" in received["system"]


def test_pipeline_passes_specialist_results_to_debate_and_moderator(monkeypatch):
    async def specialist(name, state):
        return {name: "available"}

    async def bull(state):
        assert all(name in state for name in ("research", "financial", "valuation", "macro"))
        return {"thesis_points": ["supported"]}

    async def bear(state):
        assert all(name in state for name in ("research", "financial", "valuation", "macro"))
        return {"risks": ["supported"]}

    async def moderator(state):
        assert "bull" in state and "bear" in state
        return {"recommendation": "HOLD", "confidence_score": 50}

    monkeypatch.setattr(agents, "research_agent", lambda state: specialist("research", state))
    monkeypatch.setattr(agents, "financial_agent", lambda state: specialist("financial", state))
    monkeypatch.setattr(agents, "valuation_agent", lambda state: specialist("valuation", state))
    monkeypatch.setattr(agents, "macro_agent", lambda state: specialist("macro", state))
    monkeypatch.setattr(agents, "bull_agent", bull)
    monkeypatch.setattr(agents, "bear_agent", bear)
    monkeypatch.setattr(agents, "moderator_agent", moderator)
    events = []

    async def emit(event, payload):
        events.append((event, payload))

    result = asyncio.run(agents.run_pipeline_streaming({"ticker": "AAPL"}, emit))

    assert set(("research", "financial", "valuation", "macro", "bull", "bear", "moderator")) <= set(result)
    completed = {payload["agent"] for event, payload in events if event == "agent_done"}
    assert completed == {"research", "financial", "valuation", "macro", "bull", "bear", "moderator"}


def test_pipeline_does_not_fabricate_failed_agent_or_run_moderator(monkeypatch):
    async def successful(name, state):
        return {name: "available"}

    async def failed_financial(state):
        raise RuntimeError("provider output unavailable")

    async def unexpected_moderator(state):
        raise AssertionError("moderator must not run with a missing specialist")

    monkeypatch.setattr(agents, "research_agent", lambda state: successful("research", state))
    monkeypatch.setattr(agents, "financial_agent", failed_financial)
    monkeypatch.setattr(agents, "valuation_agent", lambda state: successful("valuation", state))
    monkeypatch.setattr(agents, "macro_agent", lambda state: successful("macro", state))
    monkeypatch.setattr(agents, "moderator_agent", unexpected_moderator)
    events = []

    async def emit(event, payload):
        events.append((event, payload))

    state = {"ticker": "AAPL"}
    with pytest.raises(RuntimeError, match="financial"):
        asyncio.run(agents.run_pipeline_streaming(state, emit))

    assert "financial" not in state
    assert not any(
        event == "agent_done" and payload["agent"] == "financial"
        for event, payload in events
    )
    assert any(
        event == "agent_error" and payload["agent"] == "financial"
        for event, payload in events
    )
    assert not any(payload.get("agent") == "moderator" for _, payload in events)


async def _get_app(path):
    transport = httpx.ASGITransport(app=server.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.get(path)


def test_market_data_routes_return_provider_shapes(monkeypatch):
    async def fake_search(query):
        return [{"ticker": "AAPL", "name": "Apple"}]

    async def fake_quote(ticker):
        return {"ticker": ticker, "price": 100, "source": "test"}

    async def fake_profile(ticker):
        return {"ticker": ticker, "name": "Example Co", "ceo": "Unavailable"}

    async def fake_news(ticker):
        return [{"title": "Company update", "source": "test"}]

    async def fake_history(ticker):
        return [{"date": "2026-01-01", "close": 100}]

    monkeypatch.setattr(server, "search_ticker", fake_search)
    monkeypatch.setattr(server, "get_quote", fake_quote)
    monkeypatch.setattr(server, "get_profile", fake_profile)
    monkeypatch.setattr(server, "get_news", fake_news)
    monkeypatch.setattr(server, "get_history", fake_history)

    async def requests():
        return [
            await _get_app("/api/search?q=Apple"),
            await _get_app("/api/quote/AAPL"),
            await _get_app("/api/profile/AAPL"),
            await _get_app("/api/news/AAPL"),
            await _get_app("/api/history/AAPL"),
        ]

    responses = asyncio.run(requests())

    assert all(response.status_code == 200 for response in responses)
    assert responses[0].json()["results"][0]["ticker"] == "AAPL"
    assert responses[1].json()["source"] == "test"
    assert responses[2].json()["name"] == "Example Co"
    assert responses[3].json()["items"][0]["title"] == "Company update"
    assert responses[4].json()["points"][0]["close"] == 100


def test_cors_allows_verified_vercel_origin_without_wildcard():
    async def preflight(origin):
        transport = httpx.ASGITransport(app=server.app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://test",
        ) as client:
            return await client.options(
                "/api/health",
                headers={
                    "Origin": origin,
                    "Access-Control-Request-Method": "GET",
                },
            )

    allowed_origin = "https://alphalense-frontend.vercel.app"
    allowed = asyncio.run(preflight(allowed_origin))
    rejected = asyncio.run(preflight("https://untrusted.example"))

    assert allowed.headers["access-control-allow-origin"] == allowed_origin
    assert "access-control-allow-origin" not in rejected.headers


def test_health_route_reports_liveness_without_external_requests(monkeypatch):
    monkeypatch.setenv("RENDER_GIT_COMMIT", "test-commit")
    monkeypatch.setenv("RENDER_GIT_BRANCH", "main")
    response = asyncio.run(_get_app("/api/health"))

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert {provider["name"] for provider in payload["providers"]} >= {
        "fmp", "finnhub", "alphavantage", "gnews", "news",
    }
    assert payload["deployment"] == {
        "commit": "test-commit",
        "branch": "main",
    }


def test_health_distinguishes_gnews_from_finnhub_news_fallback(monkeypatch):
    monkeypatch.setenv("FINNHUB_API_KEY", "configured-test-key")
    monkeypatch.delenv("GNEWS_API_KEY", raising=False)

    response = asyncio.run(_get_app("/api/health"))

    providers_by_name = {
        item["name"]: item["configured"]
        for item in response.json()["providers"]
    }
    assert providers_by_name["news"] is True
    assert providers_by_name["gnews"] is False


def test_invalid_ticker_is_rejected_before_provider_calls(monkeypatch):
    async def unexpected_provider_call(ticker):
        raise AssertionError("invalid tickers must not be sent to a provider")

    monkeypatch.setattr(server, "get_quote", unexpected_provider_call)
    response = asyncio.run(_get_app("/api/quote/THISISWAYTOOLONG"))

    assert response.status_code == 422


def test_quote_and_profile_distinguish_missing_configuration_from_provider_failure(monkeypatch):
    async def no_quote(ticker):
        return None

    async def no_profile(ticker):
        return None

    monkeypatch.setattr(server, "get_quote", no_quote)
    monkeypatch.setattr(server, "get_profile", no_profile)
    for key in ("FMP_API_KEY", "FINNHUB_API_KEY", "ALPHA_VANTAGE_API_KEY"):
        monkeypatch.delenv(key, raising=False)

    async def requests():
        return [
            await _get_app("/api/quote/NVDA"),
            await _get_app("/api/profile/NVDA"),
        ]

    no_credentials = asyncio.run(requests())
    assert [response.status_code for response in no_credentials] == [503, 503]

    monkeypatch.setenv("FMP_API_KEY", "configured-test-key")
    provider_failures = asyncio.run(requests())
    assert [response.status_code for response in provider_failures] == [404, 404]


def test_market_data_fetch_survives_one_provider_component_exception(monkeypatch):
    async def fake_profile(ticker):
        return {"ticker": ticker, "name": "Example Co"}

    async def failing_quote(ticker):
        raise httpx.ReadTimeout("upstream timeout")

    async def empty(*args, **kwargs):
        return {}

    monkeypatch.setattr(server, "get_profile", fake_profile)
    monkeypatch.setattr(server, "get_quote", failing_quote)
    monkeypatch.setattr(server, "get_financials", empty)
    monkeypatch.setattr(server, "get_ratios", empty)
    monkeypatch.setattr(server, "get_peers", empty)
    monkeypatch.setattr(server, "get_analyst", empty)
    monkeypatch.setattr(server, "get_news", empty)
    monkeypatch.setattr(server, "get_history", empty)

    result = asyncio.run(server._fetch_market_data(" nvda "))

    assert result["profile"]["ticker"] == "NVDA"
    assert result["quote"] is None


def test_market_data_fetch_discards_mismatched_provider_tickers(monkeypatch):
    async def fake_profile(ticker):
        return {"ticker": "AAPL", "name": "Wrong Company"}

    async def fake_quote(ticker):
        return {"ticker": ticker, "price": 100}

    async def empty(*args, **kwargs):
        return {}

    monkeypatch.setattr(server, "get_profile", fake_profile)
    monkeypatch.setattr(server, "get_quote", fake_quote)
    for name in ("get_financials", "get_ratios", "get_peers", "get_analyst", "get_news", "get_history"):
        monkeypatch.setattr(server, name, empty)

    result = asyncio.run(server._fetch_market_data("NVDA"))

    assert result["profile"] is None
    assert result["quote"]["ticker"] == "NVDA"


def test_recent_reports_exposes_unconfigured_storage():
    server.db = None
    response = asyncio.run(_get_app("/api/research/recent/list"))

    assert response.status_code == 503


def test_agent_memory_saves_bounded_summary_with_30_day_expiry(monkeypatch):
    class FakeMemoryCollection:
        def __init__(self):
            self.document = None

        async def update_one(self, query, update, upsert=False):
            assert query == {"report_id": "report-1"}
            assert upsert is True
            self.document = update["$set"]

    collection = FakeMemoryCollection()
    monkeypatch.setattr(
        server,
        "db",
        SimpleNamespace(agent_memory=collection),
    )
    state = {
        "moderator": {
            "recommendation": "HOLD",
            "confidence_score": 60,
            "executive_summary": "Current evidence supports a cautious view.",
            "key_reasons": ["Retrieved ratio evidence"],
            "risks": ["Valuation risk"],
            "data_sources": ["fmp"],
        },
        "research": {"business_summary": "Research output"},
    }

    saved = asyncio.run(
        server._save_agent_memory("report-1", "AAPL", state)
    )

    assert saved is True
    assert collection.document["ticker"] == "AAPL"
    assert collection.document["recommendation"] == "HOLD"
    assert set(collection.document["agent_outputs"]) == {
        "research", "moderator",
    }
    assert (
        collection.document["expires_at"] - collection.document["updated_at"]
    ).days == 30


def test_agent_memory_loads_session_and_prior_ticker_history(monkeypatch):
    session_record = {
        "report_id": "report-1",
        "ticker": "NVDA",
        "recommendation": "INVEST",
        "confidence_score": 70,
    }

    class FakeCursor:
        def sort(self, *args, **kwargs):
            return self

        def limit(self, *args, **kwargs):
            return self

        async def to_list(self, *args, **kwargs):
            return [
                session_record,
                {
                    "report_id": "report-old",
                    "ticker": "NVDA",
                    "recommendation": "HOLD",
                },
            ]

    class FakeMemoryCollection:
        async def find_one(self, query, projection):
            return session_record

        def find(self, query, projection):
            assert query["ticker"] == "NVDA"
            return FakeCursor()

    monkeypatch.setattr(
        server,
        "db",
        SimpleNamespace(agent_memory=FakeMemoryCollection()),
    )

    memory = asyncio.run(
        server._load_agent_memory("NVDA", "report-1")
    )

    assert memory["available"] is True
    assert memory["session"]["recommendation"] == "INVEST"
    assert memory["prior_research"][0]["recommendation"] == "HOLD"


def test_agent_memory_route_serializes_datetime_and_nested_object_id(monkeypatch):
    created_at = datetime.now(timezone.utc)
    nested_id = ObjectId()

    class FakeMemoryCollection:
        async def find_one(self, query, projection):
            assert projection == {"_id": 0}
            return {
                "report_id": query["report_id"],
                "created_at": created_at,
                "agent_outputs": {"source_id": nested_id},
            }

    monkeypatch.setattr(
        server,
        "db",
        SimpleNamespace(agent_memory=FakeMemoryCollection()),
    )
    response = asyncio.run(_get_app("/api/research/report-1/memory"))

    assert response.status_code == 200
    payload = response.json()
    assert payload["created_at"] == created_at.isoformat()
    assert payload["agent_outputs"]["source_id"] == str(nested_id)


def test_agent_memory_backfills_existing_completed_reports(monkeypatch):
    class FakeCursor:
        def sort(self, *args, **kwargs):
            return self

        def limit(self, *args, **kwargs):
            return self

        async def to_list(self, *args, **kwargs):
            return [{
                "id": "existing-report",
                "ticker": "NVDA",
                "recommendation": "HOLD",
                "confidence_score": 55,
                "agents": {
                    "research": {"business_summary": "Existing research"},
                    "moderator": {"executive_summary": "Existing moderation"},
                },
            }]

    class FakeReports:
        def find(self, *args, **kwargs):
            return FakeCursor()

    class FakeUpdateResult:
        upserted_id = "existing-report"

    class FakeMemory:
        async def update_one(self, query, update, upsert=False):
            assert query == {"report_id": "existing-report"}
            assert upsert is True
            assert update["$setOnInsert"]["ticker"] == "NVDA"
            assert update["$setOnInsert"]["agent_outputs"]["research"]["business_summary"] == "Existing research"
            return FakeUpdateResult()

    monkeypatch.setattr(
        server,
        "db",
        SimpleNamespace(
            research_reports=FakeReports(),
            agent_memory=FakeMemory(),
        ),
    )

    created = asyncio.run(server._backfill_agent_memory())

    assert created == 1


def test_agent_memory_ttl_index_migrates_existing_index_without_dropping_data(monkeypatch):
    commands = []
    attempted_indexes = []

    class FakeMemoryCollection:
        name = "agent_memory"

        async def create_index(self, keys, **kwargs):
            attempted_indexes.append((keys, kwargs))
            if keys == "expires_at":
                raise OperationFailure("IndexOptionsConflict", code=85)
            return "ticker_1_updated_at_-1"

        async def index_information(self):
            return {"expires_at_1": {"key": [("expires_at", 1)]}}

        async def count_documents(self, query):
            assert "expires_at" in query
            return 0

    class FakeDatabase:
        agent_memory = FakeMemoryCollection()

        async def command(self, command):
            commands.append(command)

    monkeypatch.setattr(server, "db", FakeDatabase())

    asyncio.run(server._ensure_agent_memory_indexes())

    assert commands == [{
        "collMod": "agent_memory",
        "index": {"name": "expires_at_1", "expireAfterSeconds": 0},
    }]
    assert len(attempted_indexes) == 2


def test_agent_memory_ttl_migration_preserves_records_past_expiry(monkeypatch, caplog):
    commands = []

    class FakeMemoryCollection:
        name = "agent_memory"

        async def create_index(self, keys, **kwargs):
            if keys == "expires_at":
                raise OperationFailure("IndexOptionsConflict", code=85)

        async def index_information(self):
            return {"expires_at_1": {"key": [("expires_at", 1)]}}

        async def count_documents(self, query):
            return 1

    class FakeDatabase:
        agent_memory = FakeMemoryCollection()

        async def command(self, command):
            commands.append(command)

    monkeypatch.setattr(server, "db", FakeDatabase())

    asyncio.run(server._ensure_agent_memory_indexes())

    assert commands == []
    assert "migration skipped to preserve existing records" in caplog.text


def test_research_sse_stream_completes_with_agent_result(monkeypatch):
    async def fake_market_data(ticker):
        return {
            "profile": {"ticker": ticker, "name": "Example Co", "source": "test"},
            "quote": {"ticker": ticker, "price": 10, "source": "test"},
            "financials": {},
            "ratios": {},
            "peers": [],
            "analyst": None,
            "news": [],
            "history": [],
        }

    async def fake_pipeline(state, emit):
        await emit("agent_start", {"agent": "moderator"})
        state["moderator"] = {
            "recommendation": "HOLD",
            "confidence_score": 50,
        }
        await emit("agent_done", {"agent": "moderator", "data": state["moderator"]})
        return state

    monkeypatch.setattr(server, "_fetch_market_data", fake_market_data)
    monkeypatch.setattr(server, "run_pipeline_streaming", fake_pipeline)
    monkeypatch.setattr(server, "db", None)

    response = asyncio.run(_get_app("/api/research/start?ticker=AAPL"))

    assert response.status_code == 200
    assert "event: market_data" in response.text
    assert '"recommendation": "HOLD"' in response.text
    assert "event: complete" in response.text
    assert '"persisted": false' in response.text


def test_report_storage_failure_is_warned_and_marked_not_persisted(monkeypatch):
    async def valid_market_data(ticker):
        return {
            "profile": {"ticker": ticker, "name": "Example Co"},
            "quote": {"ticker": ticker, "price": 100},
            "financials": {}, "ratios": {}, "peers": [], "analyst": None,
            "news": [], "history": [],
        }

    async def valid_pipeline(state, emit):
        state["moderator"] = {"recommendation": "HOLD", "confidence_score": 50}
        return state

    class FailingCollection:
        async def insert_one(self, report):
            raise PyMongoError("storage unavailable")

    monkeypatch.setattr(server, "_fetch_market_data", valid_market_data)
    monkeypatch.setattr(server, "run_pipeline_streaming", valid_pipeline)
    monkeypatch.setattr(server, "db", SimpleNamespace(research_reports=FailingCollection()))

    response = asyncio.run(_get_app("/api/research/start?ticker=NVDA"))

    assert "event: warning" in response.text
    assert '"persisted": false' in response.text


def test_research_sse_reports_market_provider_failure(monkeypatch):
    async def failing_market_data(ticker):
        raise RuntimeError("provider unavailable")

    monkeypatch.setattr(server, "_fetch_market_data", failing_market_data)

    response = asyncio.run(_get_app("/api/research/start?ticker=AAPL"))

    assert response.status_code == 200
    assert "event: error" in response.text
    assert "Market data providers could not complete this request." in response.text


def test_research_sse_explains_missing_quote_profile_provider_keys(monkeypatch):
    async def no_market_data(ticker):
        return {"profile": None, "quote": None}

    for key in ("FMP_API_KEY", "FINNHUB_API_KEY", "ALPHA_VANTAGE_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(server, "_fetch_market_data", no_market_data)

    response = asyncio.run(_get_app("/api/research/start?ticker=AAPL"))

    assert response.status_code == 200
    assert "event: error" in response.text
    assert "No stock-data provider is configured." in response.text


def test_research_sse_distinguishes_provider_failure_from_missing_keys(monkeypatch):
    async def no_market_data(ticker):
        return {"profile": None, "quote": None}

    monkeypatch.setenv("FINNHUB_API_KEY", "test-key")
    monkeypatch.setattr(server, "_fetch_market_data", no_market_data)

    response = asyncio.run(_get_app("/api/research/start?ticker=AAPL"))

    assert response.status_code == 200
    assert "event: error" in response.text
    assert "No configured provider returned a valid profile or quote" in response.text
    assert "Ticker 'AAPL' not found" not in response.text


def test_research_stops_when_quote_or_verified_profile_is_missing(monkeypatch):
    async def partial_market_data(ticker):
        return {
            "profile": {"ticker": ticker, "name": "Company"},
            "quote": None,
        }

    async def unexpected_pipeline(*args, **kwargs):
        raise AssertionError("agents must not run without a verified quote")

    monkeypatch.setattr(server, "_fetch_market_data", partial_market_data)
    monkeypatch.setattr(server, "run_pipeline_streaming", unexpected_pipeline)
    response = asyncio.run(_get_app("/api/research/start?ticker=NVDA"))

    assert "identified, but no provider returned a valid quote" in response.text
    assert "event: complete" not in response.text


def test_research_pipeline_error_does_not_save_or_emit_complete(monkeypatch):
    async def valid_market_data(ticker):
        return {
            "profile": {"ticker": ticker, "name": "Example Co"},
            "quote": {"ticker": ticker, "price": 100},
            "financials": {}, "ratios": {}, "peers": [], "analyst": None,
            "news": [], "history": [],
        }

    async def failed_pipeline(state, emit):
        raise RuntimeError("AI provider unavailable")

    monkeypatch.setattr(server, "_fetch_market_data", valid_market_data)
    monkeypatch.setattr(server, "run_pipeline_streaming", failed_pipeline)
    monkeypatch.setattr(server, "db", None)

    response = asyncio.run(_get_app("/api/research/start?ticker=NVDA"))

    assert "AI provider unavailable" in response.text
    assert "event: complete" not in response.text
