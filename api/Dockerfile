FROM python:3.12-slim

WORKDIR /app

# Manifest first so the dependency layer caches independently of source.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

# The eval harness ships in the image so a reviewer can run the suite without a
# local Python setup:
#
#   docker compose run --rm api python -m evals.run
#
# It resolves its fixture two levels above itself — /app/evals → /docs — which
# compose supplies as a read-only mount. Keeping the fixture out of the image
# means editing a case does not require a rebuild.
COPY evals ./evals

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
