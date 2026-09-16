import pytest

from app.config import Settings


def test_cors_origins_parses_comma_separated_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Railway and .env files provide comma-separated lists, not JSON arrays."""
    monkeypatch.setenv("CORS_ORIGINS", "https://a.example.com, http://localhost:3000")
    settings = Settings()
    assert settings.cors_origin_list == ["https://a.example.com", "http://localhost:3000"]


def test_cors_origins_ignores_blank_entries(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CORS_ORIGINS", "https://a.example.com,,   ,")
    assert Settings().cors_origin_list == ["https://a.example.com"]


def test_cors_origins_default_is_localhost() -> None:
    assert Settings.model_fields["cors_origins"].default == "http://localhost:3000"


def test_is_production_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "production")
    assert Settings().is_production is True
    monkeypatch.setenv("ENVIRONMENT", "development")
    assert Settings().is_production is False
