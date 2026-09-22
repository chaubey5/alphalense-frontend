"""
check_limits_simple.py
No extra dependencies — uses Python stdlib only.
Run: python check_limits_simple.py
"""
import os
import json
import urllib.request
import urllib.error

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
FMP_API_KEY  = os.getenv("FMP_API_KEY", "")


def check_groq():
    print("\n=== GROQ ===")
    if not GROQ_API_KEY:
        print("❌ GROQ_API_KEY not set  →  set it with: set GROQ_API_KEY=your_key")
        return

    payload = json.dumps({
        "model": GROQ_MODEL,
        "messages": [{"role": "user", "content": "hi"}],
        "max_tokens": 1
    }).encode()

    req = urllib.request.Request(
        "https://api.groq.com/openai/v1/chat/completions",
        data=payload,
        headers={
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json",
        },
        method="POST"
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            headers = dict(resp.headers)
            body    = json.loads(resp.read())

        print("✅ Groq API working")
        print(f"   Requests remaining : {headers.get('x-ratelimit-remaining-requests', 'n/a')} / {headers.get('x-ratelimit-limit-requests', 'n/a')}")
        print(f"   Tokens remaining   : {headers.get('x-ratelimit-remaining-tokens', 'n/a')} / {headers.get('x-ratelimit-limit-tokens', 'n/a')}")
        print(f"   Requests reset in  : {headers.get('x-ratelimit-reset-requests', 'n/a')}")
        print(f"   Tokens reset in    : {headers.get('x-ratelimit-reset-tokens', 'n/a')}")

    except urllib.error.HTTPError as e:
        body = {}
        try:
            body = json.loads(e.read())
        except Exception:
            pass

        if e.code == 429:
            print("🚨 GROQ LIMIT HIT — 429 Too Many Requests")
            err = body.get("error", {})
            print(f"   Message : {err.get('message', 'n/a')}")
            print(f"   Type    : {err.get('type', 'n/a')}")
        elif e.code == 401:
            print("❌ GROQ — 401 Unauthorized (invalid API key)")
        elif e.code == 403:
            print("❌ GROQ — 403 Forbidden (API key is invalid, revoked, or lacks access)")
        else:
            print(f"⚠️  Groq returned HTTP {e.code}")
            print(f"   Body: {body}")

    except Exception as e:
        print(f"❌ Groq check failed: {e}")


def check_fmp():
    print("\n=== FMP (Financial Modeling Prep) ===")
    if not FMP_API_KEY:
        print("❌ FMP_API_KEY not set  →  set it with: set FMP_API_KEY=your_key")
        return

    url = f"https://financialmodelingprep.com/api/v3/quote/AAPL?apikey={FMP_API_KEY}"

    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            body = json.loads(resp.read())

        if isinstance(body, list) and len(body) > 0:
            print("✅ FMP API working")
            print(f"   Test quote (AAPL price): ${body[0].get('price', 'n/a')}")

        elif isinstance(body, dict):
            msg = body.get("Error Message", "") or body.get("message", "")
            if "Limit" in msg or "limit" in msg.lower():
                print(f"🚨 FMP LIMIT HIT: {msg}")
            elif "Invalid API" in msg or "apikey" in msg.lower():
                print(f"❌ FMP invalid API key: {msg}")
            else:
                print(f"⚠️  FMP unexpected: {body}")
        else:
            print(f"⚠️  FMP empty response: {body}")

    except urllib.error.HTTPError as e:
        if e.code == 429:
            print("🚨 FMP LIMIT HIT — 429 Too Many Requests")
        elif e.code == 403:
            print("🚨 FMP — 403 Forbidden (plan limit or invalid key)")
        else:
            print(f"⚠️  FMP HTTP {e.code}")

    except Exception as e:
        print(f"❌ FMP check failed: {e}")

    # FMP usage endpoint
    usage_url = f"https://financialmodelingprep.com/api/v4/usage?apikey={FMP_API_KEY}"
    try:
        with urllib.request.urlopen(usage_url, timeout=10) as resp:
            usage = json.loads(resp.read())
        print(f"   Daily calls used   : {usage.get('dailyRequestCount', 'n/a')}")
        print(f"   Plan               : {usage.get('currentPlanName', 'n/a')}")
    except Exception:
        print("   (Usage stats not available on free plan)")


if __name__ == "__main__":
    check_groq()
    check_fmp()
    print()