FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FIA_DB_PATH=/data/fia.sqlite3

WORKDIR /app

COPY pyproject.toml README.md ./
COPY fia ./fia
RUN pip install --no-cache-dir .

RUN mkdir -p /data

EXPOSE 8000
CMD ["sh", "-c", "uvicorn fia.api:app --host 0.0.0.0 --port ${PORT:-8000}"]
