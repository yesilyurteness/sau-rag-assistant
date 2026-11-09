# Project conventions

RAG assistant for Sakarya University Industrial Engineering students. Owner: Mustafa Enes
Yeşilyurt. Roadmap: `docs/roadmap.md`. Decisions: `docs/adr/`.

## Working rules

- Run `make check` before committing; it must pass (ruff, mypy strict, unit tests, dataset validation).
- Code, comments, docs and commit messages in English. Data, prompts and test questions in Turkish.
- New behaviour comes with tests. Retrieval/generation changes come with an eval comparison.
- Significant decisions (model, store, chunking, framework) get an ADR from `docs/adr/0000-template.md`.
- Never read `os.environ` directly; add a field to `app.core.config.Settings`.
- Secrets are `SecretStr`; never log them. Never commit `.env` or raw source documents.
- Keep core logic framework-independent; LangChain stays at the edges.
- `evals/datasets/test.jsonl` is never used for tuning.
