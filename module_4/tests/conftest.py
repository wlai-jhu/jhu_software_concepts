import os
import getpass
from pathlib import Path
from urllib.parse import urlparse

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
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        configured_url = os.environ.get("DATABASE_URL", "")
        url = (
            configured_url
            if "test" in Path(urlparse(configured_url).path).name
            else f"postgresql://{getpass.getuser()}@localhost:5432/gradcafe_test"
        )
    dbname = Path(urlparse(url).path).name
    if "test" not in dbname:
        raise RuntimeError(
            f"Refusing to run destructive tests against non-test database {dbname!r}. "
            "Set TEST_DATABASE_URL to a database name containing 'test'."
        )
    os.environ["DATABASE_URL"] = url
    return url


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
