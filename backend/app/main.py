"""
CloudLeak FastAPI application entrypoint.

Serves the dashboard API consumed by the Next.js frontend. In this phase
only the app skeleton, CORS, and a health check exist — the spend and
resources routers are wired in during Phase 5.
"""

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("cloudleak")

app = FastAPI(
    title="CloudLeak API",
    description="Real-time AWS cost anomaly detection and remediation backend.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health_check():
    return {"status": "ok", "service": "cloudleak-api"}


@app.get("/")
def root():
    return {"message": "CloudLeak API is running. See /docs for API documentation."}
