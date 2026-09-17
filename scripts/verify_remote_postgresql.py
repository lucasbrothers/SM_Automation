from __future__ import annotations

import argparse
import getpass
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from cmdb.repository import PostgresCMDBRepository, PostgresConnectionSettings


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify the remote PostgreSQL CMDB server and optionally initialize its schema."
    )
    parser.add_argument("--host", default="192.168.192.131")
    parser.add_argument("--port", type=int, default=5432)
    parser.add_argument("--database", default="postgres")
    parser.add_argument("--user", default="postgres")
    parser.add_argument("--password-env", default="SM_AUTOMATION_POSTGRES_PASSWORD")
    parser.add_argument("--sslmode", default="prefer")
    parser.add_argument(
        "--apply-schema",
        action="store_true",
        help="Create/update the CMDB schema on the remote database.",
    )
    args = parser.parse_args()

    password = os.environ.get(args.password_env)
    if not password:
        try:
            password = getpass.getpass(
                f"PostgreSQL password for {args.user}@{args.host}: "
            )
        except (EOFError, KeyboardInterrupt):
            print("\nPassword input cancelled.", file=sys.stderr)
            return 2

    os.environ[args.password_env] = password
    settings = PostgresConnectionSettings(
        host=args.host,
        port=args.port,
        database=args.database,
        user=args.user,
        password_env=args.password_env,
        sslmode=args.sslmode,
    )
    repository = PostgresCMDBRepository(settings)
    try:
        repository.connect()
        connection = repository._connection
        if connection is None:
            raise RuntimeError("PostgreSQL connection was not initialized.")
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT version(), current_database(), current_user, "
                "current_setting('server_version')"
            )
            version, database, user, server_version = cursor.fetchone()
            cursor.execute("SELECT pg_is_in_recovery()")
            in_recovery = cursor.fetchone()[0]
        print("[PASS] PostgreSQL connection")
        print(f"       server_version: {server_version}")
        print(f"       database: {database}")
        print(f"       user: {user}")
        print(f"       read_only_replica: {in_recovery}")

        if args.apply_schema:
            schema = (ROOT / "config" / "cmdb-schema.sql").read_text(encoding="utf-8")
            repository.initialize_schema(schema)
            print("[PASS] CMDB schema applied")
        return 0
    except Exception as exc:  # pragma: no cover - live connection script
        print(f"[FAIL] PostgreSQL verification: {exc}", file=sys.stderr)
        return 1
    finally:
        repository.close()
        os.environ.pop(args.password_env, None)


if __name__ == "__main__":
    raise SystemExit(main())
