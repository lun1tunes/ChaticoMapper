# syntax=docker/dockerfile:1.4

# ============================================================================
# Stage 1: Builder - Install dependencies
# ============================================================================
FROM python:3.13-slim AS builder

# Prevent Python from writing pyc files and buffering stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    POETRY_VERSION=1.8.3 \
    POETRY_HOME=/opt/poetry \
    POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_IN_PROJECT=true \
    POETRY_VIRTUALENVS_CREATE=true

# Install system dependencies required for building Python packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Set work directory
WORKDIR /app

# Copy dependency files (README.md is required by Poetry build system)
COPY pyproject.toml poetry.lock README.md ./

# Create virtual environment and install dependencies only
# Project uses package-mode=false, so we just install dependencies
RUN python -m venv /app/.venv && \
    /app/.venv/bin/pip install --upgrade pip setuptools wheel && \
    /app/.venv/bin/pip install $(python -c "import tomllib; f=open('pyproject.toml','rb'); data=tomllib.load(f); print(' '.join([dep.split('[')[0] for dep in data['project']['dependencies']]))")

# ============================================================================
# Stage 2: Runtime - Lightweight production image
# ============================================================================
FROM python:3.13-slim AS runtime

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PATH="/app/.venv/bin:$PATH"

# Install runtime dependencies only
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user for security
RUN groupadd -r chatico && \
    useradd -r -g chatico -u 1000 -d /app -s /bin/bash chatico && \
    mkdir -p /app/logs && \
    chown -R chatico:chatico /app

# Set work directory
WORKDIR /app

# Copy virtual environment from builder stage
COPY --from=builder --chown=chatico:chatico /app/.venv /app/.venv

# Copy application code
COPY --chown=chatico:chatico src/ ./src/
COPY --chown=chatico:chatico database/ ./database/
COPY --chown=chatico:chatico pyproject.toml poetry.lock ./

# Switch to non-root user
USER chatico

# Expose application port
EXPOSE 8100

# Run migrations and start application
CMD ["sh", "-c", "cd database && alembic upgrade head && cd .. && uvicorn src.main:app --host 0.0.0.0 --port ${PORT:-8100} --workers 1"]
