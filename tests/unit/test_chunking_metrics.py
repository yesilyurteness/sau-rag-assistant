from app.ingestion.chunking.metrics import (
    SizeSummary,
    count_empty,
    count_small,
    count_units_kept_whole,
    structural_report,
    summarize_sizes,
)

QUESTION_1 = "•Staj kaç gün? Staj 20 iş günüdür."
QUESTION_2 = "•Cumartesi sayılır mı? Belgelenirse sayılır."


def test_unit_inside_one_chunk_is_kept_whole() -> None:
    chunks = [f"{QUESTION_1} {QUESTION_2}"]

    assert count_units_kept_whole([QUESTION_1, QUESTION_2], chunks) == 2


def test_unit_split_across_chunks_is_not_kept_whole() -> None:
    chunks = [f"{QUESTION_1} •Cumartesi sayılır mı?", "Belgelenirse sayılır."]

    assert count_units_kept_whole([QUESTION_1, QUESTION_2], chunks) == 1


def test_line_breaks_do_not_count_as_a_split() -> None:
    unit = "Madde 1 - Öğrenciler iki staj yapar;\nher staj 20 iş günüdür."
    chunk = "Madde 1 - Öğrenciler iki staj yapar; her staj  20 iş günüdür."

    assert count_units_kept_whole([unit], [chunk]) == 1


def test_sizes_of_no_chunks_are_zero() -> None:
    assert summarize_sizes([]) == SizeSummary(0, 0, 0.0, 0.0, 0.0, 0)


def test_sizes_of_one_chunk() -> None:
    assert summarize_sizes(["x" * 7]) == SizeSummary(1, 7, 7.0, 7.0, 7.0, 7)


def test_size_quartiles() -> None:
    chunks = ["x" * length for length in (50, 10, 40, 20, 30)]

    assert summarize_sizes(chunks) == SizeSummary(5, 10, 20.0, 30.0, 40.0, 50)


def test_empty_and_small_chunks_are_counted_separately() -> None:
    chunks = ["", "   \n", "kısa", "x" * 99, "x" * 100]

    assert count_empty(chunks) == 2
    assert count_small(chunks, threshold=100) == 2


def test_report_combines_the_metrics() -> None:
    chunks = [f"{QUESTION_1} •Cumartesi sayılır mı?", "Belgelenirse sayılır.", " "]

    report = structural_report([QUESTION_1, QUESTION_2], chunks, small_threshold=30)

    assert (report.units, report.units_kept_whole, report.kept_whole_ratio) == (2, 1, 0.5)
    assert report.size.count == 3
    assert (report.empty_chunks, report.small_chunks) == (1, 1)


def test_no_units_counts_as_fully_kept() -> None:
    assert structural_report([], ["metin"]).kept_whole_ratio == 1.0
