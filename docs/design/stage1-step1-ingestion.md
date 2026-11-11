# Stage 1, step 1: ingestion design note

Status: implemented in this step; chunking rationale and measurements are in ADR-0002.

## Goal

Turn the source files in `v1-kaynaklar` into a clean, versioned, idempotent corpus: a `documents`
registry and a `chunks` table, plus a report that shows what was ingested and what looks wrong.
Retrieval (embeddings, BM25, reranking) is out of scope here and arrives in steps 3 and 4.

## What the real files look like (inspected 2026-11-11)

| Source | Finding that shapes the design |
|---|---|
| Course packages (TXT, ~82) | Each web page was printed to text twice: a pipe-table copy and a flat copy. Page stamps (`30.11.2025 16:27 Eğitim Bilgi Sistemi`), `1/3` page markers, `ebs.sakarya.edu.tr` footers and private-use icon glyphs are mixed in. The academic year `(2025 - 2026)` only appears in the flat copy's title line. |
| Regulation-style PDFs | Not formal "Madde" regulations. FAQ (`•question` + answer), numbered committee decisions (`1.` ... `6.`), short narrative pages and a step-by-step procedure (`1-`, `ADIM 3`, `8.1.2-`). Each is 1 to 6 pages. |
| Slide decks (PDF) | One slide per page, 80 to 700 characters each, some pages carry only images. `StajBilgilendirmeSunumu1.pdf` (2013-14) has a broken font encoding (`Ġ`, `ġ`, `Ģ` instead of `İ`, `Ş`, `ş`). |
| `StajBilgilendirme.txt` | A dates table and two announcements in one file. The Drive preview shows markdown escapes (`\>`, `\*\*`); they are stripped defensively in case the raw file has them. |
| PDF extraction | `pypdf` default mode inserts spaces inside words (`y apabilirler`, `C umartesi`); `pdfplumber`, `pdftotext` and `pypdf` layout mode do not (measured on the interim-internship PDF). |
| CSV | UTF-8 with BOM, `;` delimiter, a `Metin` column that is the v1 linearised sentence, trailing empty rows, empty course codes on elective slots. |

## Pipeline

```
manifest (config/sources.toml)  ->  discover files  ->  load  ->  clean  ->  chunk  ->  checks
                                                                              |
                                                                  upsert (idempotent)  +  report
```

- **Manifest first.** A file is ingested only if `config/sources.toml` lists it (or a pattern rule matches).
  Each entry sets `kind`, `academic_year`, `status`, `access`, and may mark a file `skip` with a reason.
  Unregistered files are reported, never silently ingested. This is what keeps `MezuniyetKosulları.txt`,
  the `.txt` twins of PDFs and the old "LLM Verileri" folder out of the corpus.
- **Pure core, thin edges.** Loading, cleaning, chunking and checks are plain functions over text with no
  database or framework import. The store sits behind a `DocumentStore` protocol, so the pipeline is
  testable with an in-memory fake and the real store is tested against Postgres.
- **Per-kind cleaning and chunking** (course package, FAQ, numbered items, narrative, slides). Every chunk
  carries a context header (document title, year, section) stored separately from its body.
- **CSV files** are registered in `documents` with `target = sql` and get no chunks: structured facts
  come from SQL (step 2). The loader still parses them so the report can check them.

## Data model (Alembic migration 0001)

`documents`: `source_name` (unique), `title`, `source_type`, `source_kind`, `target`, `academic_year`,
`valid_from`, `valid_until`, `status` (`current` | `superseded`), `access`, `content_hash` (sha256 of raw bytes),
`pipeline_version`, `is_active`, `metadata` (JSONB), timestamps.
`chunks`: `document_id`, `ordinal`, `section`, `header`, `content`, `content_hash`, `char_count`,
`token_estimate`, `page_start`, `page_end`, `metadata` (JSONB); unique `(document_id, ordinal)`.

Left out on purpose: the embedding column (depends on the model chosen in ADR-0004) and the full-text
search column (step 4).

## Idempotency

Re-running on unchanged input writes nothing. A changed file (new `content_hash`) or a new
`PIPELINE_VERSION` replaces that document's chunks inside one transaction. A document that is no longer in the
source set is marked `is_active = false` (kept for audit, excluded from retrieval); `--prune` deletes it.

## Report

Per file: kind, year, status, characters before and after cleaning, duplicate characters removed, chunk
count and size distribution, findings. Findings have a severity (`error`, `warning`, `info`) and a code, for
example `empty_text`, `garbled_text`, `unparsed_course_package`, `duplicate_chunk`,
`image_heavy_page`, `mentions_other_academic_year`, `ects_workload_mismatch`. The run also lists unregistered, skipped and deactivated files. `--dry-run` produces the
report without a database.

## Not in this step

Embeddings, search, SQL tables for CSVs, golden-set upload to Hugging Face. Retrieval-level evidence for the
chunking choice is collected in step 3 (see ADR-0002, "Follow-up").
