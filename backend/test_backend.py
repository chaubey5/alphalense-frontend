import asyncio
import json
from typing import Dict, Any

# Import the functions from your main file
# Replace 'your_main_file' with the actual name of your python script file
# Change this line in test_backend.py:
from agents import run_pipeline_streaming

async def mock_emit(event_type: str, payload: dict):
    """Tracks agent progress in the console."""
    agent = payload.get("agent", "unknown")
    if event_type == "agent_start":
        print(f"  ⏳ [{agent.upper()}] processing...")
    elif event_type == "agent_done":
        print(f"  ✅ [{agent.upper()}] completed successfully.")

async def test_backend():
    print("🚀 STARTING BACKEND INTEGRATION TEST...\n")

    # ----------------------------------------------------
    # TEST CASE 1: Standard Corporate Company (Apple)
    # ----------------------------------------------------
    print("--- 🏭 CASE 1: Testing Standard Corporate Path (AAPL) ---")
    corporate_state = {
        "ticker": "AAPL",
        "profile": {"sector": "Technology", "industry": "Consumer Electronics"},
        "financials": {
            "income": [{"year": 2025, "revenue": 390000, "net_income": 95000}],
            "balance": [], "cashflow": []
        },
        "ratios": {"peTTM": 30.0, "pbTTM": 40.0, "evToEbitda": 22.0},
        "quote": {"price": 180.00}
    }
    
    try:
        res_corp = await run_pipeline_streaming(corporate_state, mock_emit)
        print(f"🎯 Corp Valuation Verdict: {res_corp['valuation'].get('valuation_verdict')}\n")
    except Exception as e:
        print(f"❌ Corporate Path Crashed! Error: {e}\n")


    # ----------------------------------------------------
    # TEST CASE 2: Banking Profile (Bandhan Bank)
    # ----------------------------------------------------
    print("--- 🏦 CASE 2: Testing Banking Path (BANDHANBNK.NS) ---")
    banking_state = {
        "ticker": "BANDHANBNK.NS",
        "profile": {"sector": "Financial Services", "industry": "Banks - Private Sector"},
        "financials": {"income": [], "balance": [], "cashflow": []},
        "ratios": {"peTTM": 26.5, "pbTTM": 1.35, "nim": "6.2%", "gross_npa": "3.3%"},
        "quote": {"price": 201.76}
    }
    
    try:
        res_bank = await run_pipeline_streaming(banking_state, mock_emit)
        print(f"🎯 Bank Valuation Verdict: {res_bank['valuation'].get('valuation_verdict')}\n")
    except Exception as e:
        print(f"❌ Banking Path Crashed! Error: {e}\n")

    print("🏁 TEST COMPLETE.")

if __name__ == "__main__":
    asyncio.run(test_backend())