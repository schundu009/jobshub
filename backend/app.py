# Railway auto-detection wrapper for FastAPI
from fastapi import FastAPI
from main import app

# Ensure FastAPI is detected
assert isinstance(app, FastAPI)

if __name__ == "__main__":
    import uvicorn
    import os
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("app:app", host="0.0.0.0", port=port)
