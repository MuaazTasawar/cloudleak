"""
CloudLeak FastAPI application entrypoint.

Serves the dashboard API consumed by the Next.js frontend. Adds a global
exception handler (Phase 9) so an unexpected error anywhere in a route
returns a clean JSON error instead of a raw 500 traceback, plus a startup
check that warns loudly in the logs if AWS credentials aren't configured
— that failure mode ("everything 500s, unclear why") is exactly the kind
of thing worth catching early instead of discovering it through a stack
trace three layers deep.
"""

import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.routers import resources, spend

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

app.include_router(spend.router)
app.include_router(resources.router)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={
            "detail": "An unexpected error occurred. Check the server logs for details.",
            "path": str(request.url.path),
        },
    )


@app.on_event("startup")
async def check_configuration():
    warnings = []

    if not settings.AWS_ACCESS_KEY_ID or not settings.AWS_SECRET_ACCESS_KEY:
        warnings.append(
            "AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY are not set — "
            "all AWS-backed endpoints (spend, resources) will fail until backend/.env is filled in."
        )

    if not settings.SLACK_WEBHOOK_URL:
        warnings.append(
            "SLACK_WEBHOOK_URL is not set — anomaly and remediation alerts will be logged only, not sent to Slack."
        )

    if warnings:
        logger.warning("CloudLeak started with incomplete configuration:")
        for warning in warnings:
            logger.warning("  - %s", warning)
    else:
        logger.info("CloudLeak configuration check passed — all required settings present.")


@app.get("/health")
def health_check():
    return {"status": "ok", "service": "cloudleak-api"}


@app.get("/")
def root():
    return {"message": "CloudLeak API is running. See /docs for API documentation."}
