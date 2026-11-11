"""Parse a cleaned course information package (EBS print) and turn it into section chunks.

Input is the output of `cleaning.clean_course_package`: the pipe-table copy of the page, e.g.

    Ders Adı | Kodu | Yarıyıl | T+U Saat | Kredi | AKTS
    Bitirme Çalışması | ENM 498 | 8 | 0 + 4 | 4 | 10
    Dersin Dili | Türkçe
    ...
    Hafta | Ders Konuları | Ön Hazırlık
    1 | Konunun araştırılması |

The parser is tolerant: unknown lines are attached to the current section, and anything missing is
reported as a finding instead of raising.
"""

import re
from dataclasses import dataclass, field

from app.ingestion.chunking import MAX_CHARS, ChunkContext, finalize, pack
from app.ingestion.models import Chunk, Finding, Severity

_COURSE_HEADER = "Ders Adı | Kodu | Yarıyıl | T+U Saat | Kredi | AKTS"
_KV_KEYS = (
    "Ön Koşul Dersleri",
    "Önerilen Seçmeli Dersler",
    "Dersin Dili",
    "Dersin Seviyesi",
    "Dersin Türü",
    "Dersin Koordinatörü",
    "Dersi Verenler",
    "Dersin Yardımcıları",
    "Dersin Kategorisi",
    "Dersin Amacı",
    "Dersin İçeriği",
    "Ders Notu",
    "Ders Kaynakları",
)
_KV_RE = re.compile(rf"^(?P<key>{'|'.join(map(re.escape, _KV_KEYS))}) \|(?: (?P<value>.*))?$")
_OUTCOMES_RE = re.compile(r"^# \| Ders Öğrenme Çıktıları \| Öğretim Yöntemleri")
_WEEKLY_RE = re.compile(r"^Hafta \| Ders Konuları")
_CONTRIB_RE = re.compile(r"^# \| Ders Öğrenme Çıktılarının Program Çıktılarına")
_PROGOUT_RE = re.compile(r"^Sıra \| Program Çıktıları")
_ASSESS_RE = re.compile(r"^Değerlendirme Sistemi \|")
_WORKLOAD_RE = re.compile(r"^AKTS - İş Yükü Etkinlik \|")
_NUMBERED_ROW_RE = re.compile(r"^(\d+) \|\s*(.*)$")
_PROGOUT_ROW_RE = re.compile(r"^(\d+)(?: ?([a-d]))? \|\s*(.*)$")
_LEVEL_HEADER_RE = re.compile(r"^\| \| 1 \| 2 \| 3 \| 4 \| 5$")


@dataclass
class Outcome:
    """One learning outcome row: `text | teaching methods | measurement methods`."""

    number: int
    raw: str = ""  # row text joined across wrapped lines; cells are split from it

    def _cell(self, index: int) -> str:
        cells = [c.strip() for c in self.raw.split(" | ")]
        return cells[index].strip("| ").strip() if len(cells) > index else ""

    @property
    def text(self) -> str:
        return self._cell(0)

    @property
    def methods(self) -> str:
        return self._cell(1)

    @property
    def measures(self) -> str:
        return self._cell(2)

    def add(self, text: str) -> None:
        self.raw = f"{self.raw} {text}".strip()


@dataclass
class CoursePackage:
    name: str
    code: str
    semester: str
    tu_hours: str
    credit: str
    ects: str
    kv: dict[str, str] = field(default_factory=dict)
    outcomes: list[Outcome] = field(default_factory=list)
    weekly: list[tuple[int, str, str]] = field(default_factory=list)
    program_outcomes: list[tuple[str, str, int | None]] = field(default_factory=list)
    assessment: list[str] = field(default_factory=list)
    workload: list[str] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)

    def metadata(self) -> dict[str, object]:
        total = _first_number(self.workload, "Toplam İş Yükü |")
        per_25 = _first_number(self.workload, "Toplam İş Yükü / 25")
        return {
            "course_code": self.code,
            "course_name": self.name,
            "semester": self.semester,
            "tu_hours": self.tu_hours,
            "credit": self.credit,
            "ects": self.ects,
            "language": self.kv.get("Dersin Dili", ""),
            "level": self.kv.get("Dersin Seviyesi", ""),
            "course_type": self.kv.get("Dersin Türü", ""),
            "coordinator": self.kv.get("Dersin Koordinatörü", ""),
            "workload_total_hours": total,
            "workload_hours_div_25": per_25,
        }


