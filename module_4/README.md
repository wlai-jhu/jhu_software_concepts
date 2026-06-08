# Module 4 - Testing and Documentation

Name: Wade Lai  
JHED ID: wlai8

## Project

This module packages the Grad Cafe analytics application for automated testing and documentation. The Flask app exposes a testable `create_app(...)` factory, renders the `/analysis` page, supports `Pull Data` and `Update Analysis` button endpoints, loads applicant records into PostgreSQL, and computes the analysis answers used by the page.

Repository SSH URL:

```text
git@github.com:wlai-jhu/jhu_software_concepts.git
```

Read the Docs URL:

```text
Add the published Read the Docs link here after connecting the GitHub repository.
```

## Setup

Create or activate the project virtual environment, then install dependencies:

```bash
python -m pip install -r module_4/requirements.txt
```

Set a PostgreSQL connection string with `DATABASE_URL`. Do not copy placeholder
values like `USER` or `PASSWORD` literally.

For this Mac's local Postgres.app-style setup, use:

```bash
export DATABASE_URL="postgresql://wmacbookpro@localhost:5432/gradcafe"
```

For a password-based local `postgres` user, use:

```bash
export DATABASE_URL="postgresql://postgres:postgres@localhost:5432/gradcafe"
```

The GitHub Actions workflow uses:

```text
postgresql://postgres:postgres@localhost:5432/gradcafe_test
```

## Run the App

From the repository root:

```bash
python -m flask --app module_4.src.app run
```

If your terminal is already inside `module_4`, use:

```bash
python -m flask --app src.app run
```

Open:

```text
http://127.0.0.1:5000/analysis
```

The page includes stable selectors for tests:

```text
data-testid="pull-data-btn"
data-testid="update-analysis-btn"
data-testid="analysis-results"
```

## Run Tests

From `module_4`:

```bash
pytest -m "web or buttons or analysis or db or integration"
```

The coverage gate is configured in `pytest.ini`:

```text
--cov=src --cov-report=term-missing --cov-fail-under=100
```

The committed coverage evidence is in `coverage_summary.txt`.

## Documentation

Build the Sphinx docs locally:

```bash
cd module_4
sphinx-build -b html docs docs/_build/html
```

Open:

```text
module_4/docs/_build/html/index.html
```

## CI

The workflow at `.github/workflows/tests.yml` starts PostgreSQL, installs dependencies, and runs the full marked Pytest suite with coverage. A copy is also kept at `module_4/.github/workflows/tests.yml` for the assignment folder deliverable.

After pushing to GitHub, capture a screenshot of a successful green run and save it as:

```text
module_4/actions_success.png
```
