# Roadmap

The full roadmap (Turkish) lives in the project's planning document. Summary:

| Stage | Duration | Delivers |
|---|---|---|
| **0. Setup** | 1 week | repo skeleton, CI, data inventory, golden dataset v0, ADR-0001 |
| **1. MVP** | 3–4 weeks | ingestion pipeline, hybrid search + reranker, SQL tool, cited answers, evaluation vs v1, live URL |
| **2. Production quality** | 2–3 weeks | guardrails, red-team tests, CI/CD with eval gate, tracing and cost monitoring |
| **3. Scale and enterprise** | 2–3 weeks | multi-tenancy, RBAC, caching, load tests, MCP server, admin panel and feedback loop |
| **4. Pilot and portfolio** | 1 week + ongoing | department pilot, technical report, demo |

## Stage 0 checklist

- [x] Repository skeleton, config, logging, health checks
- [x] Docker Compose (Postgres + pgvector, Redis, API)
- [x] CI: lint, types, tests, integration tests, secret and dependency scan, Docker build
- [x] Golden dataset schema and validator
- [x] ADR-0001
- [x] Data inventory first draft (`docs/data-inventory.md`); content review of remaining files pending
- [ ] Golden dataset v0: 50 items in `evals/datasets/dev.jsonl`
- [ ] Accounts and API keys (provider spending limits set)

## Principles

1. Every technique solves a measured problem: measure before and after, report the difference.
2. Every significant decision gets an ADR.
3. Providers sit behind interfaces; swapping one is a config change.
4. Evaluation is code: versioned datasets, run in CI.
5. Safe defaults: no answer without a source, no secrets in code, no personal data in logs.
