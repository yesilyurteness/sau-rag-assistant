# ADR-0002: Structure-aware parsing and chunking per source kind

- **Status:** accepted (structural evidence); to be confirmed with retrieval metrics in step 3
- **Date:** 2026-11-11

## Context

Four of the fifteen v1 test questions failed at retrieval, and in all four the answer was in the
sources (ADR-0001). v1 linearised everything and split it into fixed character windows. Inspecting the
real files for this step showed why that hurts:

- **Course packages** (~82 TXT files) contain every EBS page twice: a pipe-table copy and a flat copy,
  plus page stamps, `1/3` markers, URL footers and private-use icon glyphs. Fixed windows index both
  copies (near-duplicate chunks) and cut tables mid-row.
- **The "regulation" PDFs are not formal regulations.** They are an FAQ (`•question` + answer), numbered
  committee decisions, a numbered application procedure (`1-`, `ADIM 3`, `8.1.2-`) and short narrative
  pages, each 1 to 6 pages long.
- **Slide decks** carry 80 to 700 characters per slide; one (2013-14) has a broken font encoding
  (`Ġ`, `ġ`, `Ģ` instead of `İ`, `Ş`, `ş`).
- **Rules carry conditions**: "Cumartesi iş günü sayılır" is only true "firma Cumartesi çalışıyorsa ve
  belgelenirse". A window boundary between the rule and its condition produces a wrong answer, which is
  the failure mode the project most wants to avoid.

PDF text extraction was measured first because it feeds every chunker. On the interim-internship PDF,
`pypdf` (default mode) inserted spaces inside 8 words (`y apabilirler`, `C umartesi`, `belge lemek`);
`pdfplumber`, `pdftotext` and `pypdf` layout mode produced none. All three extracted the same Turkish
letters on all seven PDFs.

## Options considered

| Option | Pros | Cons |
|---|---|---|
| Fixed windows (v1: ~1000 characters, overlap) | trivial, source-agnostic | splits rules from conditions, indexes duplicate print copies, chunks carry no document or year |
| Recursive splitter (paragraph, sentence, word) | better boundaries, available in LangChain | still blind to FAQ/decision/table structure and to the duplicate copies |
| Semantic chunking (embedding similarity breakpoints) | adapts to topic shifts | needs an embedding model before the model is chosen (ADR-0004), non-deterministic across model changes, no help with tables |
| **Structure-aware per source kind** | units match how the sources are written; deterministic; easy to test | more code; a new layout needs a new parser |

## Decision

Structure-aware chunking, selected by the `kind` declared for each file in `config/sources.toml`:

| Kind | Unit | Notes |
|---|---|---|
| `course_package` | one section per chunk: course card, instructors, aim and content, learning outcomes, weekly plan (week ranges), resources, assessment and ECTS workload, program-outcome contributions | the flat print copy is dropped after reading the academic year and EBS id from it; the ECTS value and `workload / 25` stay in one chunk so the "6,08 vs 5" conflict is answerable |
| `faq` | one question with its full answer | the question is repeated if a long answer is split |
| `decisions` | one numbered decision | preamble kept as its own chunk |
| `procedure` | consecutive steps packed up to the size limit | section label names the first and last step |
| `narrative`, `announcement` | heading plus its paragraphs | date-table rows are kept on their own lines and together |
| `slides` | consecutive whole slides packed up to the size limit | slide numbers stripped, `Slayt N:` prefix kept |
| `tabular` (CSV) | no chunks | structured facts come from SQL (step 2, ADR-0003) |

Common rules: a 1,200-character limit (about 360 tokens), a 120-character minimum below which a chunk is
merged into its neighbour, and a context header stored separately from the body
(`document title | academic year | section`) that is embedded and shown with the chunk. PDF text comes
from `pdfplumber`. Sizes are counted in characters so the core has no tokenizer dependency.

## Measurements

`scripts/compare_chunking.py` on the seven real PDFs plus three TXT files reconstructed from the Drive
preview (`Bitirme Calismasi.txt`, `StajBilgilendirme.txt`, `BolumTanitimi.txt`):

| Metric | Fixed 1000/200 (v1-style) | Structure-aware (v2) |
|---|---|---|
| FAQ answers, decisions and steps kept whole in one chunk | 72% (18/25) | 96% (24/25) |
| Chunks that name their document and academic year | 4% (2/57) | 100% (58/58) |
| Chunks | 57 | 58 |
| Median chunk characters | 995 | 657 |
| Course-package characters that are duplicate print copies | 12% in the sample | 0% (removed) |

The one unit v2 splits is the last procedure step, which runs to the end of the document and exceeds the
size limit. The duplicate share is understated: the reconstructed course file has a shortened flat copy,
while the real files carry a full one. The owner's full run reports the real figure per file
(`Duplicate removed` column).

## Consequences

- Each chunk can be cited with document, section, page range and academic year, which Stage 1 requires.
- Superseded sources (2013-14 and 2023 slide decks) stay retrievable for conflict questions but carry
  `status = superseded` for ranking.
- A course package that does not match the expected layout is rejected with an error in the report
  instead of being indexed as noise; new layouts need parser work.
- **Follow-up (step 3):** these are structural metrics. Once the eval runner exists, compare Recall@5 and
  MRR on `dev.jsonl` for (a) this strategy, (b) the same strategy without context headers, and (c) fixed
  windows on cleaned text, and revisit the 1,200-character limit. This ADR is updated with those numbers.
