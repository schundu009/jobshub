#!/bin/bash
# Worker entrypoint with auto-restart on crash.
# Celery workers can crash due to OOM, corrupted connections, or segfaults.
# This script ensures the workers always restart automatically.
#
# Two workers: the main one, and one that consumes only the "contracts" queue.
# Sharing one worker, the contract scrapes never ran: the hourly full-time
# scrape keeps hundreds of tasks queued, and the contracts queue starved behind
# them (24 scrape_all_contracts waiting, none received, 2026-09-30 to 10-05).

set -e

MAX_RESTARTS=100

# run_worker NAME CELERY_ARGS... : run a worker under its own restart loop.
run_worker() {
    local name=$1
    shift
    local restart_count=0
    local delay=5
    while [ $restart_count -lt $MAX_RESTARTS ]; do
        echo "Starting $name worker (attempt $((restart_count + 1))/$MAX_RESTARTS)..."
        celery -A celery_app worker --loglevel=info -n "$name@%h" "$@" || true
        restart_count=$((restart_count + 1))
        echo "$name worker exited. Restarting in ${delay}s... ($restart_count/$MAX_RESTARTS)"
        sleep $delay
        # Back off on repeated crashes
        if [ $restart_count -gt 5 ]; then delay=15; fi
        if [ $restart_count -gt 20 ]; then delay=30; fi
    done
    echo "$name worker exceeded max restarts ($MAX_RESTARTS)."
}

echo "Worker entrypoint: starting Celery workers with auto-restart (max=$MAX_RESTARTS)"

run_worker contracts \
    --concurrency=1 \
    --max-tasks-per-child=50 \
    --max-memory-per-child=512000 \
    -Q contracts &

run_worker main \
    --concurrency=4 \
    --max-tasks-per-child=50 \
    --max-memory-per-child=512000 \
    -Q default,scrapers_http,scrapers_browser,scrapers_orchestrator,maintenance

echo "Main worker exceeded max restarts. Exiting."
exit 1
