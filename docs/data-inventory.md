# Data inventory

Every source the assistant may answer from. This table drives the ingestion design:
structured sources go to SQL tables, unstructured ones to the vector index, and the
access level becomes a retrieval filter.

**Snapshot:** v1 knowledge base, 102 files in Drive (`RAG Project/v1-kaynaklar`), all from
the **2025-2026 academic year**. Nothing for 2026-2027 has been collected yet.
**Review depth:** "read" means the content was inspected; "name only" means grouped by
file name and size and still needs a content review.

| # | Source (files) | Type | Count | Target | Access | As-of | Review | Notes |
|---|---|---|---|---|---|---|---|---|
| 1 | `DersPlan.csv` | CSV | 1 | SQL `courses` | public | 2025-26 | read | Semester, code, name, type, T+U, credit, ECTS. Elective slots have no course code. Four identical `MF-Teknik Seçmeli` rows per semester. |
| 2 | `seçmeliDersler.csv` | CSV | 1 | SQL `elective_courses` | public | 2025-26 | name only | |
| 3 | `akademikKadro.csv` | CSV | 1 | SQL `staff` | public | 2025-26 | name only | Names, titles, work e-mail addresses (public on the department site). |
| 4 | `BolumYonetimi.csv` | CSV | 1 | SQL `staff` (role column) | public | 2025-26 | read | Chair and two vice chairs. Roles can change. |
| 5 | `Komisyonlar.csv` | CSV | 1 | SQL `committees`, `committee_members` | public | 2025-26 | name only | 24 KB, largest structured file. |
| 6 | `25-26AkademikTakvim.csv` | CSV | 1 | SQL `academic_calendar` | public | 2025-26 | name only | **Outdated: must be replaced with the 2026-27 calendar.** |
| 7 | `ogrenciSayilari.csv`, `personelSayısı.csv` | CSV | 2 | SQL `department_stats` | public | 2025-26 | read (students) | Student counts are per program (1st, 2nd, distance), so "how many students" needs a sum (626 + 363 + 11 = 1000). Numbers change every year. |
| 8 | Course information packages (`Matematik 1.txt` … `Yapay Zeka.txt`) | TXT | ~82 | vector, linked to `courses` by name | public | 2025-26 | name only | One file per course. Includes `Staj 1`, `Staj 2`, `Bitirme Calismasi`. |
| 9 | `OgrenciDanismanligi.pdf`, `OgrenciDegisimi.pdf`, `StajSSS.pdf`, `YatayDikeyGecisIntibakKomisyonKarari.pdf` | PDF | 4 | vector, article-aware chunking | public | 2025-26 | name only | Regulations and FAQs. |
| 10 | `StajBilgilendirmeSunumu1.pdf`, `StajBilgilendirmeSunumu2.pdf`, `2025-2026 Ara Donem Staj Hakkında - Kopya.pdf` | PDF (slides) | 3 | vector, slide-aware parsing | public | 2025-26 | name only | Slide decks need different parsing from regulations. The third file name contains "Kopya" (copy): confirm it is the intended canonical version. |
| 11 | `MezuniyetKosulları.txt`, `StajSSS.txt`, `OgrenciDegisimi.txt`, `OgrenciDanismanligi.txt` | TXT | 4 | **decide: duplicate or canonical** | public | 2025-11-24 | read (graduation) | Older plain-text copies of PDF content. Keeping both versions will return duplicate chunks. `MezuniyetKosulları.txt` states 60 internship days, which is wrong (see finding 2): do not ingest as-is. |
| 12 | `bolumTanıtımı.txt` | TXT | 1 | vector | public | n/a | read | **File is empty (0 bytes).** Upload probably failed. |

## Findings that change the plan

1. **v1 retrieval failures were not missing data.** The answers to all four failed v1 questions
   exist in the sources: department chair (`BolumYonetimi.csv`), student count
   (`ogrenciSayilari.csv`, by summation), Yöneylem 2 semester (`DersPlan.csv`), graduation
   requirements (`MezuniyetKosulları.txt`). This supports ADR-0001: the bottleneck was
   retrieval, not the knowledge base. Caveat: file dates suggest the graduation file may have
   been added after the v1 test run; this should be verified.
2. **`MezuniyetKosulları.txt` contradicts the Internship Regulation (resolved by owner).**
   The file says **60 business days** of internship are required to graduate. The correct value
   is two internships of 20 business days each (40 in total), confirmed by the project owner on
   2026-11-10. The file is therefore wrong or from an older regulation. **Decision: do not
   ingest it as-is.** Either correct the sentence in the source file or drop the file. If it is
   ingested uncorrected, the assistant will give 40 days for "how long is the internship" and
   60 days for "graduation requirements". The v1 reference answer for graduation conditions
   (minimum 2.0 GPA, 240 ECTS) does not appear in this file either; its source is unknown, so
   this question stays out of the golden dataset until a source is found.
