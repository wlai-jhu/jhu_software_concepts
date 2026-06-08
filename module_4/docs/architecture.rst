Architecture
============

Web Layer
---------

``src.app`` exposes ``create_app(...)``. Tests can inject fake scraper, loader,
query, and busy-state objects so the Flask routes are deterministic and do not
touch the network.

ETL and Database Layer
----------------------

``src.load_data`` creates the required ``applicants`` table, normalizes raw
Grad Cafe records, and inserts them into PostgreSQL. The uniqueness policy is
based on the applicant entry URL. Duplicate pulls update existing rows instead
of creating duplicate records.

Query Layer
-----------

``src.query_data`` stores the analysis questions, SQL, explanations, and answer
formatting rules. Percentage answers are rendered with exactly two decimal
places and a percent sign.

Configuration
-------------

``src.db`` reads ``DATABASE_URL`` and opens PostgreSQL connections through
``psycopg``. Tests and CI override ``DATABASE_URL`` to isolate the test database.
