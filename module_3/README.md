# Module 3 - Database Queries Assignment

This folder loads the cleaned Module 2 Grad Cafe data into PostgreSQL, runs the required SQL analysis questions, and displays the results on a Flask webpage.

## Files

- `load_data.py`: creates the `applicants` table and loads cleaned JSON records.
- `query_data.py`: contains the SQL for all required questions plus two original questions.
- `app.py`: Flask analysis page with `Pull Data` and `Update Analysis` buttons.
- `templates/index.html` and `static/styles.css`: webpage layout and styling.
- `make_query_report.py`: creates `analysis_results.pdf` after the database is loaded.
- `make_limitations_pdf.py`: creates `limitations.pdf`.
- `requirements.txt`: packages needed for PostgreSQL, Flask, and the Module 2 scraper.

## Setup

Create or activate the project virtual environment, then install the Module 3 dependencies:

```bash
python -m pip install -r module_3/requirements.txt
```

Create a PostgreSQL database. The scripts default to:

```bash
postgresql://postgres:postgres@localhost:5432/gradcafe
```

To use a different database, set `DATABASE_URL` before running the scripts:

```bash
export DATABASE_URL="postgresql://USER:PASSWORD@localhost:5432/gradcafe"
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

The `Pull Data` button starts the Module 2 scraper and cleaner in the background, then reloads records into PostgreSQL. The `Update Analysis` button refreshes the page unless a data pull is already running.

## Written Reflection

Generate `limitations.pdf` with:

```bash
python make_limitations_pdf.py
```

## Screenshots

After running `query_data.py` and the Flask app, place screenshots of the console output and running webpage in the `screenshots` folder.