3. **Every source needs an academic year.** Calendar and student counts are stale by
   definition; staff, committees and curriculum may be. Stage 1 adds `academic_year` and
   `valid_from` / `valid_until` to every document and table row, and the assistant states the
   document date it answered from.
4. **Duplicate and dirty inputs.** Duplicate elective rows (#1), TXT/PDF twins (#11), an empty
   file (#12). The ingestion pipeline must deduplicate and validate non-empty content.
5. **Linearized sentences in `DersPlan.csv` carry artifacts**, e.g. `Yapay Zeka ve Üretkenlik ()`
   for a missing course code. This was the v1 approach; v2 queries the table directly with SQL.

## Data scope decision (2026-11-10)

The project owner decided to **continue with the 2025-2026 snapshot** and not to integrate the
assistant with the department website or collect 2026-2027 data for now. The dataset can be
replaced later if needed. Consequences:

- The assistant must label time-sensitive answers with the source year (for example "according
  to the 2025-2026 academic calendar"), which is why `academic_year` metadata is in Stage 1.
- The README and any demo state that the knowledge base is a 2025-2026 snapshot.
- Golden dataset questions about dates, counts and office holders are written against the
  snapshot and tagged `snapshot-sensitive`, so they can be re-verified if the data is replaced.
- Scraping and incremental re-indexing stay in the architecture as a design capability but are
  not part of the MVP data scope.

## Column guide

- **Target:** `vector`, or the SQL table name.
- **Access:** `public`, `student`, `staff`; used for role-based retrieval filters later.
- **As-of:** academic year or date the content describes.

Raw files stay in Drive and in `data/raw/` locally (git-ignored); never commit source documents.

## Update 2026-11-10 (second pass, after owner review)

Fixed by the owner in the source files: the Spring make-up exam end date (now 5.07.2026), a
departed staff member removed from `akademikKadro.csv` and `Komisyonlar.csv`, typos in one
staff name and one e-mail address, the "Kopya" suffix removed from the Ara Dönem internship
PDF, and `BolumTanitimi.txt` re-uploaded (no longer empty). Confirmed correct: the two
Three-Course Graduation Exam rows for Spring (16-17.07.2026 and 05.10.2026; the second is
for students who complete courses in summer school).

New source `StajBilgilendirme.txt` (the Industrial Engineering section of the staj.sabis
announcement, copied by hand on 2026-11-10; only this section is used, other departments'
rules contradict it). Notes for ingestion:

- It holds the 2026 summer internship windows and application deadlines. Label answers with
  the source year; these dates are in the past for the 2025-2026 snapshot.
- It states that Saturdays count as working days if the company works Saturdays and the
  student documents it. `StajBilgilendirmeSunumu1.pdf` (2013-14) says the opposite. Prefer
  the new file; Sunumu1 stays in the corpus only as a conflict test (`staj-cumartesi` group).
- The form instructions still say "Akademik yıl: 2024-2025" (stale text in the source).
- It lists the extra-period internship exception: employer with more than 1000 employees, or
  the student meets the graduation conditions "(240 AKTS, FF DERS YOK, ORT > 2.00, 9 TEKNİK
  SEÇMELİ ALINMIŞ)". This is the first source found for the v1 "2.0 GPA / 240 ECTS" answer,
  but it is stated inside the internship exception, not as a general graduation requirement.
  No graduation-conditions question is added until the owner confirms the rule.
- Its Ara Dönem section says 3rd and 4th year students; the Ara Dönem PDF also names students
  with extended study. Minor wording difference, same rule.
- It contains the staff contact (name, e-mail, phone) of the internship office; these are
  public department contacts.


## Update 2026-11-11 (graduation file removed, graduation rule confirmed)

- The owner deleted `MezuniyetKosulları.txt` from the Drive source folder (it stated 60
  internship days, which is wrong). Table row 11 above is kept as history; the file is no
  longer part of the corpus and must not be re-added. The other three TXT twins (`StajSSS`,
  `OgrenciDegisimi`, `OgrenciDanismanligi`) are still to be moved to an `arsiv` subfolder.
- The owner confirmed the graduation rule: **240 ECTS completed and a GPA above 2.00**. This
  is now the verified source for the golden-set question `bb702c0` and replaces the
  "until the owner confirms" note above.
- Not confirmed by the owner: "no FF grades" and "9 technical electives". They appear only in
  `StajBilgilendirme.txt` (extra-period internship exception), so they are not stated as
  general graduation rules.
