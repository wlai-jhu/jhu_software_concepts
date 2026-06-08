import pytest

from src.app import BusyState, create_app


@pytest.mark.buttons
def test_pull_data_returns_ok_and_uses_scraper_rows():
    calls = {}

    def scraper():
        return [{"entry_url": "https://example.test/1"}]

    def loader(rows):
        calls["rows"] = list(rows)
        return len(calls["rows"])

    app = create_app(scraper=scraper, loader=loader, testing=True)

    response = app.test_client().post("/pull-data")

    assert response.status_code == 200
    assert response.get_json() == {"ok": True, "rows": 1}
    assert calls["rows"] == [{"entry_url": "https://example.test/1"}]


@pytest.mark.buttons
def test_pull_data_browser_form_redirects_to_analysis_page():
    app = create_app(scraper=lambda: [], loader=lambda rows: 0)

    response = app.test_client().post("/pull-data", headers={"Accept": "text/html"})

    assert response.status_code == 302
    assert response.headers["Location"] == "/analysis"


@pytest.mark.buttons
def test_update_analysis_returns_ok_when_not_busy():
    app = create_app(testing=True)

    response = app.test_client().post("/update-analysis")

    assert response.status_code == 200
    assert response.get_json() == {"ok": True}


@pytest.mark.buttons
def test_update_analysis_browser_form_redirects_to_analysis_page():
    app = create_app()

    response = app.test_client().post("/update-analysis", headers={"Accept": "text/html"})

    assert response.status_code == 302
    assert response.headers["Location"] == "/analysis"


@pytest.mark.buttons
def test_busy_state_gates_update_and_pull_without_work():
    state = BusyState()
    state.mark_running("Pull Data is running.")
    calls = {"loader": 0}

    def loader(rows):
        calls["loader"] += 1
        return len(list(rows))

    app = create_app(loader=loader, busy_state=state, testing=True)
    client = app.test_client()

    update_response = client.post("/update-analysis")
    pull_response = client.post("/pull-data")

    assert update_response.status_code == 409
    assert update_response.get_json() == {"busy": True, "ok": False}
    assert pull_response.status_code == 409
    assert pull_response.get_json() == {"busy": True, "ok": False}
    assert calls["loader"] == 0


@pytest.mark.buttons
def test_loader_error_returns_500_and_releases_busy_state():
    state = BusyState()

    def loader(rows):
        raise ValueError("load failed")

    app = create_app(scraper=lambda: [{"entry_url": "x"}], loader=loader, busy_state=state, testing=True)

    response = app.test_client().post("/pull-data")

    assert response.status_code == 500
    assert response.get_json() == {"error": "load failed", "ok": False}
    assert state.snapshot()["running"] is False
