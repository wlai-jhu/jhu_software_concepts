# Module 4 - Testing and Documentation

Name: Wade Lai  
JHED ID: wlai8

## Project

This module packages the Grad Cafe analytics application for automated testing and documentation. The Flask app exposes a testable `create_app(...)` factory, renders the `/analysis` page, supports `Pull Data` and `Update Analysis` button endpoints, loads applicant records into PostgreSQL, and computes the analysis answers used by the page. In normal browser use, `Pull Data` starts the same live scraper/clean/enrich/load pipeline pattern used in Module 3. In tests, fake scraper and loader functions keep the suite deterministic.

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

For a local Postgres.app-style setup, use your macOS username:

```bash
export DATABASE_URL="postgresql://$(whoami)@localhost:5432/gradcafe"
```

For a password-based local `postgres` user, use:

```bash
export DATABASE_URL="postgresql://postgres:postgres@localhost:5432/gradcafe"
```

The GitHub Actions workflow uses:

```text
postgresql://postgres:postgres@localhost:5432/gradcafe_test
```

Tests truncate and reload their database. Keep them pointed at a separate test
database:

```bash
createdb gradcafe_test
export TEST_DATABASE_URL="postgresql://$(whoami)@localhost:5432/gradcafe_test"
```

## Run the App

If the app is showing only the two test fixture rows, reload the application
database from the full Module 2 dataset:

```bash
export DATABASE_URL="postgresql://$(whoami)@localhost:5432/gradcafe"
python -m src.load_data --reset
```

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

Clicking `Pull Data` starts the live Module 3-style pipeline in a background
process. It can take a while because it checks Grad Cafe, refreshes comments,
runs deterministic LLM fallback cleanup when local model packages are missing,
and reloads PostgreSQL. Use `Update Analysis` after the status message says the
pull has completed.

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

The tests use `TEST_DATABASE_URL` when it is set. If it is not set, they will
fall back to a database named `gradcafe_test` and refuse to run against a
database whose name does not contain `test`.

The coverage gate is configured in `pytest.ini`:

```text
--cov=src --cov-report=term-missing --cov-fail-under=100
```

The committed coverage evidence is in `coverage_summary.txt`.

The retained live scraper pipeline under `src/pipeline/` is documented with
Sphinx but excluded from unit coverage because it performs live network
collection. The tested Flask routes use dependency injection with fake scraper
and loader functions so the suite stays fast and deterministic.

## Documentation

Build the Sphinx docs locally from the repository root:

```bash
cd module_4
sphinx-build -b html docs docs/_build/html
```

Or use the Sphinx Makefile:

```bash
cd module_4/docs
make html
```

If `sphinx-build` is not on your `PATH`, activate the Sphinx virtual environment first:

```bash
source ../../py3-sphinx/bin/activate
make html
```

Open:

```text
module_4/docs/_build/html/index.html
```

Read the Docs is configured by the repository-level `.readthedocs.yaml` file.

## CI

The workflow at `.github/workflows/tests.yml` starts PostgreSQL, installs dependencies, and runs the full marked Pytest suite with coverage. A copy is also kept at `module_4/.github/workflows/tests.yml` for the assignment folder deliverable.

After pushing to GitHub, capture a screenshot of a successful green run and save it as:

```text
module_4/actions_success.png
```
