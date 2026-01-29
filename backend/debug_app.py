"""
Minimal debug app to test Railway deployment.
"""
from fastapi import FastAPI

app = FastAPI()

@app.get("/")
def root():
    return {"status": "debug_app_running"}

@app.get("/health")
def health():
    return {"status": "healthy", "app": "debug"}
