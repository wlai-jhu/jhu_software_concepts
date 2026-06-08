"""Flask application factory for the Grad Cafe analytics service."""

from __future__ import annotations

import json
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List

from flask import Flask, jsonify, redirect, render_template, request, url_for

from .load_data import load_applicants
from .query_data import empty_analysis_results, run_all_queries


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_DATA_PATH = BASE_DIR.parent.parent / "module_2" / "llm_extend_applicant_data.json"

Scraper = Callable[[], Iterable[Dict[str, Any]]]
Loader = Callable[[Iterable[Dict[str, Any]]], int]
QueryRunner = Callable[[], List[Dict[str, Any]]]


class BusyState:
    """Small observable state container used to gate button requests."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.running = False
        self.message = "No data pull is currently running."
        self.updated_at = None

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "running": self.running,
                "message": self.message,
                "updated_at": self.updated_at,
            }

    def mark_running(self, message: str) -> bool:
        with self._lock:
            if self.running:
                return False
            self.running = True
            self.message = message
            self.updated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
            return True

    def mark_idle(self, message: str) -> None:
        with self._lock:
            self.running = False
            self.message = message
            self.updated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")


def default_scraper() -> List[Dict[str, Any]]:
    """Read the submitted Module 2 records used as the deterministic local source."""

    with DEFAULT_DATA_PATH.open(encoding="utf-8") as handle:
        return json.load(handle)


def default_loader(records: Iterable[Dict[str, Any]]) -> int:
    """Load scraped records into PostgreSQL using the Module 3 schema."""

    record_list = list(records)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", delete=False) as handle:
        json.dump(record_list, handle)
        temp_path = Path(handle.name)

    try:
        return load_applicants(temp_path, reset=False)
    finally:
        temp_path.unlink(missing_ok=True)


def create_app(
    *,
    scraper: Scraper | None = None,
    loader: Loader | None = None,
    query_runner: QueryRunner | None = None,
    busy_state: BusyState | None = None,
    testing: bool = False,
) -> Flask:
    """Create a configured Flask app with injectable data and analysis dependencies."""

    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.config.update(TESTING=testing)
    state = busy_state or BusyState()
    scrape = scraper or default_scraper
    load = loader or default_loader
    queries = query_runner or run_all_queries
    app.extensions["busy_state"] = state

    def endpoint_response(payload: Dict[str, Any], status_code: int = 200):
        """Return JSON for tests/API clients and redirect browser form posts."""

        wants_json = (
            app.config["TESTING"]
            or request.accept_mimetypes.best == "application/json"
            or request.headers.get("X-Requested-With") == "XMLHttpRequest"
        )
        if wants_json:
            return jsonify(payload), status_code
        return redirect(url_for("analysis"))

    @app.get("/")
    @app.get("/analysis")
    def analysis():
        try:
            results = queries()
            db_error = None
        except Exception as exc:
            results = empty_analysis_results()
            db_error = str(exc)
        return render_template(
            "analysis.html",
            results=results,
            db_error=db_error,
            pull_state=state.snapshot(),
        )

    @app.post("/pull-data")
    def pull_data():
        if not state.mark_running("Pull Data is running."):
            return endpoint_response({"busy": True, "ok": False}, 409)
        try:
            records = list(scrape())
            inserted = load(records)
        except Exception as exc:
            state.mark_idle(f"Pull Data failed: {exc}")
            return endpoint_response({"ok": False, "error": str(exc)}, 500)
        state.mark_idle(f"Pull Data complete. Loaded {inserted} records.")
        return endpoint_response({"ok": True, "rows": inserted})

    @app.post("/update-analysis")
    def update_analysis():
        if state.snapshot()["running"]:
            return endpoint_response({"busy": True, "ok": False}, 409)
        state.mark_idle("Analysis refreshed with the latest database results.")
        return endpoint_response({"ok": True})

    @app.get("/pull-status")
    def pull_status():
        return jsonify(state.snapshot())

    return app


app = create_app()


if __name__ == "__main__":  # pragma: no cover
    app.run(debug=True)
