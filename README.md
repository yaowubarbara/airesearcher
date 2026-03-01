# AI Researcher

An AI-powered academic research assistant with multi-agent architecture. Designed for scholars who want to accelerate literature discovery, reference management, and manuscript drafting.

## What it does

- **Journal Monitoring** — Track new publications across Semantic Scholar, OpenAlex, CrossRef, and RSS feeds
- **Smart Discovery** — Cluster papers into research directions using structured annotation (Tension / Mediator / Scale / Gap)
- **Reference Acquisition** — Automatically resolve open-access PDFs via Unpaywall, CORE, arXiv, and Europe PMC
- **Plan Generation** — Create structured research outlines with readiness checks and theory supplementation
- **Writing Agent** — Draft manuscripts with citation injection, self-review loops, and journal style adaptation
- **Citation Verification** — Parse inline citations and verify against CrossRef/OpenAlex APIs

## Architecture

Built with **LangGraph** for multi-agent orchestration:

- **Self-Refine** — Iterative critique and revision of generated content
- **Reflexion** — Learning from past failures to improve output
- **Corrective RAG** — Retrieval-augmented generation with quality checks
- **Multi-Agent Debate** — Multiple perspectives for research gap analysis

## Stack

Python, LangGraph, FastAPI, Next.js, ChromaDB, SQLite, LiteLLM

## Usage

```bash
# Backend
cd api && uvicorn main:app --port 8001

# Frontend
cd frontend && npm run dev

# CLI
python cli.py discover --domain comparative_literature
python cli.py plan --topic "..."
python cli.py write --plan-id 1
```

## Project Structure

```
src/           Core modules (orchestrator, writer, reviewer, searcher, ...)
api/           FastAPI backend with REST + WebSocket endpoints
frontend/      Next.js 14 web interface
config/        Domain configs and journal style profiles
prompts/       LLM prompt templates per domain
data/          SQLite DB and ChromaDB vector store
```
