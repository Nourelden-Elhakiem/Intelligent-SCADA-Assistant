"""FastAPI application factory and production SPA hosting."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from intelligent_scada import __version__
from intelligent_scada.api.jobs import DocumentBusyError, JobManager, QueueFullError
from intelligent_scada.api.middleware import (
    UploadSizeLimitMiddleware,
    request_context_middleware,
)
from intelligent_scada.api.routes import router
from intelligent_scada.config import Settings
from intelligent_scada.database.connection import DatabaseConfigurationError
from intelligent_scada.database.repository import DatabaseRepository
from intelligent_scada.logging_config import configure_logging
from intelligent_scada.rag.llm_client import LLMConfigurationError, LLMProviderError
from intelligent_scada.rag.service import RAGService

LOGGER = logging.getLogger(__name__)
RAGFactory = Callable[[Settings], RAGService]


def _error(request: Request, status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": code,
                "message": message,
                "request_id": getattr(request.state, "request_id", None),
            }
        },
    )


def create_app(
    settings: Settings | None = None,
    *,
    job_manager: JobManager | None = None,
    rag_factory: RAGFactory = RAGService.from_settings,
) -> FastAPI:
    resolved_settings = settings or Settings.from_env()
    resolved_settings.validate()
    configure_logging(resolved_settings.log_level)
    repository = DatabaseRepository(resolved_settings.pg_conn_str)
    manager = job_manager or JobManager(resolved_settings)
    rag_service: RAGService | None = None
    rag_lock = threading.Lock()

    def cached_rag_factory(current_settings: Settings) -> RAGService:
        nonlocal rag_service
        if rag_service is None:
            with rag_lock:
                if rag_service is None:
                    rag_service = rag_factory(current_settings)
        return rag_service

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> Any:
        resolved_settings.documents_dir.mkdir(parents=True, exist_ok=True)
        if resolved_settings.auto_init_db and resolved_settings.pg_conn_str:
            try:
                repository.apply_schema(resolved_settings.database_schema_path)
            except Exception as exc:
                LOGGER.error("Database initialization failed (%s); API remains in degraded mode", type(exc).__name__)
        yield
        manager.shutdown()

    app = FastAPI(
        title="Intelligent SCADA Assistant API",
        description=(
            "Document ingestion, pgvector retrieval, cited answer generation, "
            "session memory, and optional visual references."
        ),
        version=__version__,
        lifespan=lifespan,
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
    )
    app.state.settings = resolved_settings
    app.state.repository = repository
    app.state.job_manager = manager
    app.state.rag_factory = cached_rag_factory

    app.middleware("http")(request_context_middleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(resolved_settings.cors_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "X-Request-ID"],
    )

    app.add_middleware(UploadSizeLimitMiddleware,
                       maximum_bytes=resolved_settings.max_upload_mb * 1024 * 1024 + 65536)

    @app.exception_handler(DocumentBusyError)
    async def document_busy(request: Request, exc: DocumentBusyError) -> JSONResponse:
        return _error(request, 409, "document_busy", "The document already has an active operation.")

    @app.exception_handler(QueueFullError)
    async def queue_full(request: Request, exc: QueueFullError) -> JSONResponse:
        return _error(request, 503, "queue_full", "The ingestion queue is full. Try again later.")

    @app.exception_handler(LLMProviderError)
    async def provider_error(request: Request, exc: LLMProviderError) -> JSONResponse:
        return _error(request, exc.status_code, exc.code, str(exc))

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        messages = "; ".join(
            f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}"
            for error in exc.errors()
        )
        return _error(request, 422, "validation_error", messages)

    @app.exception_handler(LookupError)
    async def not_found(request: Request, exc: LookupError) -> JSONResponse:
        return _error(request, 404, "not_found", "The requested resource was not found.")

    @app.exception_handler(ValueError)
    async def invalid_value(request: Request, exc: ValueError) -> JSONResponse:
        LOGGER.warning("Invalid API operation (%s), request %s", type(exc).__name__, getattr(request.state, "request_id", "unknown"))
        return _error(request, 422, "invalid_value", "Invalid request or incompatible indexed data. Check the input and server logs.")

    @app.exception_handler(DatabaseConfigurationError)
    async def database_not_configured(
        request: Request, exc: DatabaseConfigurationError
    ) -> JSONResponse:
        return _error(request, 503, "database_not_configured", "The database is not configured on this server.")

    @app.exception_handler(LLMConfigurationError)
    async def answer_model_not_configured(
        request: Request, exc: LLMConfigurationError
    ) -> JSONResponse:
        return _error(request, 503, "answer_model_not_configured", "The answer model is not configured on this server.")

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        if isinstance(exc, HTTPException):
            raise exc
        LOGGER.error("Unhandled API error (%s), request %s", type(exc).__name__, getattr(request.state, "request_id", "unknown"))
        return _error(
            request,
            500,
            "internal_error",
            "The request could not be completed. Check the server logs for details.",
        )

    app.include_router(router)

    frontend_dist = resolved_settings.frontend_dist_dir
    if frontend_dist.is_dir():
        assets = frontend_dist / "assets"
        if assets.is_dir():
            app.mount("/assets", StaticFiles(directory=assets), name="frontend-assets")

    @app.get("/", include_in_schema=False)
    def frontend_index() -> Any:
        index = frontend_dist / "index.html"
        if index.is_file():
            return FileResponse(index)
        return JSONResponse(
            {
                "name": "Intelligent SCADA Assistant",
                "version": __version__,
                "api_docs": "/api/docs",
                "frontend": "Run `npm run dev` in frontend or run `npm run build` to package the UI.",
            }
        )

    @app.get("/{path:path}", include_in_schema=False)
    def frontend_fallback(path: str) -> Any:
        if path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Endpoint not found")
        index = frontend_dist / "index.html"
        candidate = (frontend_dist / path).resolve()
        if (
            frontend_dist.is_dir()
            and candidate.is_relative_to(frontend_dist.resolve())
            and candidate.is_file()
        ):
            return FileResponse(candidate)
        if index.is_file():
            return FileResponse(index)
        raise HTTPException(status_code=404, detail="Frontend is not built")

    return app
