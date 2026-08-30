# Backend API image. The analysis sandbox is a SEPARATE image
# (docker/Dockerfile.sandbox) and is launched per-run, not from here.

FROM python:3.11-slim

WORKDIR /app

# System deps: gcc for any source builds, libgomp1 for scipy/statsmodels (OpenMP).
RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

EXPOSE 8000

# Shell form so ${PORT} (set by Render/other PaaS) is expanded; falls back to 8000.
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
