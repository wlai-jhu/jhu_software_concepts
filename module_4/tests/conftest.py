import os
from pathlib import Path

import pytest

from src.load_data import CREATE_TABLE_SQL


SAMPLE_RECORDS = [
    {
        "entry_url": "https://example.test/entry/1",
        "university": "Johns Hopkins University",
        "program_name": "Computer Science",
        "date_added": "June 01, 2026",
        "applicant_status": "Accepted",
        "term": "Fall 2026",
        "student_origin": "American",
        "gpa": "3.90",
        "gre_score": "168",
        "gre_v_score": "164",
        "gre_aw": "5.0",
        "degree": "Masters",
        "comments": "Strong fit.",
    },
    {
        "entry_url": "https://example.test/entry/2",
        "university": "MIT",
        "program_name": "Computer Science",
        "date_added": "June 02, 2026",
        "applicant_status": "Rejected",
        "term": "Fall 2026",
        "student_origin": "International",
        "gpa": "3.70",
        "gre_score": "166",
        "gre_v_score": "160",
        "gre_aw": "4.5",
        "degree": "PhD",
        "comments": "",
    },
]


@pytest.fixture(scope="session", autouse=True)
def database_url():
    os.environ.setdefault("DATABASE_URL", "postgresql://wmacbookpro@localhost:5432/gradcafe")
    return os.environ["DATABASE_URL"]


@pytest.fixture()
def reset_db(database_url):
    import psycopg

    with psycopg.connect(database_url) as conn:
        with conn.cursor() as cur:
            cur.execute(CREATE_TABLE_SQL)
            cur.execute("TRUNCATE applicants;")
        conn.commit()
    return database_url


@pytest.fixture()
def sample_json_file(tmp_path):
    import json

    path = Path(tmp_path) / "records.json"
    path.write_text(json.dumps(SAMPLE_RECORDS), encoding="utf-8")
    return path


def count_applicants(database_url):
    import psycopg

    with psycopg.connect(database_url) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM applicants;")
            return cur.fetchone()[0]
