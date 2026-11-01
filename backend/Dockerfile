FROM python:3.13-slim-bookworm AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && useradd --create-home --uid 10001 app

FROM base AS runtime

COPY app ./app
USER app
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port \"${BACKEND_PORT:-8000}\""]
