"""Versioned HTTP routes for ingestion, retrieval, and document management."""

from __future__ import annotations

import mimetypes
import os
import shutil
import tempfile
from pathlib import Path
from typing import Annotated, Any, cast
from uuid import UUID

from fastapi import APIRouter, File, Form, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import FileResponse

from intelligent_scada import __version__
from intelligent_scada.api.schemas import (
    AskRequest,
    AskResponse,
    DeleteResponse,
    DocumentListResponse,
    DocumentSummary,
    HealthResponse,
    JobListResponse,
    JobResponse,
    RuntimeResponse,
    SessionMessagesResponse,
)
from intelligent_scada.config import Settings, document_key_from_name, validate_document_key
from intelligent_scada.images.image_lookup import ImageLookup
from intelligent_scada.memory.memory_store import MemoryStore

router = APIRouter(prefix="/api/v1")


def _settings(request: Request) -> Settings:
    return cast(Settings, request.app.state.settings)


def _safe_document_key(value: str) -> str:
    return validate_document_key(value)


@router.get("/health", response_model=HealthResponse, tags=["System"])
def health(request: Request) -> HealthResponse:
    settings = _settings(request)
    if not settings.pg_conn_str:
        database = "not_configured"
    else:
        try:
            database = "connected" if request.app.state.repository.ping() else "unavailable"
        except Exception:
            database = "unavailable"
    default_document = "unavailable"
    if database == "connected":
        try:
            indexed = request.app.state.repository.get_document(settings.default_document_key)
            default_document = (
                "indexed" if indexed and indexed["chunk_count"] > 0 else "not_indexed"
            )
        except Exception:
            database = "unavailable"
    if database == "not_configured":
        knowledge_base = "database_not_configured"
    elif database == "unavailable":
        knowledge_base = "database_unavailable"
    elif default_document == "indexed":
        knowledge_base = "ready"
    else:
        knowledge_base = "default_not_indexed"
    default_pdf = "available" if settings.default_pdf_path.is_file() else "missing"
    answer_model = (
        "configured"
        if settings.answer_base_url and settings.answer_api_key
        else "not_configured"
    )
    return HealthResponse(
        status=(
            "ok" if knowledge_base == "ready" and answer_model == "configured" else "degraded"
        ),
        version=__version__,
        database=database,
        answer_model=answer_model,
        default_document=default_document,
        default_pdf=default_pdf,
        knowledge_base=knowledge_base,
    )


@router.get("/runtime", response_model=RuntimeResponse, tags=["System"])
def runtime(request: Request) -> RuntimeResponse:
    settings = _settings(request)
    return RuntimeResponse(
        version=__version__,
        embedding_model=settings.embedding_model_name,
        embedding_dimension=settings.embedding_dimension,
        answer_model=settings.answer_model,
        router_enabled=settings.router_enabled,
        default_top_k=settings.default_top_k,
        max_top_k=settings.max_top_k,
        max_upload_mb=settings.max_upload_mb,
        default_document_key=settings.default_document_key,
        default_document_name=settings.default_document_name,
        default_pdf_path=settings.default_pdf_display_path,
        min_retrieval_score=settings.min_retrieval_score,
    )


@router.get("/documents", response_model=DocumentListResponse, tags=["Documents"])
def list_documents(request: Request) -> DocumentListResponse:
    settings = _settings(request)
    documents = request.app.state.repository.list_documents()
    return DocumentListResponse(
        documents=[
            DocumentSummary.model_validate(
                {
                    **item,
                    "is_default": settings.is_default_document(item["document_key"]),
                }
            )
            for item in documents
        ]
    )


