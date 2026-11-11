import re

from app.ingestion.chunking import (
    ChunkContext,
    chunk_faq,
    chunk_narrative,
    chunk_numbered,
    chunk_slides,
    finalize,
    pack,
    reflow,
    split_long,
)
from app.ingestion.models import Chunk, Page

CTX = ChunkContext(title="Belge", academic_year="2025-2026", max_chars=200)


def test_split_long_keeps_lines_and_respects_limit() -> None:
    text = "\n".join(f"- Madde {i}: kısa bir kural cümlesi burada yer alır." for i in range(10))

    pieces = split_long(text, 200)

    assert all(len(p) <= 200 for p in pieces)
    assert "\n".join(pieces) == text  # nothing lost, line breaks kept


def test_split_long_splits_a_long_line_at_sentences() -> None:
    line = " ".join(f"Cümle numarası {i} burada biter." for i in range(20))

    pieces = split_long(line, 120)

    assert all(len(p) <= 120 for p in pieces)
    assert all(p.endswith(".") for p in pieces)


def test_pack_combines_small_blocks() -> None:
    assert pack(["a" * 50, "b" * 50, "c" * 100], 120) == ["a" * 50 + "\n" + "b" * 50, "c" * 100]


def test_reflow_joins_wrapped_lines_but_keeps_items_and_date_rows() -> None:
    text = (
        "Bu cümle sayfa genişliğinde bölünmüş uzun bir satırdır ve\n"
        "devamı bir alt satırdadır.\n"
        "- Birinci madde\n"
        "- İkinci madde\n"
        "Staj Başlangıç Staj Bitiş\n"
        "22.06.2026 20.07.2026\n"
        "06.07.2026 03.08.2026"
    )

    assert reflow(text).split("\n") == [
        "Bu cümle sayfa genişliğinde bölünmüş uzun bir satırdır ve devamı bir alt satırdadır.",
        "- Birinci madde",
        "- İkinci madde",
        "Staj Başlangıç Staj Bitiş",
        "22.06.2026 20.07.2026",
        "06.07.2026 03.08.2026",
    ]


def test_faq_keeps_question_with_answer_and_joins_wrapped_question() -> None:
    text = (
        "Sık Sorulan Sorular\n"
        "•Stajımı hangi işletmede yapsam daha faydalı\n"
        "olur?\n"
        "Kararı kendiniz vermelisiniz. İşletme yetkilisiyle görüşüp stajda istenen çalışmaları\n"
        "yapıp yapamayacağınızı sorun; cevaba göre karar verin.\n"
        "•Kaza geçirirsem ne yapmalıyım?\n"
        "Üç gün içinde staj birim sorumlusuna bildirmeniz gerekir. Bu süre sigorta işlemleri için\n"
        "önemlidir ve kaçırılmamalıdır."
    )

    chunks = chunk_faq(text, ChunkContext(title="SSS"))

    assert [c.content.split("\n")[0] for c in chunks] == [
        "Soru: Stajımı hangi işletmede yapsam daha faydalı olur?",
        "Soru: Kaza geçirirsem ne yapmalıyım?",
    ]
    assert chunks[1].content.endswith("kaçırılmamalıdır.")
    assert chunks[1].header == "SSS | Kaza geçirirsem ne yapmalıyım?"


def test_numbered_decisions_one_chunk_each_with_intro() -> None:
    text = (
        "Komisyonun 04.01.2016 tarihli toplantısında aldığı kararlar aşağıdadır ve yatay, dikey\n"
        "geçiş ile ÇAP yapan tüm öğrenciler için geçerlidir.\n"
        "1. Matematik ve fizik dersleri için kredi ve not transferi yapılmaz; bu kural tüm\n"
        "geçişlerde, ön lisans derecesinde alınmış dersler için de aynı şekilde uygulanır.\n"
        "2. Türk Dili dersleri için kredi transferi yapılır; belgeler onaylı olmalı ve eksiksiz\n"
        "teslim edilmelidir. Eksik belge ile yapılan başvurular değerlendirilmez."
    )

    chunks = chunk_numbered(
        text,
        ChunkContext(title="Karar"),
        re.compile(r"^\d+\.\s"),
        item_label=lambda line: f"Karar {line.split('.')[0]}",
        pack_items=False,
    )

    assert [c.section for c in chunks] == ["Giriş", "Karar 1", "Karar 2"]
    assert "eksiksiz teslim edilmelidir." in chunks[2].content  # wrapped line re-joined


def test_numbered_procedure_packs_steps_and_names_range() -> None:
    steps = "\n".join(f"{i}- Adım açıklaması {i}: ilgili butona tıklayınız." for i in range(1, 9))
    text = f"ÖĞRENCİLERİN YAPACAĞI İŞLEMLER\n{steps}"

    chunks = chunk_numbered(
        text,
        ChunkContext(title="Prosedür", max_chars=200),
        re.compile(r"^\d+-\s"),
        item_label=lambda line: f"Adım {line.split('-')[0]}",
        pack_items=True,
    )

    assert chunks[0].section == "ÖĞRENCİLERİN YAPACAĞI İŞLEMLER / Adım 1 - 4"
    assert all(c.char_count <= 200 + 120 for c in chunks)
    assert "8- Adım" in chunks[-1].content


def test_narrative_detects_headings_with_or_without_blank_line() -> None:
    body = (
        "Bu paragraf bölüm hakkında yeterince uzun bir açıklama içerir ve tek başına bir parça "
        "olacak kadar bilgi taşır; kuruluş yılı, akreditasyon ve mezun sayısı gibi."
    )
    text = f"Tarihçe\n{body}\n\nMisyon ve Vizyon\n\n{body}"

    chunks = chunk_narrative(text, ChunkContext(title="Tanıtım"))

    assert [c.section for c in chunks] == ["Tarihçe", "Misyon ve Vizyon"]


def test_slides_are_packed_and_page_numbers_removed() -> None:
    pages = [
        Page(1, "BAŞLIK\n1"),
        Page(2, "14/27\nStaj Komisyonu\n- Madde bir"),
        Page(3, ""),
    ]

    chunks = chunk_slides(pages, ChunkContext(title="Sunum"))

    assert len(chunks) == 1
    assert chunks[0].content == "Slayt 1: BAŞLIK\nSlayt 2: Staj Komisyonu\n- Madde bir"
    assert (chunks[0].page_start, chunks[0].page_end) == (1, 2)


def test_finalize_merges_tiny_chunks_and_renumbers() -> None:
    chunks = [
        Chunk(0, "a", "h", "kısa"),
        Chunk(0, "b", "h", "x" * 150),
        Chunk(0, "c", "h", "son"),
        Chunk(0, "d", "h", ""),
    ]

    out = finalize(chunks, min_chars=20)

    assert [(c.ordinal, c.section) for c in out] == [(0, "b")]
    assert out[0].content == "kısa\n" + "x" * 150 + "\nson"
