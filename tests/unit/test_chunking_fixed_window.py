from itertools import pairwise

import pytest

from app.ingestion.chunking import chunk_fixed_window
from app.ingestion.chunking.fixed_window import DEFAULT_OVERLAP, DEFAULT_SIZE, SEGMENT_JOINER
from app.ingestion.models import Segment, TextChunk


def _words(count: int, stem: str = "staj") -> str:
    return " ".join(f"{stem}{i}" for i in range(count))


def _shared_edge(first: str, second: str) -> int:
    """Length of the longest end of `first` that is also the start of `second`."""
    for length in range(min(len(first), len(second)), 0, -1):
        if first.endswith(second[:length]):
            return length
    return 0


def test_defaults_are_the_v1_parameters() -> None:
    # TasarımDokuman.pdf, pages 11 and 15: 1000 characters, 200 characters overlap.
    assert (DEFAULT_SIZE, DEFAULT_OVERLAP) == (1000, 200)


def test_short_text_is_one_chunk() -> None:
    chunks = chunk_fixed_window([Segment(text="Staj 20 iş günüdür.")])

    assert chunks == (TextChunk(text="Staj 20 iş günüdür.", position=0),)


def test_paragraphs_that_fit_stay_together() -> None:
    paragraphs = ["A" * 300, "B" * 300, "C" * 300, "D" * 300]

    chunks = chunk_fixed_window([Segment(text="\n\n".join(paragraphs))])

    # A+B+C is 904 characters; adding D would pass 1000. A paragraph is longer than the
    # 200-character overlap, so the next chunk does not repeat one.
    assert [chunk.text for chunk in chunks] == ["\n\n".join(paragraphs[:3]), paragraphs[3]]


def test_line_breaks_are_used_before_spaces() -> None:
    lines = [f"{i:02d} " + "x" * 57 for i in range(6)]  # six 60-character lines

    chunks = chunk_fixed_window([Segment(text="\n".join(lines))], size=130, overlap=0)

    assert [chunk.text for chunk in chunks] == [
        "\n".join(lines[0:2]),
        "\n".join(lines[2:4]),
        "\n".join(lines[4:6]),
    ]


def test_no_chunk_is_longer_than_size() -> None:
    text = "\n\n".join([_words(40), _words(300, "madde"), "x" * 450, _words(5, "son")])

    chunks = chunk_fixed_window([Segment(text=text)], size=100, overlap=30)

    assert chunks
    assert all(len(chunk.text) <= 100 for chunk in chunks)


def test_neighbouring_chunks_overlap_by_at_most_the_overlap() -> None:
    chunks = chunk_fixed_window([Segment(text=_words(400))], size=100, overlap=30)

    edges = [_shared_edge(a.text, b.text) for a, b in pairwise(chunks)]
    assert all(0 < edge <= 30 for edge in edges)


def test_without_overlap_every_word_appears_once() -> None:
    text = _words(400)

    chunks = chunk_fixed_window([Segment(text=text)], size=100, overlap=0)

    assert " ".join(chunk.text for chunk in chunks) == text


def test_every_word_is_kept() -> None:
    text = _words(400)

    chunks = chunk_fixed_window([Segment(text=text)], size=100, overlap=30)

    assert {word for chunk in chunks for word in chunk.text.split()} == set(text.split())


def test_word_longer_than_size_is_cut_between_characters() -> None:
    chunks = chunk_fixed_window([Segment(text="x" * 250)], size=100, overlap=0)

    assert [chunk.text for chunk in chunks] == ["x" * 100, "x" * 100, "x" * 50]


def test_chunks_are_exact_slices_of_the_input() -> None:
    segments = [
        Segment(text="Öğrenci Danışmanlığı\n\n" + _words(120, "danışman"), page=1),
        Segment(text="Şirket Cumartesi çalışıyorsa\n" + _words(80, "iş"), page=2),
    ]
    joined = SEGMENT_JOINER.join(segment.text for segment in segments)

    chunks = chunk_fixed_window(segments, size=200, overlap=50)

    assert all(chunk.text in joined for chunk in chunks)


def test_chunk_carries_the_page_it_starts_on() -> None:
    # Short paragraphs on both sides of the page break, so one chunk crosses it.
    page_1 = "\n\n".join(["A" * 90, "B" * 90])
    page_2 = "\n\n".join(["C" * 90, "D" * 90, "E" * 90])
    segments = [Segment(text=page_1, page=1), Segment(text=page_2, page=2)]

    chunks = chunk_fixed_window(segments, size=300, overlap=0)

    # A + B + C is 274 characters; adding D would pass 300.
    assert [(chunk.text[0], chunk.page) for chunk in chunks] == [("A", 1), ("D", 2)]
    assert "C" * 90 in chunks[0].text  # page boundaries are ignored


def test_txt_chunks_have_no_page_and_no_section() -> None:
    chunks = chunk_fixed_window([Segment(text=_words(300))], size=200, overlap=40)

    assert all(chunk.page is None and chunk.section is None for chunk in chunks)


def test_positions_count_from_zero() -> None:
    chunks = chunk_fixed_window([Segment(text=_words(300))], size=200, overlap=40)

    assert [chunk.position for chunk in chunks] == list(range(len(chunks)))


@pytest.mark.parametrize("segments", [[], [Segment(text="   \n\n  ")]], ids=["none", "blank"])
def test_no_text_gives_no_chunks(segments: list[Segment]) -> None:
    assert chunk_fixed_window(segments) == ()


@pytest.mark.parametrize(("size", "overlap"), [(0, 0), (-1, 0), (100, -1), (100, 100), (100, 150)])
def test_invalid_parameters_are_rejected(size: int, overlap: int) -> None:
    with pytest.raises(ValueError):
        chunk_fixed_window([Segment(text="metin")], size=size, overlap=overlap)
