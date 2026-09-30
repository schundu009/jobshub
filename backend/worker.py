#!/usr/bin/env python3
"""
Celery worker entry point for Railway deployment.
Railway will run this file when NIXPACKS_START_CMD is not set.
"""
import os
import subprocess
import sys

if __name__ == "__main__":
    print("Starting Celery worker...")
    cmd = [
        "celery", "-A", "celery_app", "worker",
        "--loglevel=info",
        "--concurrency=2",
        "-Q", "default,scrapers_http,scrapers_orchestrator,maintenance,contracts"
    ]
    print(f"Running: {' '.join(cmd)}")
    sys.exit(subprocess.call(cmd))
