# Railway auto-detection wrapper for FastAPI
# This file helps Railway's Railpack builder detect and run the FastAPI app

from main import app

# Railway will automatically run: uvicorn app:app --host 0.0.0.0 --port $PORT
