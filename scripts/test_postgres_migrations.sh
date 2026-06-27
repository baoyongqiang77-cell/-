#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
compose_file="$project_root/infra/compose/docker-compose.persistence-test.yml"
python_bin="${PYTHON:-$project_root/.venv/bin/python}"
project_name="drone-u1-f02-persistence-test"
port="${U0_POSTGRES_TEST_PORT:-55432}"

command -v docker >/dev/null
test -x "$python_bin"

cleanup() {
  docker compose -p "$project_name" -f "$compose_file" down --remove-orphans >/dev/null 2>&1 || true
}
trap cleanup EXIT

export U0_POSTGRES_TEST_PORT="$port"
export DATABASE_URL="postgresql+psycopg://u0_test:u0_test@127.0.0.1:$port/drone_u0_test"
export PYTHONPATH="$project_root/apps/api:$project_root/src"

docker compose -p "$project_name" -f "$compose_file" up -d --wait postgres
"$python_bin" -m alembic upgrade head
"$python_bin" -m alembic downgrade base
"$python_bin" -m alembic upgrade head
"$python_bin" - <<'PY'
import os

from sqlalchemy import create_engine, inspect

from app.models import Base

engine = create_engine(os.environ["DATABASE_URL"])
try:
    actual = set(inspect(engine).get_table_names())
    expected = set(Base.metadata.tables) | {"alembic_version"}
    if actual != expected:
        raise SystemExit(
            f"table mismatch: expected={sorted(expected)}, actual={sorted(actual)}"
        )
finally:
    engine.dispose()
PY
echo "PostgreSQL migration smoke test passed."
