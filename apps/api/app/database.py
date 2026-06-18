from __future__ import annotations

from collections.abc import Generator
import os
from pathlib import Path

from fastapi import Request
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker


DEFAULT_DATABASE_URL = "sqlite+pysqlite:///./var/u0.db"


def database_url() -> str:
    return os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)


def build_session_factory(url: str) -> sessionmaker[Session]:
    parsed = make_url(url)
    is_sqlite = parsed.get_backend_name() == "sqlite"
    if is_sqlite and parsed.database not in (None, ":memory:"):
        Path(parsed.database).parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(
        parsed,
        connect_args={"check_same_thread": False} if is_sqlite else {},
        pool_pre_ping=True,
    )
    return sessionmaker(bind=engine, class_=Session, expire_on_commit=False)


def session_dependency(request: Request) -> Generator[Session, None, None]:
    session = request.app.state.session_factory()
    request.state.db_session = session
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
