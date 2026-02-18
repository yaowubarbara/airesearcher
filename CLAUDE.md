# AI Researcher

## User Workflow Rules
- **"交互一下"**: Start Cloudflare tunnel → `cloudflared tunnel --url http://localhost:3009` (frontend dev server). Ensure frontend is running first (`cd frontend && npm run dev`).

## Current Status
- All 15 phases complete. 568 unit tests + 5 LLM pipeline tests passing.
- No active work or blockers.

## Architecture
- **LangGraph** StateGraph orchestrator → LiteLLM gateway → ChromaDB vectors + SQLite metadata
- Multi-agent patterns: P-ontology annotation (discovery), Self-Refine (writing), Reflexion (memory), Corrective RAG (planning), Multi-Agent Debate (review)
- Reference pipeline: API search → OA download → OA resolve (Unpaywall/CORE/arXiv/PMC/DOI) → institutional proxy → human wishlist → ChromaDB index → writer context injection
- Frontend: Next.js + FastAPI (port 3009 / 8000)

## CLI Quick Reference
```
ai-researcher monitor|index|index-folder|search-references|search-books
ai-researcher resolve-oa|config-proxy|proxy-download|wishlist
ai-researcher discover|plan|write|verify|verify-citations|review
ai-researcher format-manuscript|learn-style|pipeline|stats|scheduler
```
