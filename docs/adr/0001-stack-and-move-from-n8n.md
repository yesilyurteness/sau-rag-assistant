# ADR-0001: Rebuild in Python (FastAPI + LangChain) instead of extending the n8n prototype

- **Status:** accepted
- **Date:** 2026-11-09

## Context

v1 was built as two n8n workflows (ingestion and chat) with Gemini 2.5 Flash, Gemini
`text-embedding-004` and Supabase pgvector. Evaluation on 15 questions:

- BERTScore F1 0.6475; 4/15 questions failed because relevant content was not retrieved.
- At least 2 answers contained wrong facts, mostly from table data (curriculum, ECTS) that had
  been linearized into sentences and searched by embedding similarity.
- Mean latency 6.12 s without streaming.

The improvements v2 needs (structure-aware chunking, hybrid search, reranking, a SQL tool for
structured data, an evaluation gate in CI, guardrails, tracing) need fine-grained control
over each retrieval step and automated tests. n8n gives fast prototyping but makes unit
testing, versioned evaluation and code review of the pipeline hard.

## Options considered

| Option | Pros | Cons |
|---|---|---|
| Extend n8n | v1 already works; fast visual iteration | hard to unit test and version; limited control over retrieval internals; weak fit for CI eval gates |
| Python, no framework | full control, fewest dependencies | more boilerplate for loaders, splitters, provider clients |
| **Python + FastAPI + LangChain (thin)** | full control where it matters; reuse LangChain integrations for loaders and providers; standard deployable API | framework churn; must keep core logic independent of it |
| LlamaIndex | strong RAG abstractions | higher-level abstractions hide the steps this project needs to measure |

## Decision

Python 3.12, FastAPI, Pydantic v2 and pydantic-settings, with LangChain used as a thin
integration layer. Retrieval, routing and guardrail logic live in our own modules behind
interfaces so providers and frameworks can be swapped. PostgreSQL 16 with pgvector is the
default store (relational data, vectors and full-text search in one system); Pinecone will be
evaluated behind the same interface (ADR-0003). Redis for cache and rate limiting.
uv for dependency management, Docker Compose for local and first deployment.

## Consequences

- Every retrieval change can be unit tested and evaluated in CI before merge.
- More code to own than in n8n; mitigated by a strict layout, type checking and tests.
- The v1 n8n workflows are kept as the baseline; v1 will be re-scored on the new golden
  dataset so the comparison uses the same metrics.
