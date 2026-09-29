#!/usr/bin/env python3
"""
Unified startup script for Railway deployment.

Set PROCESS_TYPE environment variable to control which process to run:
- web (default): Run the FastAPI web server
- worker: Run Celery worker
- beat: Run Celery beat scheduler
"""
import os
import subprocess
import sys

PROCESS_TYPE = os.environ.get("PROCESS_TYPE", "web")
PORT = os.environ.get("PORT", "8000")

if __name__ == "__main__":
    if PROCESS_TYPE == "worker":
        print("Starting Celery worker...")
        cmd = [
            "celery", "-A", "celery_app", "worker",
            "--loglevel=info",
            "--concurrency=2",
            "-Q", "default,scrapers_http,scrapers_orchestrator,maintenance"
        ]
    elif PROCESS_TYPE == "beat":
        print("Starting Celery beat scheduler...")
        cmd = [
            "celery", "-A", "celery_app", "beat",
            "--loglevel=info"
        ]
    else:
        print(f"Starting web server on port {PORT}...")
        cmd = [
            "python", "-m", "uvicorn", "main:app",
            "--host", "0.0.0.0",
            "--port", PORT,
            "--workers", os.environ.get("WEB_CONCURRENCY", "3"),
        ]

    print(f"Running: {' '.join(cmd)}")
    sys.exit(subprocess.call(cmd))
