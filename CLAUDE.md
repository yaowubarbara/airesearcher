# AI Researcher - Project Memory

## User Workflow Rules
- **"交互一下"**: When the user says "交互一下" (or similar like "我要交互"), immediately start a Cloudflare tunnel (`cloudflared tunnel --url http://localhost:3009`) pointing to the current project's frontend dev server. Ensure:
  1. The frontend dev server is running (`cd frontend && npm run dev` on port 3009 if not already running)
  2. Start `cloudflared tunnel --url http://localhost:3009` in the background
  3. Return the generated `*.trycloudflare.com` link to the user
  4. The link must point to **this project's** frontend (ai-researcher), not any other service

## Current Status
- Phase: 14 (Discovery Refactor: Problématique Ontology) — COMPLETE
- Last completed: P-ontology annotation, direction clustering, topic generation, two-level frontend
- Currently working on: Nothing
- Blockers: None

## Architecture
- LangGraph StateGraph orchestrator connecting all modules
- LiteLLM unified LLM gateway with task-based routing
- ChromaDB for vector storage, SQLite for metadata
- Multi-agent patterns: **P-ontology annotation** (topic discovery), Self-Refine (writing), Reflexion (memory), Corrective RAG (research planning), Multi-Agent Debate (self-review)
- **Reference Acquisition Pipeline**: API search → auto-download OA PDFs → **multi-source OA resolution** → **institutional proxy** → human wishlist → batch index → ChromaDB → writer context injection

