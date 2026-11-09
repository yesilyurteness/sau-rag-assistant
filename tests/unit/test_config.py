import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_defaults_are_safe_for_local_dev() -> None:
    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    assert settings.app_env == "dev"
    assert not settings.is_prod
    assert settings.anthropic_api_key is None


def test_reads_environment_variables(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "prod")
    monkeypatch.setenv("GOOGLE_API_KEY", "secret-value")

    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    assert settings.is_prod
    assert settings.google_api_key is not None
    assert settings.google_api_key.get_secret_value() == "secret-value"


def test_secrets_are_masked_in_repr(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-should-not-leak")

    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    assert "sk-should-not-leak" not in repr(settings)


def test_rejects_unknown_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "staging-typo")

    with pytest.raises(ValidationError):
        Settings(_env_file=None)  # type: ignore[call-arg]
