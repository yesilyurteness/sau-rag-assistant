# Golden evaluation dataset

One JSON object per line. Schema: [`evals/schema.py`](../schema.py).
Validate with `make validate-evals` (also runs in CI).

## Splits

| File | Used for | Rule |
|---|---|---|
| `dev.jsonl` | tuning prompts, chunking, retrieval parameters | use freely |
| `test.jsonl` | release reports only | never look at results while tuning |

The validator fails if the same question appears in both splits.

## Writing items

- Questions in the way students actually ask them, including typos and informal phrasing.
- `reference_answer`: the short, correct fact, written from the source, not from memory.
- `source_documents` / `source_sections`: where the answer is; needed to score retrieval.
- Include `refuse` cases (out of scope, unknown facts) and `adversarial` cases.
- Multi-turn cases put earlier turns in `history`; `question` is the last user message.

The five items in `dev.jsonl` are format examples (tagged `example`); verify their sources
before counting them. Target for Stage 1: 150–200 items across all categories.
