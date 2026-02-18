# ---- Stage 1: builder -------------------------------------------------------
# Install dependencies in an isolated layer so the final image stays small.
FROM python:3.11-slim AS builder

WORKDIR /build

# Install build tools needed for some native extensions
RUN pip install --upgrade pip

COPY pyproject.toml .
# Generate a requirements file from pyproject.toml (prod deps only)
RUN pip install --no-cache-dir build wheel \
    && pip install --no-cache-dir \
        pydantic>=2.6 \
        fastapi>=0.110 \
        "uvicorn[standard]>=0.27" \
        sqlalchemy>=2.0 \
        alembic>=1.13 \
        psycopg2-binary>=2.9 \
        httpx>=0.27 \
        python-dotenv>=1.0 \
        "pydantic-settings>=2.2" \
        "anthropic>=0.40" \
    --target /install


# ---- Stage 2: runtime -------------------------------------------------------
FROM python:3.11-slim AS runtime

# Security: run as a non-root user
RUN groupadd --gid 1000 appuser && useradd --uid 1000 --gid appuser --shell /bin/bash appuser

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /install /usr/local/lib/python3.11/site-packages/

# Copy application source
COPY src/ ./src/
COPY main.py .
COPY alembic.ini .
COPY alembic/ ./alembic/

# Evidence directory — bind-mount in production
RUN mkdir -p /data/evidence && chown appuser:appuser /data/evidence

# Switch to non-root user
USER appuser

EXPOSE 8000

ENV PYTHONUNBUFFERED=1 \
    EVIDENCE_ROOT=/data/evidence

# Default: start the production server
CMD ["python", "main.py"]
