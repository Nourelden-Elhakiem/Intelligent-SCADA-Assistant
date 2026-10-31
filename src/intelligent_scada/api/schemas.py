"""Validated HTTP request and response contracts."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from intelligent_scada.config import validate_document_key


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class HealthResponse(StrictModel):
    status: Literal["ok", "degraded"]
    version: str
    database: Literal["connected", "unavailable", "not_configured"]
    answer_model: Literal["configured", "not_configured"]
    default_document: Literal["indexed", "not_indexed", "unavailable"]
    default_pdf: Literal["available", "missing"]
    knowledge_base: Literal[
        "ready", "default_not_indexed", "database_unavailable", "database_not_configured"
    ]


class RuntimeResponse(StrictModel):
    version: str
    embedding_model: str
    embedding_dimension: int
    answer_model: str
    router_enabled: bool
    default_top_k: int
    max_top_k: int
    max_upload_mb: int
    default_document_key: str
    default_document_name: str
    default_pdf_path: str
    min_retrieval_score: float
    images_enabled: bool = True
    memory_enabled: bool = True


class DocumentSummary(StrictModel):
    document_key: str
    document_name: str
    source_filename: str
    embedding_model: str
    embedding_dimension: int
    chunk_count: int
    image_count: int
    created_at: datetime
    updated_at: datetime
    is_default: bool = False


class DocumentListResponse(StrictModel):
    documents: list[DocumentSummary]


JobStatus = Literal["queued", "running", "succeeded", "failed"]


class JobResponse(StrictModel):
    job_id: str
    document_key: str
    document_name: str
    status: JobStatus
    stage: str
    progress: float = Field(ge=0.0, le=1.0)
    message: str
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    result: dict[str, Any] | None = None
    error: str | None = None


class JobListResponse(StrictModel):
    jobs: list[JobResponse]


class AskRequest(StrictModel):
    question: str = Field(min_length=1, max_length=8000)
    document_key: str | None = Field(default=None, min_length=1, max_length=80)
    session_id: UUID | None = None
    memory_enabled: bool = True
    include_images: bool | None = None
    top_k: int | None = Field(default=None, ge=1, le=100)

    @field_validator("document_key")
    @classmethod
    def document_key_is_valid(cls, value: str | None) -> str | None:
        return validate_document_key(value) if value is not None else None

    @field_validator("question")
    @classmethod
    def question_is_not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Question cannot be empty")
        return value


class CitationResponse(StrictModel):
    source_id: str
    chunk_id: str
    label: str
    page_start: int
    page_end: int
    section_path: list[str]


class SourceResponse(StrictModel):
    chunk_id: str
    text: str
    page_start: int
    page_end: int
    source_pages: list[int]
    section_title: str
    section_path: list[str]
    score: float


class RelatedImageResponse(StrictModel):
    filename: str
    page: int
    width: int
    height: int
    file_size_bytes: int


class AskResponse(StrictModel):
    answer: str
    citations: list[CitationResponse]
    sources: list[SourceResponse]
    related_images: list[RelatedImageResponse]
    session_id: str | None
    routing: dict[str, Any]


class MessageResponse(StrictModel):
    role: Literal["user", "assistant"]
    content: str
    citations: list[dict[str, Any]]
    created_at: datetime


class SessionMessagesResponse(StrictModel):
    session_id: str
    messages: list[MessageResponse]


class DeleteResponse(StrictModel):
    document_key: str
    deleted: bool
    artifacts_deleted: bool


class ErrorDetail(StrictModel):
    code: str
    message: str
    request_id: str | None = None


class ErrorResponse(StrictModel):
    error: ErrorDetail
