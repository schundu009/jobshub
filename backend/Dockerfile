FROM python:3.11-slim

# Build ARG to bust cache when needed
ARG CACHE_BUST=20260310v5

WORKDIR /app

# Install system dependencies for Playwright
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    ca-certificates \
    fonts-liberation \
    libasound2 \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libatspi2.0-0 \
    libcups2 \
    libdbus-1-3 \
    libdrm2 \
    libgbm1 \
    libgtk-3-0 \
    libnspr4 \
    libnss3 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxkbcommon0 \
    libxrandr2 \
    xdg-utils \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN echo "Cache bust: $CACHE_BUST" && pip install --no-cache-dir -r requirements.txt

# Install Playwright browsers (deps already installed above)
RUN playwright install chromium

# Copy application code
COPY . .

# Expose port (Railway provides PORT env var)
EXPOSE 8000

# Start the application - use PORT env var for Railway, default to 8000.
# Multiple worker processes so one slow request can't stall the whole API.
# Startup migrations are guarded by a Postgres advisory lock (one worker runs them).
# PROMETHEUS_MULTIPROC_DIR: the workers share one metrics directory, emptied
# on boot, so /metrics reports all of them (observability/metrics.py).
CMD ["sh", "-c", "export PROMETHEUS_MULTIPROC_DIR=${PROMETHEUS_MULTIPROC_DIR:-/tmp/prometheus_multiproc} && rm -rf \"$PROMETHEUS_MULTIPROC_DIR\" && mkdir -p \"$PROMETHEUS_MULTIPROC_DIR\" && exec uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000} --workers ${WEB_CONCURRENCY:-3}"]
