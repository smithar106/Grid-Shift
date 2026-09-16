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


@pytest.mark.parametrize(
    ("provided", "expected"),
    [
        ("postgresql://u:p@host:5432/db", "postgresql+psycopg://u:p@host:5432/db"),
        ("postgres://u:p@host:5432/db", "postgresql+psycopg://u:p@host:5432/db"),
        ("postgresql+psycopg://u:p@host:5432/db", "postgresql+psycopg://u:p@host:5432/db"),
        ("sqlite:///./gridshift.db", "sqlite:///./gridshift.db"),
    ],
)
def test_sqlalchemy_url_selects_psycopg3(
    monkeypatch: pytest.MonkeyPatch, provided: str, expected: str
) -> None:
    monkeypatch.setenv("DATABASE_URL", provided)
    assert Settings().sqlalchemy_url == expected
