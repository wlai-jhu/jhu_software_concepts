Overview and Setup
==================

Install dependencies from the repository root:

.. code-block:: bash

   python -m pip install -r module_4/requirements.txt

Optional isolated Sphinx environment:

.. code-block:: bash

   python -m venv py3-sphinx
   source py3-sphinx/bin/activate
   python -m pip install -r module_4/requirements.txt

Confirm Sphinx is available:

.. code-block:: bash

   sphinx-build --help

Configure PostgreSQL with ``DATABASE_URL``. Do not copy placeholder values like
``USER`` or ``PASSWORD`` literally.

For a local Postgres.app-style setup, use your macOS username:

.. code-block:: bash

   export DATABASE_URL="postgresql://$(whoami)@localhost:5432/gradcafe"

For a password-based local ``postgres`` user, use:

.. code-block:: bash

   export DATABASE_URL="postgresql://postgres:postgres@localhost:5432/gradcafe"

Tests truncate and reload their database. Keep them pointed at a separate test
database:

.. code-block:: bash

   createdb gradcafe_test
   export TEST_DATABASE_URL="postgresql://$(whoami)@localhost:5432/gradcafe_test"

Run the Flask application:

If the app is showing only the two test fixture rows, reload the application
database from the full Module 2 dataset:

.. code-block:: bash

   export DATABASE_URL="postgresql://$(whoami)@localhost:5432/gradcafe"
   python -m src.load_data --reset

From the repository root:

.. code-block:: bash

   python -m flask --app module_4.src.app run

Open ``http://127.0.0.1:5000/analysis``.

Run tests from ``module_4``:

.. code-block:: bash

   pytest -m "web or buttons or analysis or db or integration"

The tests use ``TEST_DATABASE_URL`` when it is set. If it is not set, they fall
back to a database named ``gradcafe_test`` and refuse to run against a database
whose name does not contain ``test``.

Build this documentation:

.. code-block:: bash

   cd module_4
   sphinx-build -b html docs docs/_build/html

You can also use the generated Sphinx Makefile:

.. code-block:: bash

   cd module_4/docs
   make html

If ``sphinx-build`` is not on your ``PATH``, activate the virtual environment
first or call Sphinx through Python:

.. code-block:: bash

   source ../../py3-sphinx/bin/activate
   make html

The local HTML entry point is ``module_4/docs/_build/html/index.html``.

Read the Docs uses the repository-level ``.readthedocs.yaml`` file and the
Sphinx configuration at ``module_4/docs/conf.py``.
