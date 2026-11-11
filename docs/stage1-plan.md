# Stage 1 plan: working MVP with a live URL

Status: approved 2026-11-11. Time box: 3-4 weeks. Step 1 (ingestion) implemented, see
`docs/design/stage1-step1-ingestion.md` and ADR-0002.

## Exit criteria

1. A public URL where a student can ask a question and get a cited answer.
2. A reproducible eval report on `dev.jsonl` showing retrieval metrics (Recall@5, MRR), behavior accuracy
   (answer / refuse / clarify) and answer correctness, compared with the v1 baseline.
3. One `test.jsonl` report at the end of the stage, never used for tuning.
4. Every technique added has a before/after number and, when it is a real choice, an ADR.

## Principles for this stage

- Measure first: the eval runner exists before retrieval is tuned.
- The v1 failures were retrieval failures, so retrieval gets the most time.
- Structured facts (ECTS, staff, calendar) come from SQL, not from vector search.
- "No source, no answer": refusing is a correct outcome, not a failure.
- All answers carry the source document, section and academic year (2025-2026 snapshot).

## Steps

| # | Step | Deliverable | Measured by | ADR |
|---|---|---|---|---|
| 1 | Ingestion | Loaders for TXT, PDF and CSV; text cleanup; document registry with `academic_year`, `status` (current / superseded) and content hash; idempotent re-ingest; `documents` and `chunks` tables | Ingestion report: files, chunks per file, empty or garbled text checks | 0002 chunking |
| 2 | Structured data | SQL tables for courses, curriculum rows, prerequisites (mapped to course codes), staff, commissions, calendar, student counts; parameterized query functions exposed as tools; read-only database role | Unit tests against the real CSVs; dev items of type curriculum, staff and calendar answerable from SQL | 0003 structured access |
| 3 | Eval runner + dense baseline | Runner with cache and retry/backoff; retrieval metrics; embeddings behind an interface; pgvector search with metadata filters | Recall@5 and MRR on dev items that have `source_documents` | 0004 embedding model |
| 4 | Hybrid search + reranker | BM25 (Postgres full-text, Turkish config) + dense with RRF; reranker behind an interface (local `bge-reranker-v2-m3` default, Cohere optional); query rewriting for multi-turn | Recall@5 / MRR before and after each addition; latency | 0005 retrieval and reranker |
| 5 | Generation | Intent router (SQL tool, RAG, clarify, refuse); Turkish grounded prompt; citations; relevance threshold so weak retrieval leads to a refusal; LLM provider interface (Gemini first) | Behavior accuracy, answer correctness (LLM judge), citation correctness | 0006 orchestration |
| 6 | API and UI | `POST /chat` in FastAPI, Streamlit test UI, PII-free request logging, Langfuse traces of synthetic eval runs only, basic rate limit | API tests; manual check of the 10 hardest dev questions | n/a |
| 7 | Deployment | Container deployment, public URL, README with the 2025-2026 snapshot notice and a "do not enter personal data" warning | Smoke test against the live URL; final `test.jsonl` report | 0007 hosting |

Order matters: the eval runner (3) comes before any tuning (4, 5) so each later change is measured.

## Design decisions already taken

- Provider-agnostic interfaces for LLM, embeddings and reranker; the default reranker is local because
  the Cohere trial key allows 1,000 calls per month and cannot be used in production.
- LangChain stays at the edges; the core (chunking, retrieval, routing, eval) is framework-independent.
- Documents carry `status`: `StajBilgilendirmeSunumu1.pdf` (2013-14) stays in the corpus as `superseded`
  so the Saturday-rule conflict item is a real test, but retrieval must prefer current documents.
- `MezuniyetKosulları.txt` is excluded from the corpus (wrong internship duration).
- Gemini free tier may use submitted data: only synthetic eval questions go through it until a paid tier is used.
  The live demo carries a warning not to enter personal data.

## Risks

| Risk | Mitigation |
|---|---|
| Gemini free-tier rate limits slow the eval runs | Response cache, retry/backoff, small smoke subset for quick iterations |
| Turkish tokenization hurts BM25 | Compare Postgres Turkish config with trigram search; measure before choosing |
| Dirty source text (course package layout, broken encodings) | Ingestion report with checks; clean per source type, not globally |
| Chunk boundaries split a rule from its condition | Article/section-aware chunking with a header (document, section, year) on every chunk |
| Time-sensitive facts become stale | Answers state the source year; `snapshot-sensitive` items are re-verified if data changes |

## Needed from the owner

1. Approval of this plan and of excluding `MezuniyetKosulları.txt`.
2. Before step 7: a hosting choice and monthly budget (free options exist, with limits).
3. After step 1: a short review of the ingestion report, especially the course packages.

## Working agreement and checkpoints

Each step above is delivered in sub-steps. After every sub-step the work stops, is explained in plain
language (what, why, how, test result) and waits for the owner's approval; see `CLAUDE.md`.

Step 1 sub-steps:

| Sub-step | Scope |
|---|---|
| 1a | Loaders for TXT, PDF and CSV, text cleanup, unit tests |
| 1b | Database schema (`documents`, `chunks`, academic year, `status`) and migration |
| 1c | Chunking strategy and ADR-0002 |
| 1d | Idempotent ingestion command and the ingestion report |

The sub-steps of steps 2-7 are written and shown to the owner before each of those steps starts.

