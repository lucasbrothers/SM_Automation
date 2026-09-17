import pytest

from cmdb.repository import PostgresConnectionSettings


def test_postgres_settings_read_password_from_environment(monkeypatch):
    settings = PostgresConnectionSettings(
        host="db.internal",
        port=5432,
        database="cmdb",
        user="cmdb_app",
        password_env="CMDB_PASSWORD",
    )
    monkeypatch.setenv("CMDB_PASSWORD", "runtime-secret")

    kwargs = settings.connection_kwargs()

    assert kwargs == {
        "host": "db.internal",
        "port": 5432,
        "dbname": "cmdb",
        "user": "cmdb_app",
        "password": "runtime-secret",
        "sslmode": "verify-full",
    }


def test_postgres_settings_never_defaults_password(monkeypatch):
    monkeypatch.delenv("CMDB_PASSWORD", raising=False)
    settings = PostgresConnectionSettings(
        host="localhost",
        port=5432,
        database="cmdb",
        user="cmdb_app",
        password_env="CMDB_PASSWORD",
    )

    with pytest.raises(ValueError, match="environment variable is not set"):
        settings.connection_kwargs()