def _first_number(lines: list[str], prefix: str) -> float | None:
    for line in lines:
        if line.startswith(prefix):
            cells = [c.strip() for c in line.split("|")]
            value = next((c for c in reversed(cells) if c), "")
            try:
                return float(value.replace(",", "."))
            except ValueError:
                return None
    return None


def _cells(text: str) -> list[str]:
    return [c.strip() for c in text.split("|")]


def parse_course_package(text: str) -> CoursePackage | None:
    """Return the parsed package, or None when the text has no course header table."""
    lines = [ln for ln in text.split("\n")]
    header_at = next((i for i, ln in enumerate(lines) if ln == _COURSE_HEADER), None)
    if header_at is None:
        return None

    findings: list[Finding] = []
    values = next((ln for ln in lines[header_at + 1 :] if ln.strip()), "")
    parts = _cells(values)
    if len(parts) != 6:
        findings.append(
            Finding(
                Severity.WARNING, "course_header_malformed", f"expected 6 header cells: {values!r}"
            )
        )
        parts = (parts + [""] * 6)[:6]
    name, code, semester, tu_hours, credit, ects = parts
    pkg = CoursePackage(name, code, semester, tu_hours, credit, ects)

    mode = "kv"
    key: str | None = None
    kv_lines: dict[str, list[str]] = {}
    outcome: Outcome | None = None
    week: list[str] | None = None
    prog_row: list[str] | None = None
    pending_number: str | None = None
    weekly_raw: list[list[str]] = []
    prog_raw: list[list[str]] = []

    for line in lines[header_at + 2 :]:
        if not line:
            continue
        kv = _KV_RE.match(line)
        if kv:
            mode, key = "kv", kv.group("key")
            kv_lines[key] = [kv.group("value") or ""]
            continue
        if _OUTCOMES_RE.match(line):
            mode = "outcomes"
            continue
        if _WEEKLY_RE.match(line):
            mode = "weekly"
            continue
        if _CONTRIB_RE.match(line):
            mode = "contrib"
            continue
        if _PROGOUT_RE.match(line):
            mode = "progout"
            continue
        if _ASSESS_RE.match(line):
            mode = "assess"
            continue
        if _WORKLOAD_RE.match(line):
            mode = "workload"
            continue
        if line.startswith("Kaynaklar |"):
            mode, key = "kv", None
            continue

        if mode == "kv" and key is not None:
            kv_lines[key].append(line)
        elif mode == "outcomes":
            row = _NUMBERED_ROW_RE.match(line)
            if row:
                outcome = Outcome(int(row.group(1)))
                pkg.outcomes.append(outcome)
                outcome.add(row.group(2))
            elif outcome is not None:
                outcome.add(line)
        elif mode == "weekly":
            row = _NUMBERED_ROW_RE.match(line)
            if row:
                week = [row.group(1), row.group(2)]
                weekly_raw.append(week)
            elif week is not None:
                week[-1] = f"{week[-1]} {line}"
        elif mode == "progout":
            if _LEVEL_HEADER_RE.match(line):
                continue
            if re.fullmatch(r"\d+", line):
                pending_number = line  # id split over two lines: "10" then "a | text ..."
                continue
            candidate = f"{pending_number} {line}" if pending_number else line
            pending_number = None
            row = _PROGOUT_ROW_RE.match(candidate)
            if row:
                prog_row = [f"{row.group(1)}{row.group(2) or ''}", row.group(3)]
                prog_raw.append(prog_row)
            elif prog_row is not None:
                prog_row[-1] = f"{prog_row[-1]} {line}"
        elif mode == "assess":
            pkg.assessment.append(line)
        elif mode == "workload":
            pkg.workload.append(line)

    for k, vals in kv_lines.items():
        pkg.kv[k] = _clean_list_text(" ".join(v for v in vals if v))
    pkg.weekly = [(int(n), *_split_topic(rest)) for n, rest in weekly_raw]
    pkg.program_outcomes = [(ident, *_split_program_outcome(rest)) for ident, rest in prog_raw]
    pkg.program_outcomes = [p for p in pkg.program_outcomes if p[2] is not None]
    pkg.findings.extend(findings)
    return pkg


