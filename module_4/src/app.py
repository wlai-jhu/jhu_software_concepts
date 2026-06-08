"""Flask application factory for the Grad Cafe analytics service."""

from __future__ import annotations

import importlib.util
import json
import multiprocessing
import shutil
import subprocess
import sys
import tempfile
import threading
from datetime import datetime, time, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List

from flask import Flask, jsonify, redirect, render_template, request, url_for

from .load_data import load_applicants
from .query_data import empty_analysis_results, run_all_queries


BASE_DIR = Path(__file__).resolve().parent
PIPELINE_DIR = BASE_DIR / "pipeline"
DEFAULT_DATA_PATH = BASE_DIR.parent.parent / "module_2" / "llm_extend_applicant_data.json"

Scraper = Callable[[], Iterable[Dict[str, Any]]]
Loader = Callable[[Iterable[Dict[str, Any]]], int]
QueryRunner = Callable[[], List[Dict[str, Any]]]
LivePullStarter = Callable[["BusyState"], Dict[str, Any]]


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


def recommended_worker_count() -> int:  # pragma: no cover - live scraper tuning.
    cpu_count = multiprocessing.cpu_count()
    return max(4, min(32, cpu_count * 2))


def llm_dependencies_available() -> bool:  # pragma: no cover - depends on optional local packages.
    return all(
        importlib.util.find_spec(package_name) is not None
        for package_name in ("huggingface_hub", "llama_cpp")
    )


def display_date(entry_date) -> str:  # pragma: no cover - live status formatting.
    if entry_date is None:
        return "unknown"
    return entry_date.strftime("%b %d, %Y")


def latest_database_entry_date():  # pragma: no cover - live PostgreSQL status query.
    try:
        from .db import connect

        with connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT MAX(date_added) FROM applicants;")
                return cur.fetchone()[0]
    except Exception:
        return None


def timestamp_for_entry_date(entry_date):  # pragma: no cover - live status formatting.
    if entry_date is None:
        return None
    return datetime.combine(entry_date, time.min)


def seed_scrape_output(scrape_output: Path) -> None:  # pragma: no cover - live pipeline setup.
    if not DEFAULT_DATA_PATH.exists():
        return

    scrape_output.parent.mkdir(parents=True, exist_ok=True)
    if not scrape_output.exists():
        # Start live scraping from the submitted dataset so Pull Data preserves
        # the records already used by the assignment analysis.
        shutil.copyfile(DEFAULT_DATA_PATH, scrape_output)
        return

    submitted_records = json.loads(DEFAULT_DATA_PATH.read_text(encoding="utf-8"))
    existing_records = json.loads(scrape_output.read_text(encoding="utf-8"))
    merged_records = list(submitted_records)
    seen_urls = {record.get("entry_url") for record in submitted_records if record.get("entry_url")}
    for record in existing_records:
        entry_url = record.get("entry_url")
        if entry_url and entry_url not in seen_urls:
            merged_records.append(record)
            seen_urls.add(entry_url)

    if len(merged_records) > len(existing_records):
        scrape_output.write_text(json.dumps(merged_records, indent=2), encoding="utf-8")


