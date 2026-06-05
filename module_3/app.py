import json
import importlib.util
import multiprocessing
import subprocess
import sys
import threading
import shutil
from datetime import datetime, time
from pathlib import Path

from flask import Flask, flash, jsonify, redirect, render_template, url_for

from db import connect
from load_data import load_applicants
from query_data import run_all_queries


BASE_DIR = Path(__file__).resolve().parent
PIPELINE_DIR = BASE_DIR / "pipeline"
SUBMITTED_DATA_PATH = BASE_DIR.parent / "module_2" / "llm_extend_applicant_data.json"

app = Flask(__name__)
app.secret_key = "module-3-gradcafe-analysis"

# Shared state used by the background Pull Data thread and the status endpoint.
pull_lock = threading.Lock()
pull_state = {
    "running": False,
    "message": "No data pull is currently running.",
    "state": "idle",
    "last_entry_date": None,
    "last_entry_timestamp": None,
    "last_entry_label": None,
    "started_at": None,
}


def recommended_worker_count() -> int:
    """Use available CPU count to pick a practical concurrent page count."""
    cpu_count = multiprocessing.cpu_count()
    return max(4, min(32, cpu_count * 2))


def latest_database_entry_date():
    """Return the newest date_added currently loaded in PostgreSQL."""
    try:
        with connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT MAX(date_added) FROM applicants;")
                return cur.fetchone()[0]
    except Exception:
        return None


def timestamp_for_entry_date(entry_date):
    """Represent the date-only Grad Cafe field as a timestamp marker for status text."""
    if entry_date is None:
        return None
    return datetime.combine(entry_date, time.min)


def display_date(entry_date) -> str:
    if entry_date is None:
        return "unknown"
    return entry_date.strftime("%b %d, %Y")


def seed_scrape_output(scrape_output: Path) -> None:
    """Use the submitted Module 2 dataset as the baseline for incremental pulls."""
    if not SUBMITTED_DATA_PATH.exists():
        return

    scrape_output.parent.mkdir(parents=True, exist_ok=True)
    if not scrape_output.exists():
        shutil.copyfile(SUBMITTED_DATA_PATH, scrape_output)
        return

    submitted_records = json.loads(SUBMITTED_DATA_PATH.read_text(encoding="utf-8"))
    existing_records = json.loads(scrape_output.read_text(encoding="utf-8"))
    submitted_by_url = {
        record.get("entry_url"): record
        for record in submitted_records
        if record.get("entry_url")
    }
    merged_records = list(submitted_records)
    seen_urls = set(submitted_by_url)
    for record in existing_records:
        entry_url = record.get("entry_url")
        if entry_url and entry_url not in seen_urls:
            merged_records.append(record)
            seen_urls.add(entry_url)

    submitted_comments = sum(1 for record in submitted_records if (record.get("comments") or "").strip())
    existing_comments = sum(1 for record in existing_records if (record.get("comments") or "").strip())
    if len(merged_records) > len(existing_records) or submitted_comments > existing_comments:
        scrape_output.write_text(json.dumps(merged_records, indent=2), encoding="utf-8")


def llm_dependencies_available() -> bool:
    """Check optional local LLM packages before starting the slower model workflow."""
    return all(
        importlib.util.find_spec(package_name) is not None
        for package_name in ("huggingface_hub", "llama_cpp")
    )


def perform_data_pull(last_entry_date=None) -> tuple[str, str]:
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

        # The scraper stops early when a fetched batch overlaps with existing URLs, so this
        # target is a ceiling rather than a requirement to scrape another 1,000 records.
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

        # Comments live on entry detail pages, so they are enriched after the list scrape.
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
            # If local LLM dependencies are missing, the deterministic fallback keeps the
            # database load usable instead of failing the whole Pull Data action.
            llm_command = [
                sys.executable,
                str(PIPELINE_DIR / "llm_clean.py"),
                "--input",
                str(cleaned_output),
                "--output",
                str(llm_output),
            ]
            if llm_dependencies_available():
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
        message = (
            f"Pull Data complete. Reloaded {loaded:,} records. "
            f"{llm_message}{cutoff_message} Click Update Analysis to refresh results."
        )
        state = "ready"
    except Exception as exc:
        message = f"Pull Data stopped: {exc}"
        state = "error"

    return message, state


def run_data_pull_process(result_queue, last_entry_date) -> None:
    result_queue.put(perform_data_pull(last_entry_date=last_entry_date))


def monitor_data_pull(process, result_queue) -> None:
    process.join()
    try:
        message, state = result_queue.get_nowait()
    except Exception:
        message = f"Pull Data stopped: process exited with code {process.exitcode}."
        state = "error"

    with pull_lock:
        pull_state["running"] = False
        pull_state["message"] = message
        pull_state["state"] = state


@app.route("/")
def index():
    try:
        results = run_all_queries()
        db_error = None
    except Exception as exc:
        results = []
        db_error = str(exc)

    return render_template(
        "index.html",
        results=results,
        db_error=db_error,
        pull_state=pull_state.copy(),
    )


@app.post("/pull-data")
def pull_data():
    with pull_lock:
        if pull_state["running"]:
            flash("A data pull is already running. Update Analysis will wait until it finishes.")
            return redirect(url_for("index"))

        last_entry_date = latest_database_entry_date()
        last_entry_timestamp = timestamp_for_entry_date(last_entry_date)
        started_at = datetime.now().strftime("%b %d, %Y %I:%M %p")
        pull_state["running"] = True
        pull_state["message"] = (
            f"Pull Data is running. Checking for entries since {display_date(last_entry_date)}."
        )
        pull_state["state"] = "running"
        pull_state["last_entry_date"] = last_entry_date.isoformat() if last_entry_date else None
        pull_state["last_entry_timestamp"] = (
            last_entry_timestamp.strftime("%Y-%m-%d %H:%M:%S") if last_entry_timestamp else None
        )
        pull_state["last_entry_label"] = display_date(last_entry_date)
        pull_state["started_at"] = started_at
        result_queue = multiprocessing.Queue()
        process = multiprocessing.Process(
            target=run_data_pull_process,
            args=(result_queue, last_entry_date),
        )
        process.start()
        thread = threading.Thread(target=monitor_data_pull, args=(process, result_queue), daemon=True)
        thread.start()

    flash("Pull Data started. This page will refresh automatically until the pull finishes.")
    return redirect(url_for("index"))


@app.get("/pull-status")
def pull_status():
    with pull_lock:
        status = pull_state.copy()
    return jsonify(status)


@app.post("/update-analysis")
def update_analysis():
    with pull_lock:
        is_running = pull_state["running"]

    if is_running:
        flash("Analysis was not updated because Pull Data is still running.")
    else:
        flash("Analysis refreshed with the latest database results.")
        with pull_lock:
            pull_state["state"] = "idle"
            pull_state["message"] = "Analysis is up to date."
    return redirect(url_for("index"))


if __name__ == "__main__":
    app.run(debug=True)