def _split_topic(rest: str) -> tuple[str, str]:
    cells = [c.strip() for c in rest.split(" | ")]
    topic = cells[0].rstrip("|").strip()
    prep = cells[1].rstrip("|").strip() if len(cells) > 1 else ""
    return topic, prep


def _split_program_outcome(rest: str) -> tuple[str, int | None]:
    cells = [c.strip() for c in rest.split("|")]
    text = cells[0]
    levels = cells[1:]
    level = next((i for i, c in enumerate(levels[-5:], start=1) if c.upper() == "X"), None)
    return text, level


def _clean_list_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r",(?=\S)", ", ", text)  # "Prof.Dr. A,Prof.Dr. B" -> "Prof.Dr. A, Prof.Dr. B"
    return text.strip().strip(",").strip()


def _sentence(text: str) -> str:
    text = text.strip().rstrip(",;")
    return text if not text or text[-1] in ".!?" else f"{text}."


# --- chunks ------------------------------------------------------------------------------------

_SECTION_LABELS = {
    "card": "Ders bilgileri",
    "instructors": "Dersi verenler",
    "purpose": "Amaç ve içerik",
    "outcomes": "Öğrenme çıktıları",
    "weekly": "Haftalık plan",
    "resources": "Kaynaklar",
    "assessment": "Değerlendirme ve AKTS iş yükü",
    "program_outcomes": "Program çıktılarına katkı",
}


def course_context(pkg: CoursePackage, academic_year: str | None) -> ChunkContext:
    return ChunkContext(title=f"Ders: {pkg.name} ({pkg.code})", academic_year=academic_year)


