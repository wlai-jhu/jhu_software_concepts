import pytest
from bs4 import BeautifulSoup

from src.app import BusyState, create_app, default_loader, default_scraper


def fake_results():
    return [
        {
            "key": "international_percent",
            "question": "What percentage of entries are international students?",
            "sql": "SELECT 50.00;",
            "explanation": "Fixture result.",
            "rows": [{"answer": 50.00}],
            "answer": "50.00%",
        }
    ]


@pytest.mark.web
def test_app_factory_exposes_required_routes():
    app = create_app(query_runner=fake_results, testing=True)

    rules = {rule.rule for rule in app.url_map.iter_rules()}

    assert "/" in rules
    assert "/analysis" in rules
    assert "/pull-data" in rules
    assert "/update-analysis" in rules
    assert "/pull-status" in rules


@pytest.mark.web
def test_get_analysis_renders_required_components():
    app = create_app(query_runner=fake_results, testing=True)

    response = app.test_client().get("/analysis")
    soup = BeautifulSoup(response.data, "html.parser")

    assert response.status_code == 200
    assert "Analysis" in soup.get_text(" ")
    assert soup.select_one('[data-testid="pull-data-btn"]').get_text(strip=True) == "Pull Data"
    assert soup.select_one('[data-testid="update-analysis-btn"]').get_text(strip=True) == "Update Analysis"
    assert "Answer:" in soup.get_text(" ")


@pytest.mark.web
def test_analysis_page_renders_fallback_when_query_fails():
    def broken_queries():
        raise RuntimeError("database offline")

    app = create_app(query_runner=broken_queries, testing=True)

    response = app.test_client().get("/analysis")
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "database offline" in text
    assert "Answer:" in text


@pytest.mark.web
def test_pull_status_reports_busy_state():
    state = BusyState()
    state.mark_running("Pull Data is running.")
    app = create_app(busy_state=state, testing=True)

    response = app.test_client().get("/pull-status")

    assert response.status_code == 200
    assert response.get_json()["running"] is True


@pytest.mark.web
def test_default_scraper_reads_configured_json(monkeypatch, tmp_path):
    path = tmp_path / "records.json"
    path.write_text('[{"entry_url": "https://example.test/default"}]', encoding="utf-8")
    monkeypatch.setattr("src.app.DEFAULT_DATA_PATH", path)

    assert default_scraper() == [{"entry_url": "https://example.test/default"}]


@pytest.mark.web
def test_default_loader_writes_temp_json_and_cleans_up(monkeypatch):
    captured = {}

    def fake_load_applicants(path, reset=False):
        captured["path"] = path
        captured["reset"] = reset
        captured["content"] = path.read_text(encoding="utf-8")
        return 1

    monkeypatch.setattr("src.app.load_applicants", fake_load_applicants)

    assert default_loader([{"entry_url": "https://example.test/default"}]) == 1
    assert captured["reset"] is False
    assert "https://example.test/default" in captured["content"]
    assert not captured["path"].exists()
