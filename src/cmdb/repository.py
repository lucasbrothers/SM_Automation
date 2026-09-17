from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class PostgresConnectionSettings:
    """Store non-secret PostgreSQL connection settings."""

    host: str
    port: int
    database: str
    user: str
    password_env: str = "SM_AUTOMATION_CMDB_PASSWORD"
    sslmode: str = "verify-full"

    def connection_kwargs(self) -> dict[str, Any]:
        password = os.environ.get(self.password_env)
        if not password:
            raise ValueError(f"Database password environment variable is not set: {self.password_env}")
        return {
            "host": self.host,
            "port": self.port,
            "dbname": self.database,
            "user": self.user,
            "password": password,
            "sslmode": self.sslmode,
        }


class PostgresCMDBRepository:
    """Minimal PostgreSQL repository boundary for CMDB persistence."""

    def __init__(self, settings: PostgresConnectionSettings):
        self.settings = settings
        self._connection = None

    def connect(self) -> None:
        """Open a PostgreSQL connection using the optional psycopg package."""
        try:
            import psycopg
        except ImportError as exc:
            raise RuntimeError("Install psycopg[binary] to enable PostgreSQL CMDB access.") from exc
        self._connection = psycopg.connect(**self.settings.connection_kwargs())

    def close(self) -> None:
        if self._connection is not None:
            self._connection.close()
            self._connection = None

    def initialize_schema(self, schema_sql: str) -> None:
        """Apply an approved schema script on an open connection."""
        if self._connection is None:
            raise RuntimeError("PostgreSQL connection is not initialized.")
        with self._connection.cursor() as cursor:
            cursor.execute(schema_sql)
        self._connection.commit()
