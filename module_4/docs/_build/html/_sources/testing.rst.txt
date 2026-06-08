Testing Guide
=============

The test suite lives under ``module_4/tests`` and uses Flask's test client.
There are no live scrapes, browser clicks, or sleeps in the tests.

Markers
-------

Every test is marked with at least one assignment marker:

* ``web`` for Flask route and HTML structure tests.
* ``buttons`` for Pull Data, Update Analysis, and busy-state tests.
* ``analysis`` for answer labels and percentage formatting.
* ``db`` for schema, insert, idempotency, and query tests.
* ``integration`` for end-to-end pull, update, and render flows.

Run the full marked suite:

.. code-block:: bash

   pytest -m "web or buttons or analysis or db or integration"

Selectors
---------

The page includes stable selectors:

* ``data-testid="pull-data-btn"``
* ``data-testid="update-analysis-btn"``
* ``data-testid="pull-status"``
* ``data-testid="analysis-results"``
* ``data-testid="analysis-card"``

Fixtures and Test Doubles
-------------------------

The tests inject fake scraper and loader functions into ``create_app(...)``.
Database tests use a small deterministic sample record set and truncate the
``applicants`` table before each database test.
