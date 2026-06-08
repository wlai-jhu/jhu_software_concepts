Overview and Setup
==================

Install dependencies from the repository root:

.. code-block:: bash

   python -m pip install -r module_4/requirements.txt

Configure PostgreSQL with ``DATABASE_URL``. Do not copy placeholder values like
``USER`` or ``PASSWORD`` literally.

For this Mac's local Postgres.app-style setup, use:

.. code-block:: bash

   export DATABASE_URL="postgresql://wmacbookpro@localhost:5432/gradcafe"

For a password-based local ``postgres`` user, use:

.. code-block:: bash

   export DATABASE_URL="postgresql://postgres:postgres@localhost:5432/gradcafe"

Run the Flask application:

.. code-block:: bash

   python -m flask --app module_4.src.app run

Open ``http://127.0.0.1:5000/analysis``.

Run tests from ``module_4``:

.. code-block:: bash

   pytest -m "web or buttons or analysis or db or integration"

Build this documentation:

.. code-block:: bash

   cd module_4
   sphinx-build -b html docs docs/_build/html
