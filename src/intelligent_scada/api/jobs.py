"""Small in-process job manager for long-running document ingestion."""

from __future__ import annotations

import logging
import threading
import uuid
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from intelligent_scada.config import Settings, validate_document_key
from intelligent_scada.pipeline import Pipeline

LOGGER = logging.getLogger(__name__)
JobStatus = Literal["queued", "running", "succeeded", "failed"]
PipelineFactory = Callable[..., Pipeline]


def _now() -> datetime:
    return datetime.now(UTC)


@dataclass(slots=True)
class JobRecord:
    job_id: str
    document_key: str
    document_name: str
    status: JobStatus = "queued"
    stage: str = "queued"
    progress: float = 0.0
    message: str = "Waiting for an ingestion worker"
    created_at: datetime = field(default_factory=_now)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    result: dict[str, object] | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "document_key": self.document_key,
            "document_name": self.document_name,
            "status": self.status,
            "stage": self.stage,
            "progress": self.progress,
            "message": self.message,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "result": self.result,
            "error": self.error,
        }


class DocumentBusyError(ValueError):
    """The document is owned by another upload, ingestion, or deletion."""


class QueueFullError(RuntimeError):
    """The bounded in-process queue cannot accept another upload."""


class JobManager:
    """Run CPU-heavy ingestion outside request threads and expose stable snapshots."""

    def __init__(
        self,
        settings: Settings,
        *,
        pipeline_factory: PipelineFactory = Pipeline,
    ) -> None:
        settings.validate()
        self.settings = settings
        self.pipeline_factory = pipeline_factory
        self._jobs: dict[str, JobRecord] = {}
        self._owners: dict[str, tuple[str, bool]] = {}
        self._lock = threading.RLock()
        self._executor = ThreadPoolExecutor(
            max_workers=settings.ingestion_workers,
            thread_name_prefix="scada-ingestion",
        )

    def has_active_document(self, document_key: str) -> bool:
        with self._lock:
            return document_key in self._owners

    def reserve_document(self, document_key: str, *, ingestion: bool = True) -> str:
        validate_document_key(document_key)
        with self._lock:
            if document_key in self._owners:
                raise DocumentBusyError("The document already has an active operation")
            active = sum(is_ingestion for _, is_ingestion in self._owners.values())
            if ingestion and active >= self.settings.max_pending_jobs + self.settings.ingestion_workers:
                raise QueueFullError("The ingestion queue is full. Try again after a job completes.")
            token = str(uuid.uuid4())
            self._owners[document_key] = (token, ingestion)
            return token

    def release_document(self, document_key: str, reservation: str) -> None:
        with self._lock:
            owner = self._owners.get(document_key)
            if owner and owner[0] == reservation:
                del self._owners[document_key]

    @contextmanager
    def document_operation(self, document_key: str) -> Iterator[None]:
        token = self.reserve_document(document_key, ingestion=False)
        try:
            yield
        finally:
            self.release_document(document_key, token)

    def _prune(self) -> None:
        completed = sorted(
            (job for job in self._jobs.values() if job.status in {"succeeded", "failed"}),
            key=lambda job: job.created_at, reverse=True,
        )
        for job in completed[self.settings.retained_jobs:]:
            del self._jobs[job.job_id]

    def submit_ingestion(
        self,
        pdf_path: Path,
        *,
        document_name: str,
        document_key: str,
        include_images: bool,
        resume: bool,
        force: bool,
        reservation: str | None = None,
        staged_path: Path | None = None,
    ) -> dict[str, Any]:
        token = reservation or self.reserve_document(document_key)
        with self._lock:
            if self._owners.get(document_key) != (token, True):
                raise DocumentBusyError("The upload reservation is no longer valid")
            job_id = str(uuid.uuid4())
            record = JobRecord(job_id=job_id, document_key=document_key, document_name=document_name)
            self._jobs[job_id] = record
            try:
                self._executor.submit(
                    self._run, job_id, pdf_path, document_name, document_key,
                    include_images, resume, force, token, staged_path,
                )
            except Exception:
                del self._jobs[job_id]
                self.release_document(document_key, token)
                raise
            return record.to_dict()

    def _update(self, job_id: str, **changes: Any) -> None:
        with self._lock:
            record = self._jobs[job_id]
            for name, value in changes.items():
                setattr(record, name, value)

    def _run(
        self,
        job_id: str,
        pdf_path: Path,
        document_name: str,
        document_key: str,
        include_images: bool,
        resume: bool,
        force: bool,
        reservation: str,
        staged_path: Path | None,
    ) -> None:
        self._update(
            job_id,
            status="running",
            stage="starting",
            progress=0.01,
            message="Starting document ingestion",
            started_at=_now(),
        )

        def report(stage: str, progress: float, message: str) -> None:
            self._update(
                job_id,
                stage=stage,
                progress=progress,
                message=message,
            )

        try:
            document_data_dir = pdf_path.parent.parent
            job_settings = self.settings.for_document(
                data_dir=document_data_dir,
                pdf_filename=pdf_path.name,
                document_name=document_name,
                document_key=document_key,
            )
            if staged_path is not None:
                staged_path.replace(pdf_path)
            pipeline = self.pipeline_factory(job_settings, progress_callback=report)
            result = pipeline.ingest(
                pdf_path,
                resume=resume,
                force=force,
                include_images=include_images,
                include_index=True,
            )
        except Exception as exc:
            LOGGER.error("Ingestion job %s failed at %s (%s)", job_id,
                         (self.get(job_id) or {}).get("stage", "unknown"), type(exc).__name__)
            self._update(
                job_id,
                status="failed",
                stage="failed",
                message="Document ingestion failed",
                error="Ingestion failed. Check server logs using this job ID; verify the PDF has bookmarks and extractable text.",
                finished_at=_now(),
            )
        else:
            self._update(
                job_id,
                status="succeeded",
                stage="completed",
                progress=1.0,
                message="Document ingestion completed",
                result=result,
                finished_at=_now(),
            )
        finally:
            try:
                if staged_path is not None:
                    staged_path.unlink(missing_ok=True)
            finally:
                with self._lock:
                    self.release_document(document_key, reservation)
                    self._prune()

    def get(self, job_id: str) -> dict[str, Any] | None:
        with self._lock:
            record = self._jobs.get(job_id)
            return record.to_dict() if record else None

    def list(self, *, limit: int = 50) -> list[dict[str, Any]]:
        with self._lock:
            records = sorted(self._jobs.values(), key=lambda job: job.created_at, reverse=True)[
                :limit
            ]
            return [record.to_dict() for record in records]

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=False)
