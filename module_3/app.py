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
}


def run_data_pull() -> None:
    with pull_lock:
        pull_state["running"] = True
        pull_state["message"] = "Pull Data is running. This can take a while because Grad Cafe requests are delayed."

    try:
        scrape_output = PIPELINE_DIR / "data" / "raw_applicant_data.json"
        cleaned_output = PIPELINE_DIR / "applicant_data.json"
        llm_output = PIPELINE_DIR / "llm_extend_applicant_data.json"
        if not scrape_output.exists() and SUBMITTED_DATA_PATH.exists():
            scrape_output.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(SUBMITTED_DATA_PATH, scrape_output)

        existing_records = 0
        if scrape_output.exists():
            import json

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

        load_path = cleaned_output
        llm_message = "Downloaded fields were refreshed; LLM fields were not regenerated."
        try:
            subprocess.run(
                [
                    sys.executable,
                    str(PIPELINE_DIR / "llm_clean.py"),
                    "--input",
                    str(scrape_output),
                    "--output",
                    str(llm_output),
                    "--resume-llm",
                    "--llm-batch-size",
                    "1000",
                ],
                cwd=PIPELINE_DIR,
                check=True,
            )
            load_path = llm_output
            llm_message = "Downloaded and LLM-generated fields were refreshed."
        except Exception as exc:
            llm_message = (
                "Downloaded fields were refreshed. LLM regeneration did not complete, "
                f"so existing or fallback LLM values may be used: {exc}"
            )

        loaded = load_applicants(load_path, reset=True)
        message = f"Pull Data finished and reloaded {loaded:,} records into PostgreSQL. {llm_message}"
    except Exception as exc:
        message = f"Pull Data stopped: {exc}"

    with pull_lock:
        pull_state["running"] = False
        pull_state["message"] = message


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
    return redirect(url_for("index"))


if __name__ == "__main__":
    app.run(debug=True)
