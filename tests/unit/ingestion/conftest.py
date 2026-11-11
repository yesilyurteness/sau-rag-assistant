from pathlib import Path

import pytest

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "ingestion"


@pytest.fixture
def fixtures() -> Path:
    return FIXTURES
