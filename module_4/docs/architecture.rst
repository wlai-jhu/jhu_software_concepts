Architecture
============

Web Layer
---------

``src.app`` exposes ``create_app(...)``. Tests can inject fake scraper, loader,
query, and busy-state objects so the Flask routes are deterministic and do not
touch the network. In normal browser use, ``POST /pull-data`` starts a
background Module 3-style live pipeline process and ``GET /pull-status`` reports
progress back to the page.

ETL and Database Layer
----------------------

``src.pipeline.scrape`` and ``src.pipeline.clean`` retain the Module 3 scraping
and cleaning workflow. ``src.load_data`` creates the required ``applicants``
table, normalizes raw Grad Cafe records, and inserts them into PostgreSQL. The
uniqueness policy is based on the applicant entry URL. Duplicate pulls update
existing rows instead of creating duplicate records.

Query Layer
-----------

``src.query_data`` stores the analysis questions, SQL, explanations, and answer
formatting rules. Percentage answers are rendered with exactly two decimal
places and a percent sign.

Configuration
-------------

``src.db`` reads ``DATABASE_URL`` and opens PostgreSQL connections through
``psycopg``. Tests and CI override ``DATABASE_URL`` to isolate the test database.
