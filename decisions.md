# Architecture Decision Records

## ADR-001: LiteLLM as Unified LLM Gateway
**Date**: 2026-02-14
**Decision**: Use LiteLLM as a single interface to route requests to multiple LLM providers.
**Rationale**: Supports 100+ providers with a unified API. Task-based routing allows choosing optimal models per task type (e.g., GLM for Chinese writing, Claude for close reading). Built-in fallback, cost tracking, and token counting.

## ADR-002: ChromaDB for Vector Storage
**Date**: 2026-02-14
**Decision**: Use ChromaDB for embedding storage and semantic search.
**Rationale**: Lightweight, local-first, good Python API. Sufficient for the scale of academic papers (~10K documents). No external infrastructure needed.

## ADR-003: GLM embedding-3 API for Embeddings
**Date**: 2026-02-14 (updated)
**Decision**: Use ZhipuAI GLM `embedding-3` API for generating embeddings. Replaces the previous `intfloat/multilingual-e5-large` local model.
**Rationale**: The local sentence-transformers approach required ~9GB of disk (torch + nvidia CUDA + model weights), which is impractical for the 60GB dev environment. GLM embedding-3 provides comparable multilingual quality (Chinese, English, French) with zero disk footprint. 1024-dim output maintains compatibility. Cost is negligible (~0.5 CNY per million tokens).

## ADR-004: LangGraph for Orchestration
**Date**: 2026-02-14
**Decision**: Use LangGraph StateGraph for workflow orchestration.
**Rationale**: Supports stateful multi-step workflows with checkpointing, human-in-the-loop gates, and conditional branching. Good fit for the complex multi-agent pipeline.
