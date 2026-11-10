# Golden evaluation dataset

One JSON object per line. Schema: [`evals/schema.py`](../schema.py).
Validate with `make validate-evals` (also runs in CI).

## Splits

| File | Used for | Rule |
|---|---|---|
| `dev.jsonl` | tuning prompts, chunking, retrieval parameters | use freely |
| `test.jsonl` | release reports only | never look at results while tuning |

The validator fails if the same question appears in both splits, or if items that share a
`group` (same underlying fact, for example paraphrases) end up in different splits.

## Writing items

- Questions in the way students actually ask them, including typos and informal phrasing.
- `reference_answer`: the short, correct fact, written from the source, not from memory.
- `source_documents` / `source_sections`: where the answer is; needed to score retrieval.
- Include `refuse` cases (out of scope, unknown facts) and `adversarial` cases.
- Multi-turn cases put earlier turns in `history`; `question` is the last user message.

The 52 items (37 dev, 15 test) come from the first hand-verified question set: every
reference answer was checked against the 2025-2026 source files by the project owner.
Items tagged `snapshot-sensitive` (dates, counts, office holders) must be re-verified if the
source data is replaced. Target for Stage 1: 150–200 items across all categories.