@router.post(
    "/documents/upload",
    response_model=JobResponse,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["Documents"],
)
async def upload_document(
    request: Request,
    file: Annotated[UploadFile, File(description="SCADA manual in PDF format")],
    document_name: Annotated[str | None, Form(max_length=200)] = None,
    document_key: Annotated[str | None, Form(max_length=80)] = None,
    include_images: Annotated[bool, Form()] = True,
    resume: Annotated[bool, Form()] = False,
    force: Annotated[bool, Form()] = False,
) -> JobResponse:
    settings = _settings(request)
    original_filename = Path((file.filename or "manual.pdf").replace("\\", "/")).name
    if Path(original_filename).suffix.lower() != ".pdf":
        raise HTTPException(status_code=415, detail="Only PDF files are accepted")

    resolved_name = (document_name or Path(original_filename).stem).strip()
    if not resolved_name or len(resolved_name) > 200:
        raise HTTPException(status_code=422, detail="document_name must contain 1-200 characters")
    resolved_key = _safe_document_key(document_key or document_key_from_name(resolved_name))
    manager = request.app.state.job_manager
    reservation = manager.reserve_document(resolved_key)
    temporary: Path | None = None
    accepted = False
    maximum_bytes = settings.max_upload_mb * 1024 * 1024
    written = 0
    first_chunk = True
    try:
        pdf_dir = settings.documents_dir / resolved_key / "pdf"
        pdf_dir.mkdir(parents=True, exist_ok=True)
        destination = pdf_dir / original_filename
        fd, temporary_name = tempfile.mkstemp(prefix=".upload-", suffix=".pdf", dir=pdf_dir)
        temporary = Path(temporary_name)
        with os.fdopen(fd, "wb") as stream:
            while chunk := await file.read(1024 * 1024):
                if first_chunk:
                    first_chunk = False
                    if not chunk.startswith(b"%PDF-"):
                        raise HTTPException(
                            status_code=415, detail="The file is not a valid PDF"
                        )
                written += len(chunk)
                if written > maximum_bytes:
                    raise HTTPException(
                        status_code=413,
                        detail=f"PDF exceeds the {settings.max_upload_mb} MB upload limit",
                    )
                stream.write(chunk)
        if written == 0:
            raise HTTPException(status_code=422, detail="The uploaded PDF is empty")
        job = manager.submit_ingestion(
            destination,
            document_name=resolved_name,
            document_key=resolved_key,
            include_images=include_images,
            resume=resume,
            force=force,
            reservation=reservation,
            staged_path=temporary,
        )
        accepted = True
    finally:
        await file.close()
        if not accepted:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
            manager.release_document(resolved_key, reservation)
    return cast(JobResponse, JobResponse.model_validate(job))


@router.get("/jobs", response_model=JobListResponse, tags=["Jobs"])
def list_jobs(
    request: Request,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> JobListResponse:
    return JobListResponse(
        jobs=[
            JobResponse.model_validate(item)
            for item in request.app.state.job_manager.list(limit=limit)
        ]
    )


@router.get("/jobs/{job_id}", response_model=JobResponse, tags=["Jobs"])
def get_job(job_id: str, request: Request) -> JobResponse:
    job = request.app.state.job_manager.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Ingestion job not found")
    return cast(JobResponse, JobResponse.model_validate(job))


@router.delete(
    "/documents/{document_key}",
    response_model=DeleteResponse,
    tags=["Documents"],
)
def delete_document(
    document_key: str,
    request: Request,
    delete_artifacts: bool = Query(default=True),
) -> DeleteResponse:
    document_key = _safe_document_key(document_key)
    with request.app.state.job_manager.document_operation(document_key):
        deleted = request.app.state.repository.delete_document(document_key)
        artifacts_deleted = False
        if delete_artifacts:
            documents_root = _settings(request).documents_dir.resolve()
            target = (documents_root / document_key).resolve()
            if target.is_relative_to(documents_root) and target.exists():
                shutil.rmtree(target)
                artifacts_deleted = True
        if not deleted and not artifacts_deleted:
            raise HTTPException(status_code=404, detail="Document not found")
        return DeleteResponse(
            document_key=document_key,
            deleted=deleted,
            artifacts_deleted=artifacts_deleted,
        )


@router.post("/chat/ask", response_model=AskResponse, tags=["Chat"])
def ask_question(payload: AskRequest, request: Request) -> AskResponse:
    settings = _settings(request)
    if payload.top_k and payload.top_k > settings.max_top_k:
        raise HTTPException(
            status_code=422,
            detail=f"top_k cannot exceed the configured maximum of {settings.max_top_k}",
        )
    service = request.app.state.rag_factory(settings)
    result = service.ask(
        payload.question,
        payload.document_key,
        session_id=str(payload.session_id) if payload.session_id is not None else None,
        memory_enabled=payload.memory_enabled,
        include_images=payload.include_images,
        top_k=payload.top_k,
    )
    return cast(AskResponse, AskResponse.model_validate(result))


@router.get(
    "/sessions/{session_id}/messages",
    response_model=SessionMessagesResponse,
    tags=["Chat"],
)
def session_messages(
    session_id: UUID,
    request: Request,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> SessionMessagesResponse:
    messages = MemoryStore(_settings(request).pg_conn_str).messages(str(session_id), limit=limit)
    return SessionMessagesResponse(session_id=str(session_id), messages=messages)


@router.get(
    "/documents/{document_key}/images/{filename}",
    response_class=FileResponse,
    tags=["Documents"],
)
def document_image(document_key: str, filename: str, request: Request) -> Any:
    document_key = _safe_document_key(document_key)
    safe_filename = Path(filename).name
    if safe_filename != filename:
        raise HTTPException(status_code=404, detail="Image not found")
    image_path = ImageLookup(_settings(request).pg_conn_str, data_root=_settings(request).data_dir).resolve_path(
        document_key, safe_filename
    )
    if image_path is None or not image_path.is_file():
        raise HTTPException(status_code=404, detail="Image not found")
    media_type = mimetypes.guess_type(image_path.name)[0] or "application/octet-stream"
    return FileResponse(image_path, media_type=media_type, filename=image_path.name)
