import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from evals.schema import EvalItem
from evals.validate_dataset import validate

REPO_DATASETS = Path(__file__).parents[2] / "evals" / "datasets"


def _write(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows), encoding="utf-8")


def _item(id_: str, question: str) -> dict[str, object]:
    return {
        "id": id_,
        "question": question,
        "reference_answer": "x",
        "source_documents": ["doc"],
        "category": "general",
    }


def test_repository_datasets_are_valid() -> None:
    report = validate(REPO_DATASETS)
    assert report.ok, report.errors


def test_answer_items_require_ground_truth() -> None:
    with pytest.raises(ValidationError, match="reference_answer"):
        EvalItem.model_validate({"id": "general-001", "question": "Soru?", "category": "general"})


def test_refusal_items_do_not_need_reference() -> None:
    item = EvalItem.model_validate(
        {
            "id": "outofscope-001",
            "question": "Hava nasıl?",
            "expected_behavior": "refuse",
            "category": "out_of_scope",
        }
    )
    assert item.reference_answer is None


def test_detects_question_leaking_between_dev_and_test(tmp_path: Path) -> None:
    _write(tmp_path / "dev.jsonl", [_item("general-001", "Bölüm başkanı kimdir?")])
    _write(tmp_path / "test.jsonl", [_item("general-002", "  BÖLÜM başkanı   kimdir? ")])

    report = validate(tmp_path)

    assert not report.ok
    assert any("both dev and test" in e for e in report.errors)


def test_detects_duplicate_ids(tmp_path: Path) -> None:
    _write(
        tmp_path / "dev.jsonl", [_item("general-001", "Soru A?"), _item("general-001", "Soru B?")]
    )

    report = validate(tmp_path)

    assert any("duplicate id" in e for e in report.errors)
