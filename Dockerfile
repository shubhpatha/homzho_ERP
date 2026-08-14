# ──────────────────────────────────────────────────────────────
# Homzho ERP — Dockerfile
# Target: GCP Cloud Run / GKE
# Runtime: Python 3.11-slim + Gunicorn
# ──────────────────────────────────────────────────────────────

# ── Base image ────────────────────────────────────────────────
FROM python:3.11-slim

# Metadata
LABEL maintainer="Homzho ERP" \
      description="Homzho ERP – Flask/Gunicorn production image"

# ── Environment variables ─────────────────────────────────────
# Prevents .pyc files and enables unbuffered stdout/stderr (important for GCP logging)
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    # Flask config
    FLASK_APP=app.py \
    FLASK_ENV=production \
    # Gunicorn will bind to this port; Cloud Run injects PORT=8080
    PORT=8080

# ── System dependencies ───────────────────────────────────────
# - gcc / libffi-dev: needed by some Python packages
# - libpq-dev: only if you ever migrate to PostgreSQL (safe to keep)
# - curl: used in health-check
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        libffi-dev \
        curl \
    && rm -rf /var/lib/apt/lists/*

# ── Create a non-root user for security ──────────────────────
RUN groupadd --gid 1001 appgroup && \
    useradd  --uid 1001 --gid appgroup --no-create-home appuser

# ── Working directory ─────────────────────────────────────────
WORKDIR /app

# ── Install Python dependencies ───────────────────────────────
# Copy requirements first to leverage Docker layer caching —
# if requirements.txt hasn't changed, pip install is skipped.
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# ── Copy application source ───────────────────────────────────
COPY . .

# ── Create runtime directories and set ownership ─────────────
# These are the directories the app writes to at runtime.
# On Cloud Run, mount a GCS FUSE bucket or Cloud Filestore here.
# On GKE / Compose, mount a persistent volume.
RUN mkdir -p \
        static/uploads/customers \
        static/uploads/maintenance \
        static/uploads/expenses \
        exports \
        backups \
        logs \
    && chown -R appuser:appgroup /app

# ── Switch to non-root user ───────────────────────────────────
USER appuser

# ── Declare volumes for persistent data ───────────────────────
# Database, uploads, exports and backups must survive container restarts.
VOLUME ["/app/static/uploads", "/app/exports", "/app/backups", "/app/logs"]

# ── Health check ──────────────────────────────────────────────
# GCP Load Balancer / Cloud Run uses this to determine readiness.
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:${PORT}/favicon.ico || exit 1

# ── Expose port ───────────────────────────────────────────────
EXPOSE ${PORT}

# ── Start Gunicorn ────────────────────────────────────────────
# Workers  = 2 × CPU + 1  (Cloud Run default: 1 vCPU → 3 workers)
# Threads  = 2             (allows concurrent requests per worker)
# Timeout  = 120s          (generous for PDF/export operations)
# --bind uses $PORT injected by Cloud Run (default 8080)
CMD ["sh", "-c", \
     "exec gunicorn \
        --bind 0.0.0.0:${PORT} \
        --workers ${GUNICORN_WORKERS:-3} \
        --threads ${GUNICORN_THREADS:-2} \
        --timeout ${GUNICORN_TIMEOUT:-120} \
        --log-level ${LOG_LEVEL:-error} \
        --access-logfile - \
        --error-logfile - \
        'app:create_app()'"]
