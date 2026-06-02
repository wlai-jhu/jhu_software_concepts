import json
import importlib.util
import subprocess
import sys
import threading
import shutil
from pathlib import Path

from flask import Flask, flash, redirect, render_template, url_for

from load_data import load_applicants
from query_data import run_all_queries


BASE_DIR = Path(__file__).resolve().parent
PIPELINE_DIR = BASE_DIR / "pipeline"
SUBMITTED_DATA_PATH = BASE_DIR.parent / "module_2" / "llm_extend_applicant_data.json"

app = Flask(__name__)
app.secret_key = "module-3-gradcafe-analysis"

pull_lock = threading.Lock()
pull_state = {
    "running": False,
    "message": "No data pull is currently running.",
    "state": "idle",
}


def seed_scrape_output(scrape_output: Path) -> None:
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
    return all(
        importlib.util.find_spec(package_name) is not None
        for package_name in ("huggingface_hub", "llama_cpp")
    )


def run_data_pull() -> None:
    with pull_lock:
        pull_state["running"] = True
        pull_state["message"] = "Pull Data is running. This can take a while because Grad Cafe requests are delayed."
        pull_state["state"] = "running"

    try:
        scrape_output = PIPELINE_DIR / "data" / "raw_applicant_data.json"
        cleaned_output = PIPELINE_DIR / "applicant_data.json"
        llm_output = PIPELINE_DIR / "llm_extend_applicant_data.json"
        seed_scrape_output(scrape_output)

        existing_records = 0
        if scrape_output.exists():
            existing_records = len(json.loads(scrape_output.read_text(encoding="utf-8")))
        target_records = max(existing_records + 1000, 1000)
        commands = [
            [
                sys.executable,
                str(PIPELINE_DIR / "scrape.py"),
                "--target",
                str(target_records),
                "--delay",
                "3",
                "--stop-on-existing",
                "--parallel-pages",
                "16",
                "--output",
                str(scrape_output),
            ],
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
                "16",
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
        message = (
            f"Pull Data finished and reloaded {loaded:,} records into PostgreSQL. "
            f"{llm_message} Click Update Analysis to refresh the displayed results."
        )
        state = "ready"
    except Exception as exc:
        message = f"Pull Data stopped: {exc}"
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

        thread = threading.Thread(target=run_data_pull, daemon=True)
        thread.start()

    flash("Pull Data started. The page will show the latest status when refreshed.")
    return redirect(url_for("index"))


@app.post("/update-analysis")
def update_analysis():
    if pull_state["running"]:
        flash("Analysis was not updated because Pull Data is still running.")
    else:
        flash("Analysis refreshed with the latest database results.")
        pull_state["state"] = "idle"
        pull_state["message"] = "Analysis is up to date."
    return redirect(url_for("index"))


if __name__ == "__main__":
    app.run(debug=True)
