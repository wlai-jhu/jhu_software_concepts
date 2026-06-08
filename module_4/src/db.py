import os
from contextlib import contextmanager
from urllib.parse import urlparse


DEFAULT_DATABASE_URL = "postgresql://postgres:postgres@localhost:5432/gradcafe"


def database_url() -> str:
    url = os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL)
    parsed = urlparse(url)
    if parsed.username in {"USER", "USERNAME"} or parsed.password == "PASSWORD":
        raise RuntimeError(
            "DATABASE_URL still contains placeholder credentials. Use a real PostgreSQL "
            "connection string, such as postgresql://$(whoami)@localhost:5432/gradcafe "
            "for local Postgres.app or postgresql://postgres:postgres@localhost:5432/gradcafe "
            "for a password-based postgres user."
        )
    return url


def require_psycopg():
    try:
        import psycopg
    except ImportError as exc:
        raise RuntimeError(
            "psycopg is not installed. Run: python -m pip install -r requirements.txt"
        ) from exc
    return psycopg


@contextmanager
def connect(row_factory=None):
    psycopg = require_psycopg()
    kwargs = {}
    if row_factory is not None:
        kwargs["row_factory"] = row_factory
    with psycopg.connect(database_url(), **kwargs) as conn:
        yield conn
