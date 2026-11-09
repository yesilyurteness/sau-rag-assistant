# Data inventory

Every source the assistant may answer from. Fill one row per source during Stage 0.
This table drives the ingestion design: structured sources go to SQL tables, unstructured
ones to the vector index, and the access level becomes a retrieval filter.

| # | Source | Type | URL / location | Update frequency | Structured? | Target | Access level | Owner | Status |
|---|---|---|---|---|---|---|---|---|---|
| 1 | Example: Staj Yönergesi | PDF | bölüm sitesi / Drive | yearly | no | vector | public | Staj Komisyonu | to collect |
| 2 | Example: Ders planı | Excel | Drive | per semester | yes | SQL `courses` | public | Bölüm | to collect |
| 3 | Example: Akademik kadro ve iletişim | web page | bölüm sitesi | per semester | yes | SQL `staff` | public | Bölüm | to collect |

**Column guide**

- **Type:** PDF, Excel/CSV, web page, TXT, announcement.
- **Structured?:** yes if the content is naturally rows and columns (courses, ECTS, staff,
  committees, calendar dates). These are answered with exact SQL lookups, not embeddings.
- **Target:** `vector`, or the SQL table name.
- **Access level:** `public`, `student`, `staff`. Used for role-based retrieval filters later.
- **Status:** to collect, collected, parsed, indexed.

Raw files go to `data/raw/` locally (git-ignored); never commit source documents that are
not public.
