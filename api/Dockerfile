FROM python:3.12-slim

WORKDIR /app

# Manifest first so the dependency layer caches independently of source.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

# The eval harness and its fixture ship in the image, so a reviewer can run the
# suite without a local Python setup:
#
#   docker compose run --rm api python -m evals.run
COPY evals ./evals

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
