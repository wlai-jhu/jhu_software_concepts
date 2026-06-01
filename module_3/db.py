import os
from contextlib import contextmanager


DEFAULT_DATABASE_URL = "postgresql://postgres:postgres@localhost:5432/gradcafe"


def database_url() -> str:
    return os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL)


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
