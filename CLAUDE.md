# AI Researcher - Project Memory

## Current Status
- Phase: 9 (End-to-End LLM Pipeline Tests) — COMPLETE + post-Phase 9 bug fixes
- Last completed: Fixed 3 bugs found during Phase 9 testing
- Currently working on: Nothing
- Blockers: None

## Architecture
- LangGraph StateGraph orchestrator connecting all modules
- LiteLLM unified LLM gateway with task-based routing
- ChromaDB for vector storage, SQLite for metadata
- Multi-agent patterns: STORM (topic discovery), Self-Refine (writing), Reflexion (memory), Corrective RAG (research planning), Multi-Agent Debate (self-review)
- **Reference Acquisition Pipeline**: API search → auto-download OA PDFs → **multi-source OA resolution** → **institutional proxy** → human wishlist → batch index → ChromaDB → writer context injection

## Module Progress
- [x] Project structure setup
- [x] pyproject.toml
- [x] knowledge_base/models.py, db.py, vector_store.py
- [x] llm/router.py + config/llm_routing.yaml
- [x] journal_monitor/sources/* (semantic_scholar, openalex, crossref, cnki stub, rss)
- [x] journal_monitor/monitor.py, models.py
- [x] literature_indexer/pdf_parser.py, embeddings.py, indexer.py
- [x] topic_discovery/gap_analyzer.py, trend_tracker.py, topic_scorer.py
- [x] research_planner/planner.py, outline_generator.py, reference_selector.py
- [x] writing_agent/writer.py, close_reader.py, citation_manager.py
- [x] reference_verifier/verifier.py, doi_resolver.py, format_checker.py
- [x] self_review/reviewer.py, style_checker.py, journal_fit.py
- [x] journal_style_learner/learner.py, style_profile.py, style_extractor.py
- [x] submission_manager/formatter.py, cover_letter.py, response_template.py
- [x] orchestrator.py (LangGraph workflow with ACQUIRE_REFS phase)
- [x] cli.py (Click CLI with all commands + scheduler)
- [x] config/journals.yaml (18 journals: EN/ZH/FR)
- [x] config/journal_profiles/ (8 profiles: EN/ZH/FR)
- [x] config/reviewer_profiles/ (6 profiles: EN/ZH/FR)
- [x] prompts/ (close_reading, gap_analysis, review, writing/*)
- [x] **reference_acquisition/** (searcher, downloader, pipeline, web_searcher, **oa_resolver**, **proxy_session**)
- [x] **utils/api_clients.py** (S2, OpenAlex, CrossRef, **Unpaywall, CORE**)
- [x] **config/proxy.yaml** (institutional proxy config with 11 publisher domains)
- [x] tests/ (8 test files, 123 unit tests total)
- [x] **tests/test_llm_pipeline.py** (5 LLM pipeline tests: discover, plan, write, review, full chain)

## Phase 6 — Reference Acquisition Pipeline (COMPLETE)
- [x] Paper model + DB: added `pdf_url` field, migration, `update_paper_pdf()`, `get_papers_needing_pdf()`
- [x] API sources extract OA PDF URLs: S2 `openAccessPdf`, OpenAlex `pdf_url`/`oa_url`, CrossRef `link[]`
- [x] `src/reference_acquisition/searcher.py` — multi-API keyword search with DOI dedup
- [x] `src/reference_acquisition/downloader.py` — async PDF downloader with size/magic validation
- [x] `src/reference_acquisition/pipeline.py` — search→insert→download→index orchestration
- [x] `src/reference_acquisition/web_searcher.py` — Google Books + Open Library for novels/theory/criticism
- [x] Research Planner integration — auto-acquires references before `ReferenceSelector`
- [x] Writer enhancement — `_retrieve_reference_context()` injects ChromaDB passages into prompts
- [x] Orchestrator — `ACQUIRE_REFS` node between discover→plan
- [x] CLI: `search-references`, `search-books`, `wishlist`, `index-folder`
- [x] Tests: 20 new unit tests (OA URL extraction, PDF validation, dedup, DB wishlist, web searcher)

## Phase 7 — Autonomous OA Resolution (COMPLETE)
- [x] `UnpaywallClient` — queries Unpaywall API by DOI, returns `best_oa_location` + `oa_locations[]` PDF URLs
- [x] `COREClient` — queries CORE API by DOI or title, returns `downloadUrl` from 200M+ institutional repos
- [x] Paper model: added `external_ids: dict[str, str]` field (stores ArXiv, PMID, PMCID, etc.)
- [x] DB migration for `external_ids` column
- [x] `_s2_paper_to_paper()` populates `external_ids` from S2 `externalIds`
- [x] `src/reference_acquisition/oa_resolver.py` — `OAResolver` with 5-source priority chain:
  1. Unpaywall (best_oa_location, then oa_locations[])
  2. CORE (DOI search, then title search with Jaccard similarity > 0.8)
  3. arXiv (extract ID from external_ids/DOI/URL → construct PDF URL)
  4. Europe PMC (DOI/PMID → PMCID → PDF URL)
  5. DOI content negotiation (HEAD with Accept: application/pdf)
- [x] `download_with_fallback()` in downloader — tries multiple URLs in sequence
- [x] Pipeline integration — step 3.5 runs OA resolver on failed/missing papers
- [x] `AcquisitionReport.oa_resolved` field tracks OA-resolved count
- [x] CLI: `resolve-oa` command with `--limit` and `--dry-run` flags
- [x] Tests: 40 unit tests + 3 integration tests (all passing, no regressions)

## Phase 8 — Institutional Proxy Access (COMPLETE)
- [x] `config/proxy.yaml` — proxy config template with 11 publishers (JSTOR, MUSE, Springer, Elsevier, Wiley, T&F, CUP, OUP, Duke, SAGE, De Gruyter)
- [x] `src/reference_acquisition/proxy_session.py` — `InstitutionalProxy` class:
  - Config loading from YAML, password from env var (never stored in file)
  - `needs_proxy(url)` — domain matching against publisher list
  - `rewrite_url(url)` — query string mode + prefix mode auto-detection
  - `login()` — POST to EZproxy with session cookie persistence
  - `download_pdf(url, dest)` — authenticated download with PDF validation
  - `download_paper(paper, dir)` — DOI → publisher URL → proxy rewrite → download
  - `update_config()` / `save_config()` — programmatic config management
- [x] Downloader enhancement — `PDFDownloader` accepts optional `proxy` param, `download_via_proxy()` method
- [x] Pipeline integration — step 3.75 runs proxy download after OA resolver, before wishlist
- [x] `AcquisitionReport.proxy_downloaded` field tracks proxy-downloaded count
- [x] CLI: `config-proxy` (one-time setup with login test) + `proxy-download` (batch download with `--limit`/`--dry-run`)
- [x] Tests: 25 unit tests (config loading, domain matching, URL rewriting, login, download, pipeline integration)

## Phase 9 — End-to-End LLM Pipeline Tests (COMPLETE)
- [x] `pyproject.toml` — added `llm_pipeline` pytest marker
- [x] `tests/test_llm_pipeline.py` — 5 test functions exercising real LLM calls:
  - `test_stage_discover()` — STORM multi-perspective gap analysis + topic scoring (6 LLM calls)
  - `test_stage_plan()` — thesis generation + reference selection + outline generation (3-8 LLM calls)
  - `test_stage_write()` — 2-section manuscript with Self-Refine + abstract (5-7 LLM calls)
  - `test_stage_review()` — Multi-Agent Debate with 3 reviewers + meta-reviewer (4 LLM calls)
  - `test_full_chain()` — discover → plan → write → review end-to-end (uses temp DB copy)
- [x] Dual run modes: `pytest -m llm_pipeline` or `python tests/test_llm_pipeline.py [stage]`
- [x] Rate-limit retry with exponential backoff (5s → 10s → 20s)
- [x] Cost tracking and reporting per stage
- [x] Graceful skip when ZHIPUAI_API_KEY not set
- [x] All 121 existing unit tests unchanged, no regressions

## Post-Phase 9 Bug Fixes
- [x] **Abstract generation overflow** (`writer.py`): Long manuscripts exceeded GLM-5 context window, producing empty abstracts. Fix: truncate to 12K chars (head+tail) before sending to LLM.
- [x] **CrossRef search noise** (`searcher.py`, `api_clients.py`): CrossRef `query` parameter returned completely irrelevant results (Trump tariffs, dental calculus for a comparative literature query). Fix: switched to `query.bibliographic` (title/abstract only) + keyword overlap filtering on titles.
- [x] **Plan stage redundant acquisition** (`planner.py`, `orchestrator.py`): `create_plan()` ran full reference acquisition pipeline (~20min) even when orchestrator already did it in a prior step. Fix: added `skip_acquisition` parameter; orchestrator now skips it; tests use `skip_acquisition=True`.

## Real-world Testing Results
- API search (OpenAlex/CrossRef): works, returns metadata + some pdf_urls
- Semantic Scholar: works but easily rate-limited (429) without API key
- PDF download: works for truly OA sources (arXiv confirmed: 2.1MB PDF downloaded + indexed)
- Most publisher "OA" URLs return 403 (need institutional access)
- Archive.org PDFs: 401/403 (need borrowing session)
- Google Books: works but low free quota (429 quickly)
- Open Library: works, finds classic literature
- Full indexing pipeline: confirmed working — PDF → 24 sections → 42 ChromaDB chunks → semantic search returns relevant passages
- **Human-in-the-loop workflow**: agent generates wishlist → user provides PDFs → `index-folder` batch indexes

## Test Summary
- `tests/test_monitor.py` — 7 unit tests (DB operations)
- `tests/test_verifier.py` — 11 unit tests (format checker, DOI resolver)
- `tests/test_writer.py` — 15 unit tests (language detection, chunking, citations, word count)
- `tests/test_reference_acquisition.py` — 20 unit tests + 3 integration tests (OA extraction, dedup, DB, web searcher)
- `tests/test_oa_resolver.py` — 40 unit tests + 3 integration tests (Unpaywall, CORE, arXiv, Europe PMC, priority order, batch, fallback)
- `tests/test_integration_apis.py` — 14 integration tests (real API calls)
- `tests/test_proxy_session.py` — 25 unit tests (config, domain matching, URL rewriting, login, download, pipeline integration)
- `tests/test_e2e.py` — 6 end-to-end tests (full workflow)
- `tests/test_llm_pipeline.py` — 5 LLM pipeline tests (real API calls, skipped without key)
- **Total: 121 unit tests + 5 LLM pipeline tests, all passing (LLM tests skip without ZHIPUAI_API_KEY)**

## Key Decisions
- LiteLLM as unified LLM gateway (see decisions.md #001)
- ChromaDB for vector store (see decisions.md #002)
- GLM embedding-3 API for embeddings (see decisions.md #003)
- LangGraph for orchestration (see decisions.md #004)
- Human-in-the-loop for PDF acquisition (most publishers block direct download)
- Multi-source OA resolution before human fallback (Unpaywall → CORE → arXiv → Europe PMC → DOI negotiation)
- Institutional proxy as fallback after OA resolution, before human wishlist

## CLI Commands Available
- `ai-researcher monitor` - Scan journals for new papers
- `ai-researcher index <pdf>` - Index a PDF into knowledge base
- `ai-researcher **index-folder** <dir>` - Batch-index all PDFs in a folder
- `ai-researcher **search-references** <topic>` - Search APIs + generate PDF wishlist
- `ai-researcher **search-books** <queries...>` - Search Google Books + Open Library
- `ai-researcher **resolve-oa** [--limit N] [--dry-run]` - Resolve OA URLs for papers missing PDFs
- `ai-researcher **config-proxy**` - Configure institutional proxy (one-time setup)
- `ai-researcher **proxy-download** [--limit N] [--dry-run]` - Download paywalled PDFs via proxy
- `ai-researcher **wishlist**` - Show papers still needing PDFs
- `ai-researcher discover` - Find research gaps
- `ai-researcher plan <topic_id> --journal <name>` - Create research plan
- `ai-researcher write <plan_id>` - Generate manuscript
- `ai-researcher verify <ms_id>` - Verify references
- `ai-researcher review <ms_id>` - Self-review manuscript
- `ai-researcher format-manuscript <ms_id>` - Format for submission
- `ai-researcher learn-style <journal> <pdfs...>` - Learn journal style
- `ai-researcher pipeline --journal <name>` - Full pipeline
- `ai-researcher stats` - Usage statistics
- `ai-researcher scheduler` - Start periodic monitoring daemon

## Reference Acquisition Workflow
```
search-references "topic" → API搜索 → 自动下载OA PDF → OA解析(Unpaywall/CORE/arXiv/PMC/DOI)
                                                          ↓
                                              自动下载OA解析到的PDF
                                                          ↓
                                              机构代理下载(EZproxy, 如已配置)
                                                          ↓
                                              仍未获取 → 生成wishlist
                                                          ↓
wishlist → 显示待获取清单(标题/DOI) → 用户自己下载PDF → data/papers/
                                                          ↓
index-folder data/papers/ → 解析PDF → embedding → ChromaDB索引
                                                          ↓
plan/write → writer从ChromaDB检索真实段落 → 注入prompt → 引用真实内容

resolve-oa [--limit N] → 批量OA解析 → 自动下载+索引 → 减少wishlist

config-proxy → 配置EZproxy(一次性) → 保存config/proxy.yaml
proxy-download [--limit N] → DOI→出版商URL→代理重写→下载+索引 → 减少wishlist
```

## Notes for Next Session
- CNKI source is a stub (needs institutional API access)
- LLM pipeline tests: `python tests/test_llm_pipeline.py discover` (or plan/write/review/chain/all)
- LLM tests via pytest: `pytest tests/test_llm_pipeline.py -m llm_pipeline -v` (requires ZHIPUAI_API_KEY)
- Streamlit dashboard: run with `streamlit run dashboard.py`
- Scheduler: run with `ai-researcher scheduler` (blocks until Ctrl+C)
- Embeddings: GLM embedding-3 API (requires ZHIPUAI_API_KEY env var)
- ZHIPUAI_API_KEY has been provided and tested — embedding + indexing confirmed working
- Semantic Scholar free tier rate limits aggressively; consider getting an API key
- Google Books API also rate limits quickly; consider adding API key support
- `data/papers/` directory has one test PDF (arXiv attention paper)
- DB already has ~500 papers from prior monitor runs (most need PDFs — run `wishlist` to see)
- Unpaywall requires `UNPAYWALL_EMAIL` env var (defaults to `researcher@example.com`)
- CORE API supports optional `CORE_API_KEY` env var for higher rate limits
- Run `ai-researcher resolve-oa --dry-run --limit 10` to preview OA resolution without downloading
- Institutional proxy: run `ai-researcher config-proxy` to set up, requires `INSTITUTIONAL_PASSWORD` env var
- Run `ai-researcher proxy-download --dry-run --limit 5` to preview proxy URL rewriting
