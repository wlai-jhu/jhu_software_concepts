import pytest

from src.app import create_app
from src.load_data import load_applicants
from src.query_data import expected_result_keys, run_query
from tests.conftest import SAMPLE_RECORDS, count_applicants


@pytest.mark.db
def test_insert_on_pull_writes_required_non_null_fields(reset_db, sample_json_file):
    before = count_applicants(reset_db)

    loaded = load_applicants(sample_json_file, reset=False)

    import psycopg
    from psycopg.rows import dict_row

    with psycopg.connect(reset_db, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT p_id, program, date_added, url, status, term, us_or_international, degree
                FROM applicants
                ORDER BY p_id;
                """
            )
            rows = cur.fetchall()

    assert before == 0
    assert loaded == len(SAMPLE_RECORDS)
    assert len(rows) == len(SAMPLE_RECORDS)
    for row in rows:
        assert all(row[field] is not None for field in row)


@pytest.mark.db
def test_post_pull_data_writes_rows_to_database(reset_db, tmp_path):
    import json

    def loader(records):
        path = tmp_path / "posted-records.json"
        path.write_text(json.dumps(list(records)), encoding="utf-8")
        return load_applicants(path, reset=False)

    app = create_app(scraper=lambda: SAMPLE_RECORDS, loader=loader, testing=True)

    response = app.test_client().post("/pull-data")

    assert response.status_code == 200
    assert response.get_json() == {"ok": True, "rows": len(SAMPLE_RECORDS)}
    assert count_applicants(reset_db) == len(SAMPLE_RECORDS)


@pytest.mark.db
def test_duplicate_pull_does_not_duplicate_rows(reset_db, sample_json_file):
    load_applicants(sample_json_file, reset=False)
    load_applicants(sample_json_file, reset=False)

    assert count_applicants(reset_db) == len(SAMPLE_RECORDS)


@pytest.mark.db
def test_reset_load_replaces_existing_rows(reset_db, sample_json_file):
    load_applicants(sample_json_file, reset=False)

    loaded = load_applicants(sample_json_file, reset=True)

    assert loaded == len(SAMPLE_RECORDS)
    assert count_applicants(reset_db) == len(SAMPLE_RECORDS)


@pytest.mark.db
def test_query_function_returns_expected_keys(reset_db, sample_json_file):
    load_applicants(sample_json_file, reset=False)

    from src.query_data import ANALYSIS_QUESTIONS

    result = run_query(ANALYSIS_QUESTIONS[0])

    assert expected_result_keys() == set(result)