def course_chunks(pkg: CoursePackage, ctx: ChunkContext) -> list[Chunk]:
    """One chunk per section (split by size where needed), each tagged with the section name."""
    out: list[Chunk] = []

    def add(section: str, blocks: list[str], label: str | None = None) -> None:
        blocks = [b for b in blocks if b.strip()]
        for part in pack(blocks, ctx.max_chars):
            name = label or _SECTION_LABELS[section]
            out.append(Chunk(0, name, ctx.header(name), part, metadata={"course_section": section}))

    kv = pkg.kv
    card = [
        f"Ders adı: {pkg.name}",
        f"Ders kodu: {pkg.code}",
        f"Yarıyıl: {pkg.semester}",
        f"Haftalık ders saati (teori + uygulama): {pkg.tu_hours}",
        f"Kredi: {pkg.credit}",
        f"AKTS: {pkg.ects}",
        f"Ön koşul dersleri: {kv.get('Ön Koşul Dersleri') or 'yok'}",
        f"Önerilen seçmeli dersler: {kv.get('Önerilen Seçmeli Dersler') or 'yok'}",
        f"Dersin dili: {kv.get('Dersin Dili', '')}",
        f"Dersin seviyesi: {kv.get('Dersin Seviyesi', '')}",
        f"Dersin türü: {kv.get('Dersin Türü', '')}",
        f"Dersin koordinatörü: {kv.get('Dersin Koordinatörü', '')}",
        f"Dersin kategorisi: {kv.get('Dersin Kategorisi', '')}",
    ]
    add("card", ["\n".join(line for line in card if not line.endswith(": "))])

    staff = [f"Dersin koordinatörü: {kv.get('Dersin Koordinatörü', '')}"]
    if kv.get("Dersi Verenler"):
        staff.append(f"Dersi verenler: {kv['Dersi Verenler']}")
    if kv.get("Dersin Yardımcıları"):
        staff.append(f"Dersin yardımcıları: {kv['Dersin Yardımcıları']}")
    if len(staff) > 1:
        add("instructors", ["\n".join(staff)])

    add(
        "purpose",
        [
            f"Dersin amacı: {kv['Dersin Amacı']}" if kv.get("Dersin Amacı") else "",
            f"Dersin içeriği: {kv['Dersin İçeriği']}" if kv.get("Dersin İçeriği") else "",
        ],
    )

    add(
        "outcomes",
        [
            f"Öğrenme çıktısı {o.number}: {_sentence(o.text)}"
            + (f" Öğretim yöntemleri: {o.methods.rstrip(',')}." if o.methods else "")
            + (f" Ölçme yöntemleri: {o.measures.rstrip(',')}." if o.measures else "")
            for o in pkg.outcomes
        ],
    )

    for first, last, text in _pack_weeks(pkg.weekly, ctx.max_chars):
        add("weekly", [text], label=f"Haftalık plan (hafta {first}-{last})")

    add(
        "resources",
        [
            f"Ders notu: {kv['Ders Notu']}" if kv.get("Ders Notu") else "",
            f"Ders kaynakları: {kv['Ders Kaynakları']}" if kv.get("Ders Kaynakları") else "",
        ],
    )

    assessment = _render_table_lines(pkg.assessment)
    if assessment:
        assessment.insert(0, "Değerlendirme sistemi (katkı oranı, %):")
    workload = _render_table_lines(pkg.workload, header=_WORKLOAD_HEADER)
    if workload:
        assessment += ["AKTS iş yükü:", *workload]
    if assessment:
        assessment.append(f"Dersin AKTS kredisi (ders bilgileri tablosu): {pkg.ects}")
    add("assessment", ["\n".join(assessment)])

    add(
        "program_outcomes",
        [
            "\n".join(
                f"Program çıktısı {ident}: {_shorten(text, 90)} (katkı düzeyi {level}/5)"
                for ident, text, level in pkg.program_outcomes
            )
        ],
    )
    return finalize(out, min_chars=0)


def _pack_weeks(
    weeks: list[tuple[int, str, str]], max_chars: int = MAX_CHARS
) -> list[tuple[int, int, str]]:
    groups: list[tuple[int, int, str]] = []
    lines: list[tuple[int, str]] = []
    for number, topic, prep in sorted(weeks, key=lambda w: w[0]):
        line = f"Hafta {number}: {topic}" + (f" (ön hazırlık: {prep})" if prep else "")
        if lines and sum(len(t) + 1 for _, t in lines) + len(line) > max_chars:
            groups.append((lines[0][0], lines[-1][0], "\n".join(t for _, t in lines)))
            lines = []
        lines.append((number, line))
    if lines:
        groups.append((lines[0][0], lines[-1][0], "\n".join(t for _, t in lines)))
    return groups


_ROW_LABELS = {"dersAKTSKredisi": "Dersin AKTS kredisi (iş yükü tablosu)"}
_WORKLOAD_HEADER = ["sayı", "süre (saat)", "toplam iş yükü (saat)"]


def _render_table_lines(lines: list[str], header: list[str] | None = None) -> list[str]:
    """Render `label | a | b | c` rows as readable lines (`label: header value; ...`)."""
    out: list[str] = []
    header = list(header or [])
    for line in lines:
        cells = _cells(line)
        label, values = cells[0], cells[1:]
        if label in ("Yarıyıl Çalışmaları", "AKTS - İş Yükü Etkinlik") or label.startswith(
            "Etkinlik"
        ):
            header = values
            continue
        filled = [(i, v) for i, v in enumerate(values) if v]
        label = _ROW_LABELS.get(label, label)
        if not filled:
            continue
        if len(filled) == 1 or not header:
            out.append(f"{label}: {', '.join(v for _, v in filled)}")
        else:
            named = [f"{header[i]} {v}" if i < len(header) else v for i, v in filled]
            out.append(f"{label}: {'; '.join(named)}")
    return out


def _shorten(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1].rsplit(" ", 1)[0] + "…"
