import pytest

from src.app import create_app
from src.load_data import load_applicants
from src.query_data import run_all_queries
from tests.conftest import SAMPLE_RECORDS, count_applicants


@pytest.mark.integration
def test_pull_update_render_end_to_end(reset_db, tmp_path):
    import json

    def scraper():
        return SAMPLE_RECORDS

    def loader(records):
        path = tmp_path / "records.json"
        path.write_text(json.dumps(list(records)), encoding="utf-8")
        return load_applicants(path, reset=False)

    app = create_app(scraper=scraper, loader=loader, query_runner=run_all_queries, testing=True)
    client = app.test_client()

    pull_response = client.post("/pull-data")
    update_response = client.post("/update-analysis")
    page_response = client.get("/analysis")

    assert pull_response.status_code == 200
    assert count_applicants(reset_db) == len(SAMPLE_RECORDS)
    assert update_response.status_code == 200
    text = page_response.get_data(as_text=True)
    assert "Answer:" in text
    assert "50.00%" in text


@pytest.mark.integration
def test_multiple_pulls_with_overlap_remain_unique(reset_db, tmp_path):
    import json

    call_count = {"value": 0}

    def scraper():
        call_count["value"] += 1
        if call_count["value"] == 1:
            return SAMPLE_RECORDS[:1]
        return SAMPLE_RECORDS

    def loader(records):
        path = tmp_path / f"records-{call_count['value']}.json"
        path.write_text(json.dumps(list(records)), encoding="utf-8")
        return load_applicants(path, reset=False)

    app = create_app(scraper=scraper, loader=loader, testing=True)
    client = app.test_client()

    assert client.post("/pull-data").status_code == 200
    assert client.post("/pull-data").status_code == 200
    assert count_applicants(reset_db) == len(SAMPLE_RECORDS)
