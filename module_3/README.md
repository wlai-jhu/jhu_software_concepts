# Module 3 - Database Queries Assignment

This folder loads the cleaned Module 2 Grad Cafe data into PostgreSQL, runs the required SQL analysis questions, and displays the results on a Flask webpage.

## Files

- `load_data.py`: creates the `applicants` table and loads cleaned JSON records.
- `query_data.py`: contains the SQL for all required questions plus two original questions.
- `app.py`: Flask analysis page with `Pull Data` and `Update Analysis` buttons.
- `templates/index.html` and `static/styles.css`: webpage layout and styling.
- `make_query_report.py`: creates `analysis_results.pdf` after the database is loaded.
- `make_limitations_pdf.py`: creates `limitations.pdf`.
- `pipeline/`: local Module 3 copy of the scraper, cleaner, and LLM standardization code used by the `Pull Data` button.
- `requirements.txt`: packages needed for PostgreSQL, Flask, and the Module 2 scraper.

## Setup

Create or activate the project virtual environment, then install the Module 3 dependencies:

```bash
python -m pip install -r module_3/requirements.txt
```

Install and start PostgreSQL before loading data. On macOS, the simplest local option is
[Postgres.app](https://postgresapp.com/). After opening Postgres.app, start the server and
create the `gradcafe` database:

```bash
/Applications/Postgres.app/Contents/Versions/latest/bin/createdb gradcafe
```

Create a PostgreSQL database. The scripts default to:

```bash
postgresql://postgres:postgres@localhost:5432/gradcafe
```

To use a different database, set `DATABASE_URL` before running the scripts:

```bash
export DATABASE_URL="postgresql://USER:PASSWORD@localhost:5432/gradcafe"
```

On this Mac, the local Postgres.app-style connection string is expected to be:

```bash
export DATABASE_URL="postgresql://wmacbookpro@localhost:5432/gradcafe"
```

## Load Data

From the `module_3` folder:

```bash
python load_data.py --reset
```

By default, this loads:

```text
../module_2/llm_extend_applicant_data.json
```

## Run SQL Analysis

```bash
python query_data.py
```

To create the PDF with query answers, SQL, and explanations:

```bash
python make_query_report.py
```

## Run the Flask Webpage

```bash
flask --app app run
```

Open the local URL printed by Flask, usually:

```text
http://127.0.0.1:5000
```

The Module 1 portfolio projects page also links to this local Module 3 analysis app from:

```text
http://127.0.0.1:8080/projects
```

For that link to open the analysis page, run the Module 1 portfolio server on port 8080 and this Module 3 Flask app on port 5000 at the same time.

The `Pull Data` button starts the Module 3 scraper pipeline in the background, preserves the enriched submitted dataset as the baseline, stops once newly fetched Grad Cafe pages overlap with existing records, attempts to refresh LLM-standardized fields, and then reloads records into PostgreSQL. If the LLM step cannot complete, the page reports the fallback and still reloads the downloaded/cleaned fields so the database remains usable.

The `Update Analysis` button refreshes the page unless a data pull is already running.

## Written Reflection

Generate `limitations.pdf` with:

```bash
python make_limitations_pdf.py
```

## Screenshots

After running `query_data.py` and the Flask app, place screenshots of the console output and running webpage in the `screenshots` folder.
