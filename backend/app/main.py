"""
app/main.py
────────────
FastAPI application factory with:
- Lifespan: DB connection warm-up, logging init
- CORS middleware
- Request-ID injection middleware
- Structured error handlers
- Health check endpoint
"""
from __future__ import annotations

import os
os.environ.setdefault("USE_TF", "0")
os.environ.setdefault("TRANSFORMERS_NO_TF", "1")
import uuid
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.api.router import api_router
from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.db.session import engine

settings = get_settings()
log = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    log.info("startup", environment=settings.ENVIRONMENT)

    # Verify DB connection and ensure tables exist
    from app.db.base import Base
    import app.models  # noqa: F401
    async with engine.begin() as conn:
        await conn.execute(text("SELECT 1"))
        await conn.run_sync(Base.metadata.create_all)
    log.info("database_connected")

    yield

    await engine.dispose()
    log.info("shutdown")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Veritas AI",
        description="Grounded Intelligence platform with verifiable citations",
        version="0.1.0",
        docs_url="/docs" if settings.ENVIRONMENT == "development" else None,
        redoc_url="/redoc" if settings.ENVIRONMENT == "development" else None,
        lifespan=lifespan,
    )

    # ── CORS ──────────────────────────────────────────────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Request-ID middleware ──────────────────────────────────────────────────
    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

    # ── Global error handlers ──────────────────────────────────────────────────
    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        request_id = request.headers.get("X-Request-ID", "unknown")
        log.exception("unhandled_error", request_id=request_id, exc_info=exc)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"error": "Internal server error", "request_id": request_id},
        )

    # ── Health check ──────────────────────────────────────────────────────────
    @app.get("/health", tags=["infra"])
    async def health() -> dict:
        return {"status": "ok", "version": "0.1.0"}

    # ── Routers ───────────────────────────────────────────────────────────────
    app.include_router(api_router)

    # ── Serve frontend SPA if built ───────────────────────────────────────────
    from pathlib import Path
    from fastapi.staticfiles import StaticFiles
    from fastapi.responses import FileResponse
    from fastapi import HTTPException

    possible_dist_paths = [
        Path(__file__).resolve().parent.parent.parent / "frontend" / "dist",
        Path("/app/frontend/dist"),
        Path("frontend/dist"),
        Path("/app/dist"),
    ]
    dist_dir = next((p for p in possible_dist_paths if p.exists() and (p / "index.html").exists()), None)

    if dist_dir:
        if (dist_dir / "assets").exists():
            app.mount("/assets", StaticFiles(directory=str(dist_dir / "assets")), name="assets")

        @app.get("/{full_path:path}", include_in_schema=False)
        async def serve_spa(full_path: str):
            if full_path.startswith("api/") or full_path in ("docs", "openapi.json", "redoc", "health"):
                raise HTTPException(status_code=404, detail="Not found")
            target = dist_dir / full_path
            if target.is_file():
                return FileResponse(target)
            return FileResponse(dist_dir / "index.html")

    return app


app = create_app()
