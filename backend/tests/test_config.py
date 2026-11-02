import pytest
from pydantic import ValidationError

from app.config import Settings


@pytest.fixture
def database_environment(monkeypatch):
    values = {
        "POSTGRES_DB": "iot_noise",
        "POSTGRES_USER": "iot",
        "POSTGRES_PASSWORD": "example:@/with?symbols#",
        "DB_HOST": "db",
        "DB_PORT": "5432",
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)
    return values


def test_database_url_preserves_password_characters(database_environment):
    settings = Settings()

    assert settings.database_url.password == database_environment["POSTGRES_PASSWORD"]
    assert settings.database_url.host == "db"
    assert settings.database_url.port == 5432
    assert database_environment["POSTGRES_PASSWORD"] not in repr(settings)
    assert database_environment["POSTGRES_PASSWORD"] not in str(settings.database_url)


def test_database_password_is_required(database_environment, monkeypatch):
    monkeypatch.delenv("POSTGRES_PASSWORD")

    with pytest.raises(ValidationError):
        Settings()


@pytest.mark.parametrize("port", ["0", "65536", "not-a-port"])
def test_database_port_is_validated(database_environment, monkeypatch, port):
    monkeypatch.setenv("DB_PORT", port)

    with pytest.raises(ValidationError):
        Settings()