def perform_live_data_pull(last_entry_date=None) -> tuple[str, str]:  # pragma: no cover - live network workflow.
    try:
        scrape_output = PIPELINE_DIR / "data" / "raw_applicant_data.json"
        cleaned_output = PIPELINE_DIR / "applicant_data.json"
        llm_output = PIPELINE_DIR / "llm_extend_applicant_data.json"
        seed_scrape_output(scrape_output)

        existing_records = 0
        if scrape_output.exists():
            existing_records = len(json.loads(scrape_output.read_text(encoding="utf-8")))
        target_records = max(existing_records + 1000, 1000)
        parallel_pages = recommended_worker_count()

        scrape_command = [
            sys.executable,
            str(PIPELINE_DIR / "scrape.py"),
            "--target",
            str(target_records),
            "--delay",
            "3",
            "--stop-on-existing",
            "--parallel-pages",
            str(parallel_pages),
            "--output",
            str(scrape_output),
        ]
        if last_entry_date:
            # Avoid re-scraping pages older than the newest row already loaded.
            scrape_command.extend(["--stop-before-date", last_entry_date.isoformat()])

        commands = [
            scrape_command,
            [
                sys.executable,
                str(PIPELINE_DIR / "clean.py"),
                "--input",
                str(scrape_output),
                "--output",
                str(cleaned_output),
            ],
        ]

        for command in commands:
            subprocess.run(command, cwd=PIPELINE_DIR, check=True)

        # Comment enrichment is separated from the first scrape/clean pass because
        # it can resume independently and is the slowest network-heavy step.
        subprocess.run(
            [
                sys.executable,
                str(PIPELINE_DIR / "enrich_comments.py"),
                "--input",
                str(cleaned_output),
                "--output",
                str(cleaned_output),
                "--start-index",
                str(existing_records),
                "--all-records",
                "--parallel-pages",
                str(parallel_pages),
                "--delay",
                "1",
                "--progress",
                str(PIPELINE_DIR / "data" / "comment_enrichment.progress.json"),
            ],
            cwd=PIPELINE_DIR,
            check=True,
        )

        load_path = cleaned_output
        llm_message = "Downloaded fields and comments were refreshed; LLM fields were not regenerated."
        try:
            llm_command = [
                sys.executable,
                str(PIPELINE_DIR / "llm_clean.py"),
                "--input",
                str(cleaned_output),
                "--output",
                str(llm_output),
            ]
            if llm_dependencies_available():
                # Use the local LLM only when its optional packages are installed;
                # otherwise llm_clean.py writes deterministic fallback fields.
                llm_command.extend(["--resume-llm", "--llm-batch-size", "1000"])
                llm_message = "Downloaded, comment, and LLM-generated fields were refreshed."
            else:
                llm_command.append("--skip-llm-run")
                llm_message = (
                    "Downloaded fields and comments were refreshed. Optional local LLM packages "
                    "are not installed, so deterministic fallback LLM fields were used."
                )
            subprocess.run(llm_command, cwd=PIPELINE_DIR, check=True)
            load_path = llm_output
        except Exception as exc:
            llm_message = (
                "Downloaded fields and comments were refreshed. LLM regeneration did not complete, "
                f"so existing or fallback LLM values may be used: {exc}"
            )

        loaded = load_applicants(load_path, reset=True)
        cutoff_message = f" Checked for entries since {display_date(last_entry_date)}."
        return (
            f"Pull Data complete. Reloaded {loaded:,} records. {llm_message}{cutoff_message} "
            "Click Update Analysis to refresh results.",
            "ready",
        )
    except Exception as exc:
        return f"Pull Data stopped: {exc}", "error"


def run_live_data_pull_process(result_queue, last_entry_date) -> None:  # pragma: no cover
    result_queue.put(perform_live_data_pull(last_entry_date=last_entry_date))


def monitor_live_data_pull(process, result_queue, state: BusyState) -> None:  # pragma: no cover
    process.join()
    try:
        message, _state_name = result_queue.get_nowait()
    except Exception:
        message = f"Pull Data stopped: process exited with code {process.exitcode}."
    state.mark_idle(message)


def start_live_data_pull(state: BusyState) -> Dict[str, Any]:  # pragma: no cover - starts long live process.
    last_entry_date = latest_database_entry_date()
    last_entry_timestamp = timestamp_for_entry_date(last_entry_date)
    message = f"Pull Data is running. Checking for entries since {display_date(last_entry_date)}."
    if not state.mark_running(message):
        return {"busy": True, "ok": False}

    result_queue = multiprocessing.Queue()
    # Run the live scraper outside the Flask request so the browser gets a quick
    # response while the long pipeline continues in the background.
    process = multiprocessing.Process(
        target=run_live_data_pull_process,
        args=(result_queue, last_entry_date),
    )
    process.start()
    thread = threading.Thread(
        target=monitor_live_data_pull,
        args=(process, result_queue, state),
        daemon=True,
    )
    thread.start()
    return {
        "ok": True,
        "running": True,
        "last_entry_timestamp": (
            last_entry_timestamp.strftime("%Y-%m-%d %H:%M:%S") if last_entry_timestamp else None
        ),
    }


def create_app(
    *,
    scraper: Scraper | None = None,
    loader: Loader | None = None,
    query_runner: QueryRunner | None = None,
    busy_state: BusyState | None = None,
    live_pull_starter: LivePullStarter | None = None,
    testing: bool = False,
) -> Flask:
    """Create a configured Flask app with injectable data and analysis dependencies."""

    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.config.update(TESTING=testing)
    state = busy_state or BusyState()
    scrape = scraper or default_scraper
    load = loader or default_loader
    queries = query_runner or run_all_queries
    live_starter = live_pull_starter or start_live_data_pull
    # Tests inject scraper/loader callables so they never run the live network pipeline.
    use_live_pull = scraper is None and loader is None
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
        if use_live_pull and not app.config["TESTING"]:
            payload = live_starter(state)
            status_code = 409 if payload.get("busy") else 200
            return endpoint_response(payload, status_code)

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
