import subprocess
import sys
import threading
from pathlib import Path

from flask import Flask, flash, redirect, render_template, url_for

from load_data import load_applicants
from query_data import run_all_queries


BASE_DIR = Path(__file__).resolve().parent
REPO_DIR = BASE_DIR.parent
MODULE_2_DIR = REPO_DIR / "module_2"

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
        scrape_output = MODULE_2_DIR / "data" / "raw_applicant_data.json"
        commands = [
            [
                sys.executable,
                str(MODULE_2_DIR / "scrape.py"),
                "--target",
                "50000",
                "--delay",
                "3",
                "--resume",
                "--output",
                str(scrape_output),
            ],
            [
                sys.executable,
                str(MODULE_2_DIR / "clean.py"),
                "--input",
                str(scrape_output),
                "--output",
                str(MODULE_2_DIR / "applicant_data.json"),
            ],
        ]

        for command in commands:
            subprocess.run(command, cwd=MODULE_2_DIR, check=True)

        loaded = load_applicants(MODULE_2_DIR / "applicant_data.json", reset=True)
        message = f"Pull Data finished and reloaded {loaded:,} records into PostgreSQL."
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
