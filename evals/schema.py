"""Schema for the golden evaluation dataset (one JSON object per line, JSONL).

Splits live in separate files: `dev.jsonl` is used while tuning prompts and
parameters; `test.jsonl` is only used for release reports. Keeping them apart
prevents tuning on the test set (evaluation data leakage).
"""

from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

Category = Literal[
    "regulation",  # yönetmelik / yönerge
    "internship",  # staj
    "curriculum",  # ders planı, AKTS, ön koşul
    "staff",  # akademik kadro, iletişim, komisyonlar
    "calendar",  # akademik takvim, sınav tarihleri
    "exchange",  # Erasmus, Farabi
    "general",  # bölüm hakkında genel bilgi
    "out_of_scope",  # bölüm dışı konular
    "adversarial",  # prompt injection, sızdırma denemeleri
]
ExpectedBehavior = Literal["answer", "refuse", "clarify"]


class Turn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["user", "assistant"]
    content: str = Field(min_length=1)


class EvalItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[a-z]+-\d{3,}$", description="e.g. 'internship-001'")
    question: str = Field(min_length=3)
    history: list[Turn] = Field(
        default_factory=list, description="Prior turns for multi-turn cases"
    )
    expected_behavior: ExpectedBehavior = "answer"
    reference_answer: str | None = None
    source_documents: list[str] = Field(default_factory=list)
    source_sections: list[str] = Field(default_factory=list, description="e.g. 'Madde 7'")
    category: Category
    difficulty: Literal["easy", "medium", "hard"] = "medium"
    tags: list[str] = Field(default_factory=list)
    notes: str | None = None

    @model_validator(mode="after")
    def answerable_items_need_ground_truth(self) -> Self:
        if self.expected_behavior == "answer":
            if not self.reference_answer:
                raise ValueError("items with expected_behavior='answer' need a reference_answer")
            if not self.source_documents:
                raise ValueError("items with expected_behavior='answer' need source_documents")
        return self
