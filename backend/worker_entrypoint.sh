#!/bin/bash
# Worker entrypoint with auto-restart on crash.
# Celery workers can crash due to OOM, corrupted connections, or segfaults.
# This script ensures the worker always restarts automatically.

set -e

MAX_RESTARTS=100
RESTART_DELAY=5
restart_count=0

echo "Worker entrypoint: starting Celery worker with auto-restart (max=$MAX_RESTARTS)"

while [ $restart_count -lt $MAX_RESTARTS ]; do
    echo "Starting worker (attempt $((restart_count + 1))/$MAX_RESTARTS)..."

    celery -A celery_app worker \
        --loglevel=info \
        --concurrency=4 \
        --max-tasks-per-child=50 \
        --max-memory-per-child=512000 \
        -Q default,scrapers_http,scrapers_browser,scrapers_orchestrator,maintenance \
        || true

    exit_code=$?
    restart_count=$((restart_count + 1))

    echo "Worker exited with code $exit_code. Restarting in ${RESTART_DELAY}s... ($restart_count/$MAX_RESTARTS)"
    sleep $RESTART_DELAY

    # Increase delay on repeated crashes (backoff)
    if [ $restart_count -gt 5 ]; then
        RESTART_DELAY=15
    fi
    if [ $restart_count -gt 20 ]; then
        RESTART_DELAY=30
    fi
done

echo "Worker exceeded max restarts ($MAX_RESTARTS). Exiting."
exit 1
