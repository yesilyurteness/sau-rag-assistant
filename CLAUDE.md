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

## How we work with the owner

The owner wants to understand every change before the next one starts. Therefore:

- Work in small steps. One step is one idea that fits in a short explanation (for example "add the
  PDF loader", not "build the ingestion pipeline"). Split large plan steps into sub-steps first and
  show the split before coding.
- After each step stop and explain in plain language: what was done, why, how it works (name the
  files), what was tested and the result. Then wait for explicit approval before the next step.
- Do not start a following step, and do not push more than one step of work, without that approval.
- Prefer one commit per step so the history matches the explanations.
- If a step turns out larger than expected, stop and re-split instead of continuing.

## Git

- Start every session with `git pull --rebase origin main`; push with `git push origin main`.
  Never use `--force`. If `main` is protected, open a branch and a PR.
- Add files by name; never `git add .` or `git add -A`. Check `git status --short` and
  `git diff --staged` for secrets before committing. `.env` is never committed.
- The owner works in one local folder and pulls from GitHub. Before asking the owner to run
  commands or before any git step on their side, remind them to run `git pull --rebase origin main`.

