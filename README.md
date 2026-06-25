# AlphaLens

## Overview

AlphaLens is an AI-powered stock research platform that allows users to search for publicly traded companies, retrieve market data, company profiles, historical price information, news, and generate AI-assisted research reports. The system combines financial market APIs with large language models to provide structured investment research and analysis.

### Main Features

* Company and stock search

* Real-time stock quotes

* Company profile information

* Historical market data

* Latest company news

* AI-generated research reports

* REST API backend with interactive documentation

* Web-based frontend interface
## How to Run It

### Prerequisites

* Python 3.11+

* Node.js 18+

* MongoDB database

* API keys for financial data and AI services

# Steps

1. Clone repository

2. Setup backend

3. Install requirements

4. Configure .env

5. Run FastAPI server

6. Setup frontend

7. Install npm packages

8. Configure frontend .env

9. Run React app


Commands:
cd backend
pip install -r requirements.txt
uvicorn server:app --reload

### Backend Setup
1. Navigate to backend directory
cd backend

2. Install dependencies
pip install -r requirements.txt

3. Create a `.env` file
MONGO_URL=<your_mongodb_connection_string>

DB_NAME=alphalense

FMP_API_KEY=<your_financial_modeling_prep_key>

GROQ_API_KEY=<your_groq_api_key>

4. Run backend
uvicorn server:app --reload
Backend runs at:
http://localhost:8000

API documentation:
http://localhost:8000/docs

### Frontend Setup
1. Navigate to frontend directory
cd frontend

2. Install dependencies
npm install

3. Create `.env`
REACT_APP_BACKEND_URL=http://localhost:8000

4. Start frontend
npm start
Frontend runs at:
http://localhost:3000

### Production Deployment
Backend:
https://alphalense-backend.onrender.com

Frontend:
https://alphalense-frontend.vercel.app

## How It Works
### Architecture

[ React 19 Client UI Hub ] 

                     │ 

                     ▼ (Persistent EventSource Connection)

       [ FastAPI Async Gateway App ] 

                     │

         ┌───────────┴───────────┐

         ▼                       ▼

 [ Motor Async MongoDB ]   [ Asynchronous Graph Coordinator Pool ]

 (JSON State Ingestion)          │

                                 ├──► Phase 1: parallel [Research, Fin, Val, Macro]

                                 ├──► Phase 2: parallel [Bull vs. Bear Debate Node]

                                 └──► Phase 3: sequential [CIO Moderator Synthesis]

                                                 │

                                                 ▼

                                     [ Tiered Fallback Provider Mesh ]

                                     ├── FMP Stable (Primary Route)

                                     ├── Finnhub Ingestion (TTM Multiples & SEC Parsing)

                                     ├── Alpha Vantage (Company Profiles)

                                     └── Yahoo Finance (Chart Matrix Data Streams)

### Workflow

1. User searches for a company.

2. Backend retrieves market data and company information.

3. News and historical data are fetched.

4. Research pipeline aggregates information.

5. LLM generates a structured research report.

6. Report is returned to frontend and displayed to the user.


## Key Decisions & Trade-offs
### Decisions

* FastAPI chosen for high-performance backend APIs.

* React chosen for frontend UI development.

* MongoDB used for flexible report storage.

* Render used for backend deployment.

* Vercel used for frontend deployment.



### Trade-offs
* Free hosting tiers introduce cold starts.

* Research quality depends on external API availability.

* Financial data coverage is limited by API quotas.

* Focus was placed on functionality rather than advanced UI polish.



### Features Deferred

* User authentication

* Portfolio tracking

* Report export (PDF)

* Advanced caching layer

* Multi-agent research orchestration


## Example Runs

### Example 1: Apple (AAPL)
Output Highlights:

* Current market price

* Company overview

* Recent news summary

* AI-generated investment research


### Example 2: Tesla (TSLA)
Output Highlights:

* Historical performance trends

* Recent developments

* Risk factors

* Research summary



### Example 3: Microsoft (MSFT)
Output Highlights:

* Financial overview

* Market positioning

* AI-generated analysis


## What I Would Improve With More Time

* Add authentication and user accounts

* Portfolio monitoring features

* Advanced report generation

* PDF export support

* Better caching and performance optimization

* Enhanced financial metrics and visualizations

* Improved research depth using multiple LLM agents

* Automated testing and CI/CD pipelines

  

## LLM Usage

AI/LLM Co-Pilot Integration & Thought Process

* AI/LLM Methodology Selection: This platform was engineered using an iterative, dual-model AI development paradigm. To maximize code generation fidelity and architectural execution, Claude 4.5 (via E1 coding assistant configuration) was selected as the primary Pair-Programmer and Systems Architect. Concurrently, Groq's LLaMA-3.3-70B-Versatile engine was chosen as the runtime multi-agent orchestration infrastructure due to its sub-3-second inference speeds.

* Detailed LLM In-Context Inventions & Engineering Contributions:
System Architecture Planning & DAG Topology:
Assisted in designing a 3-Phase non-blocking Directed Acyclic Graph (DAG) using native Python asyncio.gather().

* The LLM guided the decision to bypass heavy frameworks like LangGraph in favor of a raw async supervisor-worker pool to minimize compute latency and prevent task overhead.

* Multi-Tier Provider Hardening (HTTP 429 Mitigation):

* During active sandboxed execution, primary data nodes experienced immediate rate-limit failures (HTTP 429).

* The LLM assisted in writing an in-memory TTL caching layout and mapping out an alternative ingestion pipeline. This allowed the system to parse raw Finnhub SEC GAAP JSON streams (us-gaap_Revenues) to dynamically rebuild balance sheets when primary APIs degraded.

* Context Density Tuning & Token Optimization:

* Initial parallel runs choked on Groq's Daily Token Limits (TPD) due to passing full raw JSON streams down to secondary agents (Bull, Bear, Moderator).

* Co-piloted a contextual compaction algorithm that reduced prompt token payloads by over 60%, stabilizing the multi-agent pipeline under production limits.

* Frontend Architecture & Reactive Stream Binding:

* Guided the implementation of a unified React useReducer state hook (useResearchPipeline.js) to consume backend Server-Sent Events (SSE) cleanly.

* Resolved critical frontend closures and state-shadowing bugs, and assisted in configuring root metadata overrides inside frontend/public/index.html to fully stamp out framework placeholders.



Deployment Operations & CI/CD Debugging:

* Provided rapid troubleshooting patterns for path routing discrepancies during Render deployment (FastAPI route ordering fixes) and automated environment configuration bindings on Vercel.

* give me the direct pdf file above info like read me file of project and same flow of arctechture
