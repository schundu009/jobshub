#!/bin/bash
# Beat entrypoint with auto-restart on crash.

set -e

MAX_RESTARTS=100
RESTART_DELAY=5
restart_count=0

echo "Beat entrypoint: starting Celery beat with auto-restart (max=$MAX_RESTARTS)"

while [ $restart_count -lt $MAX_RESTARTS ]; do
    echo "Starting beat (attempt $((restart_count + 1))/$MAX_RESTARTS)..."

    celery -A celery_app beat \
        --loglevel=info \
        -s /app/data/celerybeat-schedule \
        || true

    exit_code=$?
    restart_count=$((restart_count + 1))

    echo "Beat exited with code $exit_code. Restarting in ${RESTART_DELAY}s... ($restart_count/$MAX_RESTARTS)"
    sleep $RESTART_DELAY
done

echo "Beat exceeded max restarts ($MAX_RESTARTS). Exiting."
exit 1
