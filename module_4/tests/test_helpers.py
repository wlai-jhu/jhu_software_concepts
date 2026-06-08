import builtins

import pytest

from src import db
from src.load_data import first_present, load_json, normalize_record, parse_date, parse_float
from src.query_data import empty_analysis_results, run_all_queries
from tests.conftest import SAMPLE_RECORDS


@pytest.mark.db
def test_loader_helpers_normalize_expected_variants(sample_json_file):
    record = {
        "url": "https://example.test/alternate",
        "university_cleaned": "Stanford University",
        "program_name_cleaned": "Computer Science",
        "status": "Accepted",
        "us_or_international": "Other",
        "gre": "GRE Q: 170",
        "gre_v": "GRE V: 165",
    }

    assert load_json(sample_json_file) == SAMPLE_RECORDS
    assert parse_date(None) is None
    assert parse_date("Jun 03, 2026") == "2026-06-03"
    assert parse_date("2026-06-04") == "2026-06-04"
    assert parse_date("not a date") is None
    assert parse_float(None) is None
    assert parse_float("") is None
    assert parse_float("missing") is None
    assert parse_float("GPA: 3.85") == 3.85
    assert first_present({"a": "", "b": "value"}, "a", "b") == "value"
    assert first_present({}, "missing") is None

    normalized = normalize_record(record, 10)

    assert normalized["p_id"] == 10
    assert normalized["program"] == "Stanford University - Computer Science"
    assert normalized["url"] == "https://example.test/alternate"
    assert normalized["gre"] == 170.0
    assert normalized["gre_v"] == 165.0


@pytest.mark.db
def test_generated_url_is_used_when_record_has_no_url():
    normalized = normalize_record({}, 42)

    assert normalized["url"] == "generated:42"
    assert normalized["program"] is None


@pytest.mark.analysis
def test_empty_analysis_and_run_all_queries(monkeypatch):
    calls = []

    def fake_run_query(question):
        calls.append(question.key)
        return {"key": question.key}

    monkeypatch.setattr("src.query_data.run_query", fake_run_query)

    results = run_all_queries()

    assert empty_analysis_results()[0]["answer"] == "No result"
    assert len(results) == len(calls)


@pytest.mark.db
def test_database_helpers_cover_default_and_import_error(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert db.database_url() == db.DEFAULT_DATABASE_URL

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "psycopg":
            raise ImportError("missing")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    with pytest.raises(RuntimeError, match="psycopg is not installed"):
        db.require_psycopg()