## Module Progress
- [x] Project structure setup
- [x] pyproject.toml
- [x] knowledge_base/models.py, db.py, vector_store.py
- [x] llm/router.py + config/llm_routing.yaml
- [x] journal_monitor/sources/* (semantic_scholar, openalex, crossref, cnki stub, rss)
- [x] journal_monitor/monitor.py, models.py
- [x] literature_indexer/pdf_parser.py, embeddings.py, indexer.py
- [x] topic_discovery/gap_analyzer.py (**P-ontology annotation**), trend_tracker.py (**direction clustering**), topic_scorer.py (**topic generation**)
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
- [x] **config/citation_profiles/comparative_literature.yaml** (citation norms from 6-article analysis)
- [x] **citation_verifier/** (parser, engine, annotator, pipeline — MLA citation parsing + CrossRef/OpenAlex verification + [VERIFY] tags)
- [x] **Web frontend** — Next.js + FastAPI: ReadinessPanel (upload + re-check), PlanOutline (per-section grounding), PlanChat, sufficiency gate, **DirectionCard** (two-level discover)
- [x] tests/ (15 test files, 510 unit tests total)
- [x] **tests/test_llm_pipeline.py** (5 LLM pipeline tests: discover, plan, write, review, full chain)
- [x] **tests/test_citation_profile.py** (34 tests: profile loading, ReferenceType, DB, classification, balance)
- [x] **tests/test_citation_phase10.py** (54 tests: Phase 10 citation features end-to-end)
- [x] **tests/test_citation_manager.py** (83 tests: footnotes, block quotes, secondary citation, multilingual, verification, critic parsing)
- [x] **tests/test_citation_verifier.py** (64 tests: parser, engine, annotator, report, pipeline)
- [x] **tests/test_primary_text_detection.py** (36 tests: title extraction, Jaccard overlap, models, detection with mocked DB/VS, DB title search)
- [x] **tests/test_problematique.py** (41 tests: P-ontology enums, models, DB annotations/directions/topics, annotation pipeline, clustering, generation, row converters, parse helpers)

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

## Phase 10 — Citation Profile & Reference Type System (COMPLETE)

### Phase 10.1 — Citation Profile (COMPLETE)
- [x] Synthesized cross-paper citation patterns from 6 published articles in *Comparative Literature*
- [x] `config/citation_profiles/comparative_literature.yaml` — comprehensive citation norms including:
  - Reference type distribution targets (primary_literary, secondary_criticism, theory, methodology, historical_context, reference_work, self_citation)
  - Bibliography size targets (35-60 entries)
  - Citation density norms (3.0-5.5 per page, with section-level patterns)
  - Quotation patterns (what to quote vs paraphrase, block quote conventions)
  - Quote introduction strategies (verbs, framing patterns, advanced techniques)
  - Multilingual handling rules (original-first for primary texts, translation attribution)
  - Footnote conventions (8-20 substantive notes, not mere pointers)
  - Citation format specification (Chicago/MLA hybrid)
  - 9 reference selection principles distilled from cross-paper analysis
  - Author positioning conventions (sympathetic extension, dialectical synthesis, immanent critique)

### Phase 10.2 — Reference Type System (COMPLETE)
- [x] `ReferenceType` enum in `models.py`: 8 types (primary_literary, secondary_criticism, theory, methodology, historical_context, reference_work, self_citation, unclassified)
- [x] `ref_type` field added to `Reference` model (default: unclassified)
- [x] DB schema updated: `ref_type TEXT NOT NULL DEFAULT 'unclassified'` in references_ table
- [x] DB migration for existing databases (ALTER TABLE adds column)
- [x] `insert_reference()` and `_row_to_reference()` updated for ref_type
- [x] New DB methods: `update_reference_type()`, `get_references_by_type()`
- [x] `_parse_ref_type()` — robust parser with alias support and normalization
- [x] `load_citation_profile()` — YAML profile loader
- [x] `classify_references()` — LLM-based batch classification with self-citation fast-path
- [x] `check_type_balance()` — compares actual distribution against profile targets
- [x] `format_balance_report()` — human-readable deviation report
- [x] Tests: 34 new tests covering profile loading, enum, DB operations, classification, and balance checking

### Phase 10.3 — CitationManager Refactoring (COMPLETE)
- [x] Footnote/endnote generation: `add_footnote()` with substantive content + "See ..." bibliographic clusters, `format_footnote_full()` (Chicago first-occurrence), `format_footnote_short()` (subsequent), `render_footnotes_section()` (Markdown)
- [x] Block quote formatting: `format_block_quote()` with multilingual original + italicized translation + translator note + style-aware attribution
- [x] "qtd. in" secondary citation: `format_secondary_citation()` — MLA ("qtd. in"), Chicago ("quoted in"), GB/T 7714 ("转引自")
- [x] Multilingual inline quotation: `format_inline_quote_multilingual()` — original in quotes, translation in parentheses per CL convention
- [x] Extended `format_citation()` with `page` override and `short_title` disambiguation parameters
- [x] Extended `verify_all_citations()` to detect MLA author-page format, "qtd. in" patterns, and deduplicate matches
- [x] `CitationManager` now stateful with `__init__()` for footnote tracking + `reset_footnotes()`
- [x] All 169 existing tests pass, no regressions

### Phase 10.4 — Writer Prompts & Critic Rewrite (COMPLETE)
- [x] `prompts/writing/argument_section.md` — added: quote vs paraphrase strategy by source type, quote length distribution (short phrase/sentence/block), introduction verb diversity list + framing patterns, multilingual quotation rules, footnote guidelines, new anti-patterns
- [x] `prompts/writing/introduction.md` — added: citation strategy section (density, verb diversity, paraphrase vs quote rules), footnote guidance, author positioning modes
- [x] `prompts/writing/conclusion.md` — added: explicit citation strategy section (minimal density, no new sources, primary text callback pattern)
- [x] `writer.py` `_build_system_prompt()` — now calls `_load_citation_norms()` to inject condensed citation profile norms from YAML into system prompt (quotation strategy, verbs, multilingual rules, footnote targets, section density norms, "qtd. in")
- [x] `writer.py` `_retrieve_reference_context()` — groups ChromaDB results by ref_type into PRIMARY/THEORY/SECONDARY/UNCLASSIFIED buckets with differentiated injection instructions per bucket
- [x] `writer.py` `_critic_evaluate()` — expanded from 3 to 5 scoring axes: added `citation_sophistication` (citation method diversity, verb variety, integration quality) and `quote_paraphrase_ratio` (balance by source type, quote length distribution)
- [x] `_parse_critic_response()` — handles 5 dimensions with backward-compatible defaults (new dimensions default to 3 when absent)
- [x] `reviewer.py` `_REVIEW_PROMPT` — added `citation_sophistication` and `quote_paraphrase_ratio` to score schema with detailed scoring rubric
- [x] `reviewer.py` `_META_PROMPT` — added new dimensions to meta-review consolidation schema
- [x] `reviewer.py` fallback defaults and `_fallback_synthesis()` — updated `score_keys` to include 7 dimensions
- [x] All 169 existing tests pass, no regressions

### Phase 10.5 — Integration Tests (COMPLETE)
- [x] `tests/test_citation_manager.py` — 83 new tests covering all Phase 10.3/10.4 features:
  - **TestFootnoteGeneration** (10): `add_footnote()` markers, content storage, "See ..." bibliographic clusters with refs, reset state, `render_footnotes_section()` Markdown format
  - **TestFootnoteFullFormat** (8): Chicago first-occurrence footnotes — single/multi author, journal vs book, page override, et al. for 4+, no-author fallback
  - **TestFootnoteShortFormat** (4): Subsequent-occurrence shortened footnotes — title truncation to 4 words, page override, Chinese author names
  - **TestBlockQuoteFormatting** (8): Block quotes across MLA/Chicago/GB styles, multilingual original+translation, translator notes, multiline, no-page fallback
  - **TestSecondaryCitation** (8): "qtd. in" (MLA), "quoted in" (Chicago), "转引自" (GB/T 7714) with/without pages, style fallback, ref.pages fallback
  - **TestMultilingualInlineQuotation** (4): Original-only, original+translation, translator notes
  - **TestExtendedFormatCitation** (6): Page override, short_title disambiguation, precedence over ref.pages
  - **TestExtendedVerifyCitations** (10): MLA author-page pattern, "qtd. in"/"quoted in"/"转引自" patterns, deduplication, mixed citation types, numeric brackets
  - **TestExtractSurname** (7): First-Last, Last-First, Chinese single-char, empty/whitespace
  - **TestParseCriticResponse** (7): 5 scoring dimensions, backward-compatible defaults, markdown fences, invalid JSON fallback
  - **TestReferenceTypeGrouping** (5): PRIMARY/SECONDARY/THEORY set membership, no overlap, UNCLASSIFIED exclusion
  - **TestBibliographyFormatting** (6): MLA/Chicago/GB journal articles, cached format bypass, DOI formatting
- [x] All 294 unit tests pass, 0 failures, no regressions (31 integration/LLM tests deselected)

## Phase 11 — Citation Verification Post-Processing (COMPLETE)
- [x] `src/citation_verifier/__init__.py` — package init
- [x] `src/citation_verifier/parser.py` — `ParsedCitation` dataclass + `parse_mla_citations()` with 5 pattern priority:
  1. Secondary: `(qtd. in Author, *Title* Page)` + Chicago `(quoted in Author Page)`
  2. Author + italic title + page: `(Derrida, *Sovereignties* 42)`
  3. Author + quoted title + page: `(Derrida, "Demeure" 78)`
  4. Simple author + page: `(Felstiner 247)` — excludes year-like 1800-2099
  5. Title-only italic: `(*Atemwende* 78)`
- [x] `group_citations()` — groups by author surname
- [x] `src/citation_verifier/engine.py` — `CitationVerificationEngine`:
  - CrossRef `query.bibliographic` search + OpenAlex fallback
  - `_is_title_match()` fuzzy matching (exact, substring, Jaccard >0.8)
  - `_extract_context_title()` — scans 500 chars before citation for title mentions
  - `_check_page_range()` — validates cited pages against article page ranges; marks book pages unverifiable
  - Result caching per author+title key to avoid duplicate API calls
  - Semaphore(5) concurrency limit for parallel verification
- [x] `src/citation_verifier/annotator.py`:
  - `annotate_manuscript()` — inserts `[VERIFY:work]`, `[VERIFY:page]`, `[VERIFY:page-range]` tags; processes end-to-start to preserve positions
  - `VerificationReport` — `summary()` one-liner + `to_markdown()` full report with issues/verified tables
- [x] `src/citation_verifier/pipeline.py` — `verify_manuscript_citations()` orchestrator: parse → verify → annotate → report
- [x] `run_demo.py` integration — verification step after Works Cited, `[VERIFY]` tags rendered as yellow-highlighted HTML spans
- [x] `cli.py` — `verify-citations` command with `--output` and `--report` flags
- [x] `tests/test_citation_verifier.py` — 64 tests:
  - **TestMLACitationParser** (16): all 5 patterns, Chinese authors, accented/hyphenated names, year exclusion, position correctness, sorting
  - **TestGroupCitations** (3): author grouping, secondary grouping, title-only grouping
  - **TestTitleMatch** (6): exact, case-insensitive, substring, word overlap, no match, empty
  - **TestNormalizeCrossref** (2): full article normalization, missing fields
  - **TestPageRangeValidation** (9): in-range, out-of-range, boundaries, book type, no range, cited range, unparseable
  - **TestExtractContextTitle** (2): title found before citation, no title found
  - **TestManuscriptAnnotation** (5): work/page/page-range tags, verified unchanged, multiple annotations
  - **TestVerificationReport** (5): all verified, mixed issues, markdown output, empty, counts
  - **TestEngineVerifyAll** (7): verified, not found, out of range, book page, cache, no author, no page
  - **TestEngineSearchMethods** (3): CrossRef search, OpenAlex search, fallback
  - **TestPipeline** (2): no citations, with citations
  - **TestEngineMatches** (4): title match, author surname, no match, partial title
- [x] All 364 unit tests pass, 0 failures, no regressions

## Phase 12 — Corpus Principal Missing Detection (COMPLETE)
- [x] `MissingPrimaryText` model in `models.py` — stores text_name, sections_needing, passages_needed, purpose
- [x] `PrimaryTextReport` model in `models.py` — total_unique, available, missing lists, `all_available` property, `summary()` method
- [x] `Database.search_papers_by_title(query, limit)` in `db.py` — case-insensitive `LIKE %query%` search
- [x] `_extract_title(text)` in `planner.py` — parses "Author, Title (Year)" patterns, strips quotes/italics/parens
- [x] `_jaccard_word_overlap(a, b)` in `planner.py` — word-level Jaccard similarity for fuzzy matching
- [x] `detect_missing_primary_texts(plan, db, vector_store)` in `planner.py`:
  - Collects unique `primary_texts` across outline sections with deduplication
  - Tier 1: SQLite LIKE search by extracted title, checks INDEXED/ANALYZED status
  - Tier 2: ChromaDB semantic search with Jaccard overlap validation (>0.5)
  - Aggregates sections_needing and passages_needed per missing text
- [x] CLI `plan` command — calls detection after plan creation, displays Rich table of missing works
- [x] CLI `wishlist` command — loads most recent plan, shows "Corpus Principal" section at top
- [x] `_display_primary_text_report()` helper in `cli.py` — Rich table with missing works, needed sections, passages, and next-step instructions
- [x] `WorkflowState.primary_text_report` field in `orchestrator.py`
- [x] `plan_node` in orchestrator — calls `detect_missing_primary_texts()` after plan creation, stores in state, logs warnings (non-blocking)
- [x] `tests/test_primary_text_detection.py` — 36 tests:
  - **TestExtractTitle** (12): author+title, year, quoted with collection, double-quoted, title-only, Chinese, asterisk italic, empty, whitespace, smart quotes, multiple commas
  - **TestJaccardWordOverlap** (5): identical, no overlap, partial, empty, case-insensitive
  - **TestPrimaryTextReport** (4): empty, all available, some missing, all missing
  - **TestMissingPrimaryText** (2): basic fields, defaults
  - **TestDetectMissingPrimaryTexts** (9): empty outline, no texts, all found via SQLite, missing not in DB, exists but not indexed, dedup across sections, mixed found/missing, purpose from argument, empty strings skipped
  - **TestSearchPapersByTitle** (4): substring match, case-insensitive, no match, limit
- [x] All 426 unit tests pass (36 new + 390 existing), 0 failures, no regressions

## Phase 13 — Pre-Plan Readiness Gate + Per-Section Reference Grounding (COMPLETE)
- [x] `OutlineSection.missing_references` field in `models.py` — backward-compatible `list[str]` default `[]`
- [x] `outline_generator.py` — prompt changes:
  - `PROBLEMATIQUE REQUIREMENT` block: each section's `argument` must be a specific, falsifiable claim naming authors/texts/concepts
  - LLM instructed to separate `secondary_sources` (from available refs) vs `missing_references` (needed but unavailable)
  - New `missing_references` JSON output field parsed in `_parse_outline()`
- [x] `_ground_references(sections, available_references)` in `outline_generator.py`:
  - Post-LLM cross-check: fuzzy-matches each `secondary_sources` entry against available references using `_jaccard_word_overlap()` (threshold 0.3)
  - Unmatched sources moved to `missing_references` with dedup
- [x] `planner.py` `refine_plan()` system prompt — added `missing_references` field and problématique requirement
- [x] `types.ts` — `missing_references?: string[]` added to `OutlineSection` interface
- [x] `ReadinessPanel.tsx` — new `onUpload` and `onRecheck` props:
  - When `status !== 'ready'`: renders `UploadZone` for PDF upload + "Re-check Readiness" button
- [x] `plan/page.tsx` — sufficiency gate:
  - Extracted `triggerReadinessCheck` callback (reused in `useEffect` + buttons)
  - `onUpload` triggers re-check after upload; `onRecheck` triggers re-check directly
  - When not ready: warning banner + two buttons ("Re-check Readiness" primary, "Create Plan Anyway" warning-styled)
  - When ready: normal "Create Plan" button
- [x] `PlanOutline.tsx` — per-section reference grounding display:
  - Argument prefixed with "Problématique:" label in accent color
  - Secondary sources labeled "(N available)"
  - Missing references shown with warning styling (amber text, ✗ icons)
- [x] All 469 unit tests pass, 0 failures, no regressions
- [x] TypeScript compiles cleanly (`npx tsc --noEmit`)

## Phase 14 — Discovery Refactor: Problématique Ontology (COMPLETE)

Replaced STORM 4-perspective gap analysis with structured P-ontology annotation pipeline.

### New Discovery Flow
```
Journal papers (with abstracts)
    ↓
Per-paper LLM annotation: P = ⟨T, M, S, G⟩
    ↓
Cluster annotations → 3-8 Problématique Directions
    ↓
Per-direction → 10 concrete research topics
    ↓
Frontend: two-level display (directions → topics)
    ↓
User selects topic → proceeds to References
```

### Data Models
- [x] `AnnotationScale` enum (5 values: textual, perceptual, mediational, institutional, methodological)
- [x] `AnnotationGap` enum (5 values: mediational_gap, temporal_flattening, method_naturalization, scale_mismatch, incommensurability_blindspot)
- [x] `PaperAnnotation` model — P = ⟨T, M, S, G⟩ with tensions, mediators, scale, gap, evidence, deobjectification
- [x] `ProblematiqueDirection` model — clustered direction with dominant T/M/S/G, paper_ids, topic_ids
- [x] `TopicProposal.direction_id` — links topics to their parent direction

### Database
- [x] `paper_annotations` table (UNIQUE on paper_id, indexed)
- [x] `problematique_directions` table
- [x] Migration: `direction_id` column on `topic_proposals`
- [x] 10 new DB methods: `insert_annotation`, `get_annotation`, `get_annotations`, `get_unannotated_papers`, `count_annotations`, `insert_direction`, `get_directions`, `get_direction`, `get_topics_by_direction`
- [x] Row converters: `_row_to_annotation()`, `_row_to_direction()`
- [x] Updated `insert_topic()` and `_row_to_topic()` for `direction_id`

### Backend Pipeline (full rewrites)
- [x] `gap_analyzer.py` — **replaced STORM multi-perspective** with 6-step P-ontology annotation prompt:
  1. De-objectification, 2. Tensions (A ↔ B), 3. Mediators, 4. Scale (5 fixed), 5. Gap (5 fixed), 6. Evidence
  - `annotate_paper()` — single paper annotation via LLM
  - `annotate_corpus()` — batch annotation, skips existing, stores to DB
- [x] `trend_tracker.py` — **replaced trend tracking** with direction clustering:
  - `cluster_into_directions()` — LLM synthesizes annotations into 3-8 directions with shared T/M/S/G patterns
  - Maps paper_indices to paper_ids
- [x] `topic_scorer.py` — **replaced scoring** with topic generation:
  - `generate_topics_for_direction()` — LLM proposes 10 concrete topics per direction
  - Scores set to 0.0 (no separate scoring pass)

### Orchestrator
- [x] `WorkflowState.directions: list[dict]` field added
- [x] `discover_node` rewritten: annotate_corpus → cluster_into_directions → generate_topics_for_direction (per direction)

### API Endpoints (rewrite)
- [x] `POST /discover` — background task: annotate → cluster → generate topics (progress: 0.1→0.6 annotating, 0.7 clustering, 0.8-0.95 generating)
- [x] `GET /discover/status` — annotation/direction/topic counts
- [x] `GET /directions` — list all directions
- [x] `GET /directions/{id}` — single direction with its topics
- [x] `GET /topics` — updated with optional `direction_id` query param

### CLI
- [x] `discover` command rewritten: `--annotate-only` flag, displays Rich table of directions (title, tensions, paper count, topic count)

### Frontend
- [x] `types.ts` — added `PaperAnnotation`, `ProblematiqueDirection`, `DirectionWithTopics`, `AnnotationStatus` interfaces; `direction_id` on `Topic`
- [x] `api.ts` — `startDiscovery` (limit=200), `getAnnotationStatus`, `getDirections`, `getDirectionWithTopics`, `getTopics` with `directionId`
- [x] `store.ts` — `selectedDirectionId` state + `selectDirection` action
- [x] `TopicCard.tsx` — simplified: removed `ScoreBadge` and 4-score display
- [x] `DirectionCard.tsx` — **new component**: collapsible card with P-ontology badges (tensions=blue, mediators=purple, scale=green, gap=amber), expands to show TopicCards
- [x] `discover/page.tsx` — **rewritten**: annotation status bar, two-level hierarchy (DirectionCards → TopicCards), loads directions on mount

### Tests
- [x] `tests/test_problematique.py` — 41 new tests:
  - **TestAnnotationScaleEnum** (2): all values, from_string
  - **TestAnnotationGapEnum** (1): all values
  - **TestPaperAnnotationModel** (2): defaults, full construction
  - **TestProblematiqueDirectionModel** (2): defaults, full construction
  - **TestTopicProposalDirectionId** (2): default None, set value
  - **TestDBAnnotations** (6): insert/get, not found, list, count, unannotated, insert-or-replace
  - **TestDBDirections** (3): insert/get, not found, list
  - **TestDBTopicWithDirection** (2): insert with direction_id, get_topics_by_direction
  - **TestAnnotatePaper** (4): valid JSON, empty abstract, invalid enum fallback, LLM failure
  - **TestAnnotateCorpus** (2): batch annotation, skip already-annotated
  - **TestClusterIntoDirections** (4): valid clustering, paper_indices mapping, empty annotations, out-of-range indices
  - **TestGenerateTopics** (3): 10 topics generated, direction_id set, LLM failure
  - **TestRowConverters** (2): annotation, direction
  - **TestParseAnnotation** (6): valid JSON, invalid scale/gap fallback, no JSON, markdown fences, non-list fallback
- [x] `tests/test_llm_pipeline.py` — `test_stage_discover()` updated: tests annotation → clustering → topic generation
- [x] All 515 unit tests pass (41 new + 474 existing), 0 regressions
- [x] TypeScript compiles cleanly (`npx tsc --noEmit`)

## Phase 9 — End-to-End LLM Pipeline Tests (COMPLETE)
- [x] `pyproject.toml` — added `llm_pipeline` pytest marker
- [x] `tests/test_llm_pipeline.py` — 5 test functions exercising real LLM calls:
  - `test_stage_discover()` — P-ontology annotation + direction clustering + topic generation (N+2 LLM calls)
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
- `tests/test_writer.py` — 26 unit tests (language detection, chunking, citations, word count, revise_manuscript, format_review_feedback)
- `tests/test_reference_acquisition.py` — 20 unit tests + 3 integration tests (OA extraction, dedup, DB, web searcher)
- `tests/test_oa_resolver.py` — 40 unit tests + 3 integration tests (Unpaywall, CORE, arXiv, Europe PMC, priority order, batch, fallback)
- `tests/test_integration_apis.py` — 14 integration tests (real API calls)
- `tests/test_proxy_session.py` — 25 unit tests (config, domain matching, URL rewriting, login, download, pipeline integration)
- `tests/test_e2e.py` — 6 end-to-end tests (full workflow)
- `tests/test_llm_pipeline.py` — 5 LLM pipeline tests (real API calls, skipped without key)
- `tests/test_citation_profile.py` — 34 tests (profile loading, ReferenceType enum, DB ref_type ops, LLM classification, type balance checking)
- `tests/test_citation_phase10.py` — 54 tests (Phase 10 citation features: secondary citations, footnotes, block quotes, multilingual, type classification, profile loading)
- `tests/test_citation_manager.py` — 83 tests (Phase 10.5: footnotes, block quotes, secondary citation, multilingual inline, extended format_citation, verify_all_citations, critic parsing, type grouping, bibliography formatting)
- `tests/test_citation_verifier.py` — 64 tests (Phase 11: MLA parser, page range validation, annotation, report, engine verify, search methods, pipeline)
- `tests/test_primary_text_detection.py` — 36 tests (Phase 12: title extraction, Jaccard overlap, models, detection with mocked DB/VS, DB title search)
- `tests/test_problematique.py` — 41 tests (Phase 14: P-ontology enums, models, DB annotations/directions/topics, annotation pipeline, clustering, generation, row converters, parse helpers)
- **Total: 510 unit tests + 5 LLM pipeline tests, all passing (LLM tests skip without ZHIPUAI_API_KEY)**

## Key Decisions
- LiteLLM as unified LLM gateway (see decisions.md #001)
- ChromaDB for vector store (see decisions.md #002)
- GLM embedding-3 API for embeddings (see decisions.md #003)
- LangGraph for orchestration (see decisions.md #004)
- Human-in-the-loop for PDF acquisition (most publishers block direct download)
- Multi-source OA resolution before human fallback (Unpaywall → CORE → arXiv → Europe PMC → DOI negotiation)
- Institutional proxy as fallback after OA resolution, before human wishlist
- **P-ontology annotation** replaces STORM multi-perspective for discovery (structured P = ⟨T, M, S, G⟩ per paper → direction clustering → topic generation)

## CLI Commands Available
- `ai-researcher monitor` - Scan journals for new papers
- `ai-researcher index <pdf>` - Index a PDF into knowledge base
- `ai-researcher **index-folder** <dir>` - Batch-index all PDFs in a folder
- `ai-researcher **search-references** <topic>` - Search APIs + generate PDF wishlist
- `ai-researcher **search-books** <queries...>` - Search Google Books + Open Library
- `ai-researcher **resolve-oa** [--limit N] [--dry-run]` - Resolve OA URLs for papers missing PDFs
- `ai-researcher **config-proxy**` - Configure institutional proxy (one-time setup)
- `ai-researcher **proxy-download** [--limit N] [--dry-run]` - Download paywalled PDFs via proxy
- `ai-researcher **wishlist**` - Show papers still needing PDFs + corpus principal report
- `ai-researcher discover [--annotate-only] [--limit N]` - P-ontology annotation + direction clustering + topic generation
- `ai-researcher plan <topic_id> --journal <name>` - Create research plan + detect missing primary texts
- `ai-researcher write <plan_id>` - Generate manuscript
- `ai-researcher verify <ms_id>` - Verify references
- `ai-researcher **verify-citations** <manuscript.md> [-o output] [-r report]` - Verify inline citations against CrossRef/OpenAlex + insert [VERIFY] tags
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

## Discovery Flow (P-ontology)
```
Papers (with abstracts) → Per-paper LLM annotation P = ⟨T, M, S, G⟩
    ↓
Annotations stored in paper_annotations table (skips already-annotated)
    ↓
LLM clusters annotations → 3-8 ProblematiqueDirection objects
    ↓
Per direction → LLM generates 10 TopicProposal objects (direction_id set)
    ↓
Frontend: DirectionCard (collapsible, P-badges) → TopicCard list
    ↓
User selects topic → proceeds to References
```
- `--annotate-only` flag: only run annotation step, skip clustering/generation
- Annotations are cached per paper_id (idempotent re-runs)
- API endpoint `GET /discover/status` shows annotation/direction/topic counts

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
