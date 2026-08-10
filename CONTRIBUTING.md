# Contributing

Use Python 3.10+ and install the development extras:

    python -m pip install -e '.[server,dev]'

Before submitting a change, add offline TDD coverage and run:

    ruff format --check .
    ruff check .
    mypy src
    python -m pytest -q
    python -m build
    vidsnap conformance

Do not commit credentials, local media, datasets, generated RunBundles, benchmark outputs, cookies, or .env files. Changes may not introduce SaaS state, databases, queues, accounts, arbitrary model routing, or a frontend.
