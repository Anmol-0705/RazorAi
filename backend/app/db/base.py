"""SQLAlchemy engine/session setup.

`DATABASE_URL` is read from the environment (loaded from a local `.env`
via python-dotenv if present — see `.env.example` at the repo root).
No default connection string with real credentials is baked in.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

_ENV_PATH = Path(__file__).resolve().parents[3] / ".env"
load_dotenv(_ENV_PATH)

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql+psycopg://postgres:postgres@localhost:5432/razorrecon"
)

# Hosted Postgres providers (e.g. Render) hand out plain
# "postgres://"/"postgresql://" connection strings with no driver
# specified, which SQLAlchemy resolves to psycopg2 — not installed
# here (this project pins psycopg3, see requirements.txt). Normalize
# so either form works without editing the URL by hand.
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = "postgresql+psycopg://" + DATABASE_URL[len("postgres://"):]
elif DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = "postgresql+psycopg://" + DATABASE_URL[len("postgresql://"):]

engine = create_engine(DATABASE_URL, pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


class Base(DeclarativeBase):
    pass


def get_db():
    """FastAPI dependency: yields a request-scoped session, always closed."""
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()
