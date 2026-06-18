[CmdletBinding()]
param(
    [int]$Port = 55432
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$ComposeFile = Join-Path $ProjectRoot "infra\compose\docker-compose.persistence-test.yml"
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$ProjectName = "drone-u0-persistence-test"
$PreviousDatabaseUrl = $env:DATABASE_URL
$PreviousPort = $env:U0_POSTGRES_TEST_PORT
$PreviousPythonPath = $env:PYTHONPATH

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker is required to run the PostgreSQL migration smoke test."
}
if (-not (Test-Path -LiteralPath $Python)) {
    throw "Python environment not found at $Python."
}

try {
    $env:U0_POSTGRES_TEST_PORT = [string]$Port
    $env:DATABASE_URL = "postgresql+psycopg://u0_test:u0_test@127.0.0.1:$Port/drone_u0_test"

    & docker compose -p $ProjectName -f $ComposeFile up -d --wait postgres
    if ($LASTEXITCODE -ne 0) { throw "PostgreSQL test service failed to start." }

    & $Python -m alembic upgrade head
    if ($LASTEXITCODE -ne 0) { throw "Alembic upgrade failed." }
    & $Python -m alembic downgrade base
    if ($LASTEXITCODE -ne 0) { throw "Alembic downgrade failed." }
    & $Python -m alembic upgrade head
    if ($LASTEXITCODE -ne 0) { throw "Alembic second upgrade failed." }

    $InspectScript = @'
from sqlalchemy import create_engine, inspect
from app.models import Base
import os

engine = create_engine(os.environ["DATABASE_URL"])
try:
    actual = set(inspect(engine).get_table_names())
    expected = set(Base.metadata.tables) | {"alembic_version"}
    if actual != expected:
        raise SystemExit(f"table mismatch: expected={sorted(expected)}, actual={sorted(actual)}")
finally:
    engine.dispose()
'@
    $env:PYTHONPATH = "$ProjectRoot\apps\api;$ProjectRoot\src"
    & $Python -c $InspectScript
    if ($LASTEXITCODE -ne 0) { throw "PostgreSQL table inspection failed." }

    Write-Host "PostgreSQL migration smoke test passed."
}
finally {
    & docker compose -p $ProjectName -f $ComposeFile down --remove-orphans 2>$null
    if ($null -eq $PreviousDatabaseUrl) {
        Remove-Item Env:DATABASE_URL -ErrorAction SilentlyContinue
    } else {
        $env:DATABASE_URL = $PreviousDatabaseUrl
    }
    if ($null -eq $PreviousPort) {
        Remove-Item Env:U0_POSTGRES_TEST_PORT -ErrorAction SilentlyContinue
    } else {
        $env:U0_POSTGRES_TEST_PORT = $PreviousPort
    }
    if ($null -eq $PreviousPythonPath) {
        Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue
    } else {
        $env:PYTHONPATH = $PreviousPythonPath
    }
}
