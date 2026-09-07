FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
# The application is stdlib-only; pytest is pre-installed for the tests_unit/ suite (there is no network at run time).
RUN pip install --no-cache-dir pytest==8.4.1
WORKDIR /app
COPY . /tmp/ctx
RUN set -e; \
    if [ -d /tmp/ctx/environment/app ]; then SRC=/tmp/ctx/environment/app; else SRC=/tmp/ctx/app; fi; \
    cp -a "$SRC/." /app/ && rm -rf /tmp/ctx && \
    find /app -name __pycache__ -type d -prune -exec rm -rf {} + && \
    rm -f /app/data/recon.db /app/data/recon.db-wal /app/data/recon.db-shm && \
    python scripts/load_ledger.py --customers data/customers.csv --invoices data/invoices.csv --db data/recon.db && \
    python -m pytest tests_unit -q -p no:cacheprovider --basetemp=/tmp/ut && \
    rm -rf /tmp/ut /tmp/pytest-of-root && \
    find /app -name __pycache__ -type d -prune -exec rm -rf {} +
