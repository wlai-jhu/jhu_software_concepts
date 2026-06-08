Operational Notes
=================

Busy State Policy
-----------------

The app uses a small observable ``BusyState`` object. If a pull is running,
``POST /pull-data`` and ``POST /update-analysis`` return HTTP 409 with
``{"busy": true, "ok": false}``.

In normal browser use, ``Pull Data`` starts the live scraper/clean/enrich/load
pipeline in a background process, then redirects back to the analysis page.
The status endpoint reports when the process finishes. In tests, the same route
uses injected fakes so the suite never depends on a live network scrape.

Idempotency Strategy
--------------------

The PostgreSQL table uses ``url text UNIQUE``. Inserts use ``ON CONFLICT (url)``
to update existing rows, so repeated pulls with overlapping records keep one row
per Grad Cafe entry URL.

Troubleshooting
---------------

If tests cannot connect to PostgreSQL, confirm that the server is running and
that ``DATABASE_URL`` points to the test database. In CI, the workflow creates a
PostgreSQL service and sets ``DATABASE_URL`` automatically.

If Sphinx cannot import modules, run the build from ``module_4`` so ``docs/conf.py``
can add the module folder to ``sys.path``.
