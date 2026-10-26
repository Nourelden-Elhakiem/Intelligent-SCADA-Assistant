"""Central, typed configuration for the Intelligent SCADA Assistant."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field, replace
from functools import lru_cache
from pathlib import Path

from dotenv import dotenv_values, load_dotenv

DEFAULT_DOCUMENT_NAME = "Power SCADA Operation 2020 System Guide"
DEFAULT_DOCUMENT_KEY = "power-scada-operation-2020-system-guide"
DEFAULT_PDF_FILENAME = "Power SCADA Operation 2020 System Guide.pdf"
DEFAULT_PDF_RELATIVE_PATH = Path("data") / "pdf" / DEFAULT_PDF_FILENAME
DEFAULT_EMBEDDING_MODEL = "sentence-transformers/all-mpnet-base-v2"
DEFAULT_EMBEDDING_DIMENSION = 768
DEFAULT_EMBEDDING_BATCH_SIZE = 64
DEFAULT_DATABASE_SCHEMA = Path("database") / "schema.sql"
PACKAGED_DATABASE_SCHEMA = Path("database") / "migrations" / "001_initial.sql"


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    return int(value) if value else default


def _env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    return float(value) if value else default


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_csv(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    value = os.getenv(name)
    if not value:
        return default
    return tuple(item.strip() for item in value.split(",") if item.strip())


def document_key_from_name(name: str) -> str:
    """Return a stable, human-readable key suitable for artifact and DB scoping."""
    key = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return key[:80].rstrip("-") or "document"


def validate_document_key(value: str) -> str:
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", value) or len(value) > 80:
        raise ValueError("Document keys must be 1–80 lowercase letters/digits separated by hyphens")
    return value


def _resolve_path(value: str | Path, base: Path) -> Path:
    path = Path(value).expanduser()
    return (path if path.is_absolute() else base / path).resolve()


@dataclass(frozen=True, slots=True)
class Settings:
    """All configurable paths and processing settings.

    Defaults preserve the original notebook configuration. Secrets are read from
    environment variables and are excluded from the dataclass representation.
    """

    project_root: Path
    data_dir: Path
    pdf_filename: str = DEFAULT_PDF_FILENAME
    document_name: str = DEFAULT_DOCUMENT_NAME
    document_key: str = DEFAULT_DOCUMENT_KEY
    default_document_name: str = DEFAULT_DOCUMENT_NAME
    default_document_key: str = DEFAULT_DOCUMENT_KEY
    default_pdf_path_override: Path | None = None

    output_image_format: str = "png"
    image_filename_template: str = (
        "page{page:04d}_img{index:03d}_w{width:04d}_h{height:04d}.{ext}"
    )

    header_footer_patterns: tuple[str, ...] = ("System Guide", "7EN02-0440-03")
    page_number_pattern: str = r"^Page\s+\d+\s+of\s+\d+$"

    chunk_target_size: int = 2500
    chunk_max_size: int = 3500
    chunk_overlap: int = 200
    chunking_strategy: str = "legacy"
    skip_sections: tuple[str, ...] = ("Contents",)

    min_width: int = 80
    min_height: int = 80
    min_combined_width: int = 200
    min_combined_height: int = 150
    blank_std_threshold: float = 5.0
    blank_brightness_low: float = 10.0
    blank_brightness_high: float = 245.0

    embedding_model_name: str = DEFAULT_EMBEDDING_MODEL
    embedding_dimension: int = DEFAULT_EMBEDDING_DIMENSION
    embedding_batch_size: int = DEFAULT_EMBEDDING_BATCH_SIZE
    embedding_model_revision: str | None = None

    pg_conn_str: str | None = field(default=None, repr=False)
    hf_token: str | None = field(default=None, repr=False)

    answer_base_url: str | None = field(default=None, repr=False)
    answer_api_key: str | None = field(default=None, repr=False)
    answer_model: str = "gemini-2.5-flash"
    router_base_url: str | None = field(default=None, repr=False)
    router_api_key: str | None = field(default=None, repr=False)
    router_model: str = "openai/gpt-4.1-mini"
    router_enabled: bool = False

    default_top_k: int = 6
    max_top_k: int = 12
    min_retrieval_score: float = 0.25
    memory_summary_threshold: int = 12
    log_level: str = "INFO"

    api_host: str = "127.0.0.1"
    api_port: int = 8000
    api_reload: bool = False
    api_workers: int = 1
    ingestion_workers: int = 1
    max_pending_jobs: int = 4
    retained_jobs: int = 100
    max_upload_mb: int = 250
    auto_init_db: bool = True
    cors_origins: tuple[str, ...] = (
        "http://localhost:3000",
        "http://localhost:5173",
    )

    @classmethod
    def from_env(
        cls,
        *,
        project_root: Path | None = None,
        data_dir: Path | None = None,
        env_file: Path | None = None,
        env_override: bool = False,
    ) -> Settings:
        process_root = os.getenv("SCADA_PROJECT_ROOT")
        root_value = project_root or Path(process_root or Path.cwd())
        root = root_value.expanduser().resolve()
        dotenv_path = (env_file or root / ".env").expanduser().resolve()
        if dotenv_path.exists():
            file_root = dotenv_values(dotenv_path).get("SCADA_PROJECT_ROOT")
            load_dotenv(dotenv_path, override=env_override)
            if project_root is None and file_root and (env_override or not process_root):
                # Bootstrap exactly one dotenv file; a relocated root does not load another.
                root = _resolve_path(file_root, dotenv_path.parent)

        data_value: str | Path = (
            data_dir if data_dir is not None else os.getenv("SCADA_DATA_DIR") or root / "data"
        )
        resolved_data_dir = _resolve_path(data_value, root)
        default_document_name = (
            os.getenv("SCADA_DEFAULT_DOCUMENT_NAME") or DEFAULT_DOCUMENT_NAME
        )
        default_document_key = os.getenv(
            "SCADA_DEFAULT_DOCUMENT_KEY"
        ) or document_key_from_name(default_document_name)
        default_pdf_path_value = os.getenv("SCADA_DEFAULT_PDF_PATH")
        default_pdf_path_override = (
            Path(default_pdf_path_value).expanduser() if default_pdf_path_value else None
        )
        document_name = os.getenv("SCADA_DOCUMENT_NAME") or default_document_name
        document_key = os.getenv("SCADA_DOCUMENT_KEY") or (
            default_document_key
            if document_name == default_document_name
            else document_key_from_name(document_name)
        )
        settings = cls(
            project_root=root,
            data_dir=resolved_data_dir,
            pdf_filename=os.getenv("SCADA_PDF_FILENAME")
            or (
                default_pdf_path_override.name
                if default_pdf_path_override is not None
                else DEFAULT_PDF_FILENAME
            ),
            document_name=document_name,
            document_key=document_key,
            default_document_name=default_document_name,
            default_document_key=default_document_key,
            default_pdf_path_override=default_pdf_path_override,
            output_image_format=os.getenv("SCADA_OUTPUT_IMAGE_FORMAT") or "png",
            chunk_target_size=_env_int("SCADA_CHUNK_TARGET_SIZE", 2500),
            chunk_max_size=_env_int("SCADA_CHUNK_MAX_SIZE", 3500),
            chunk_overlap=_env_int("SCADA_CHUNK_OVERLAP", 200),
            chunking_strategy=os.getenv("SCADA_CHUNKING_STRATEGY") or "legacy",
            min_width=_env_int("SCADA_MIN_IMAGE_WIDTH", 80),
            min_height=_env_int("SCADA_MIN_IMAGE_HEIGHT", 80),
            min_combined_width=_env_int("SCADA_MIN_COMBINED_WIDTH", 200),
            min_combined_height=_env_int("SCADA_MIN_COMBINED_HEIGHT", 150),
            blank_std_threshold=_env_float("SCADA_BLANK_STD_THRESHOLD", 5.0),
            blank_brightness_low=_env_float("SCADA_BLANK_BRIGHTNESS_LOW", 10.0),
            blank_brightness_high=_env_float("SCADA_BLANK_BRIGHTNESS_HIGH", 245.0),
            embedding_model_name=os.getenv("SCADA_EMBEDDING_MODEL") or DEFAULT_EMBEDDING_MODEL,
            embedding_dimension=_env_int(
                "SCADA_EMBEDDING_DIMENSION", DEFAULT_EMBEDDING_DIMENSION
            ),
            embedding_batch_size=_env_int(
                "SCADA_EMBEDDING_BATCH_SIZE", DEFAULT_EMBEDDING_BATCH_SIZE
            ),
            embedding_model_revision=os.getenv("SCADA_EMBEDDING_REVISION") or None,
            pg_conn_str=os.getenv("PG_CONN_STR"),
            hf_token=os.getenv("HF_TOKEN"),
            answer_base_url=os.getenv("SCADA_ANSWER_BASE_URL") or os.getenv("GEMINI_BASE_URL"),
            answer_api_key=os.getenv("SCADA_ANSWER_API_KEY") or os.getenv("GEMINI_API_KEY"),
            answer_model=os.getenv("SCADA_ANSWER_MODEL")
            or os.getenv("GEMINI_MODEL")
            or "gemini-2.5-flash",
            router_base_url=os.getenv("SCADA_ROUTER_BASE_URL")
            or os.getenv("OPENROUTER_BASE_URL"),
            router_api_key=os.getenv("SCADA_ROUTER_API_KEY") or os.getenv("OPENROUTER_API_KEY"),
            router_model=os.getenv("SCADA_ROUTER_MODEL")
            or os.getenv("OPENROUTER_MODEL")
            or "openai/gpt-4.1-mini",
            router_enabled=_env_bool("SCADA_ROUTER_ENABLED", False),
            default_top_k=_env_int("SCADA_DEFAULT_TOP_K", 6),
            max_top_k=_env_int("SCADA_MAX_TOP_K", 12),
            min_retrieval_score=_env_float("SCADA_MIN_RETRIEVAL_SCORE", 0.25),
            memory_summary_threshold=_env_int("SCADA_MEMORY_SUMMARY_THRESHOLD", 12),
            log_level=(os.getenv("SCADA_LOG_LEVEL") or "INFO").upper(),
            api_host=os.getenv("SCADA_API_HOST") or "127.0.0.1",
            api_port=_env_int("SCADA_API_PORT", 8000),
            api_reload=_env_bool("SCADA_API_RELOAD", False),
            api_workers=_env_int("SCADA_API_WORKERS", 1),
            ingestion_workers=_env_int("SCADA_INGESTION_WORKERS", 1),
            max_pending_jobs=_env_int("SCADA_MAX_PENDING_JOBS", 4),
            retained_jobs=_env_int("SCADA_RETAINED_JOBS", 100),
            max_upload_mb=_env_int("SCADA_MAX_UPLOAD_MB", 250),
            auto_init_db=_env_bool("SCADA_AUTO_INIT_DB", True),
            cors_origins=_env_csv(
                "SCADA_CORS_ORIGINS",
                ("http://localhost:3000", "http://localhost:5173"),
            ),
        )
        settings.validate()
        return settings

    def validate(self) -> None:
        if self.chunk_target_size <= 0 or self.chunk_max_size <= 0:
            raise ValueError("Chunk sizes must be positive integers")
        if self.chunk_target_size > self.chunk_max_size:
            raise ValueError("chunk_target_size cannot exceed chunk_max_size")
        if self.chunk_overlap < 0 or self.chunk_overlap >= self.chunk_max_size:
            raise ValueError("chunk_overlap must be between 0 and chunk_max_size")
        if self.embedding_dimension != DEFAULT_EMBEDDING_DIMENSION:
            raise ValueError("The release database schema requires embedding_dimension=768")
        if self.embedding_batch_size <= 0:
            raise ValueError("embedding_batch_size must be positive")
        if not 1 <= self.default_top_k <= self.max_top_k <= 100:
            raise ValueError("Require 1 <= default_top_k <= max_top_k <= 100")
        if self.memory_summary_threshold <= 0:
            raise ValueError("memory_summary_threshold must be positive")
        validate_document_key(self.document_key)
        validate_document_key(self.default_document_key)
        for name in (self.document_name, self.default_document_name):
            if not name.strip() or len(name) > 200:
                raise ValueError("Document names must contain 1–200 characters")
        if not self.pdf_filename or any(c in self.pdf_filename for c in "/\\"):
            raise ValueError("pdf_filename must be a filename; use SCADA_DEFAULT_PDF_PATH for paths")
        if not -1.0 <= self.min_retrieval_score <= 1.0:
            raise ValueError("min_retrieval_score must be between -1 and 1")
        if self.chunking_strategy not in {"legacy", "targeted"}:
            raise ValueError("chunking_strategy must be 'legacy' or 'targeted'")
        if self.api_port <= 0 or self.api_port > 65535:
            raise ValueError("api_port must be between 1 and 65535")
        if self.api_workers != 1 or self.ingestion_workers != 1:
            raise ValueError("Process-local jobs require one API worker and one ingestion worker")
        if self.max_pending_jobs <= 0 or self.retained_jobs <= 0:
            raise ValueError("Job admission and retention limits must be positive")
        if self.max_upload_mb <= 0:
            raise ValueError("max_upload_mb must be positive")

    def configure_worker_environment(self) -> None:
        """Pass resolved paths to Uvicorn reload and worker child processes."""
        os.environ["SCADA_PROJECT_ROOT"] = str(self.project_root)
        os.environ["SCADA_DATA_DIR"] = str(self.data_dir)

    @property
    def pdf_dir(self) -> Path:
        return self.data_dir / "pdf"

    @property
    def pdf_path(self) -> Path:
        return self.pdf_dir / self.pdf_filename

    @property
    def default_pdf_path(self) -> Path:
        """Resolved location of the application's primary Power SCADA manual."""
        if self.default_pdf_path_override is None:
            return self.data_dir / "pdf" / DEFAULT_PDF_FILENAME
        if self.default_pdf_path_override.is_absolute():
            return self.default_pdf_path_override.resolve()
        return (self.project_root / self.default_pdf_path_override).resolve()

    @property
    def default_pdf_display_path(self) -> str:
        """Safe setup hint: never disclose an absolute host path in HTTP responses."""
        if self.default_pdf_path_override is None:
            return DEFAULT_PDF_RELATIVE_PATH.as_posix()
        try:
            return self.default_pdf_path.relative_to(self.project_root).as_posix()
        except ValueError:
            return self.default_pdf_path.name

    def require_default_pdf(self) -> Path:
        """Return the primary PDF or raise an actionable setup error."""
        path = self.default_pdf_path
        if not path.is_file():
            raise FileNotFoundError(
                "Default Power SCADA manual not found. Copy "
                f"'{DEFAULT_PDF_FILENAME}' to '{self.default_pdf_display_path}' "
                "or set SCADA_DEFAULT_PDF_PATH to its location."
            )
        return path

    def is_default_document(self, document_key: str) -> bool:
        return document_key == self.default_document_key

    def for_default_document(self) -> Settings:
        """Return pipeline settings pinned to the primary manual identity."""
        return replace(
            self,
            pdf_filename=self.default_pdf_path.name,
            document_name=self.default_document_name,
            document_key=self.default_document_key,
        )

    def for_document(
        self,
        *,
        document_name: str,
        document_key: str | None = None,
        data_dir: Path | None = None,
        pdf_filename: str | None = None,
    ) -> Settings:
        """Return an isolated settings view for one indexed manual."""
        resolved_name = document_name.strip()
        if not resolved_name:
            raise ValueError("document_name cannot be empty")
        resolved_key = (document_key or document_key_from_name(resolved_name)).strip()
        validate_document_key(resolved_key)
        scoped = replace(
            self,
            data_dir=_resolve_path(data_dir or self.data_dir, self.project_root),
            pdf_filename=pdf_filename or self.pdf_filename,
            document_name=resolved_name,
            document_key=resolved_key,
        )
        scoped.validate()
        return scoped

    @property
    def database_schema_path(self) -> Path:
        """Return the repository schema, falling back to the packaged migration."""
        project_schema = self.project_root / DEFAULT_DATABASE_SCHEMA
        if project_schema.is_file():
            return project_schema
        packaged_schema = Path(__file__).resolve().parent / PACKAGED_DATABASE_SCHEMA
        if packaged_schema.is_file():
            return packaged_schema
        raise FileNotFoundError(
            "Database schema not found. Expected "
            f"'{project_schema}' or packaged schema '{packaged_schema}'."
        )

    @property
    def raw_images_dir(self) -> Path:
        return self.data_dir / "images" / "raw"

    @property
    def manifests_dir(self) -> Path:
        return self.data_dir / "manifests"

    @property
    def filtered_keep_dir(self) -> Path:
        return self.data_dir / "filtered" / "keep"

    @property
    def filtered_discard_dir(self) -> Path:
        return self.data_dir / "filtered" / "discard"

    @property
    def text_dir(self) -> Path:
        return self.data_dir / "text"

    @property
    def linked_dir(self) -> Path:
        return self.data_dir / "linked"

    @property
    def embeddings_dir(self) -> Path:
        return self.data_dir / "embeddings"

    @property
    def image_manifest_path(self) -> Path:
        return self.manifests_dir / "image_manifest.json"

    @property
    def filter_manifest_path(self) -> Path:
        return self.manifests_dir / "filter_manifest.json"

    @property
    def pdf_structure_path(self) -> Path:
        return self.manifests_dir / "pdf_structure.json"

    @property
    def raw_text_path(self) -> Path:
        return self.text_dir / "pages_raw.json"

    @property
    def clean_text_path(self) -> Path:
        return self.text_dir / "pages_clean.json"

    @property
    def text_chunks_path(self) -> Path:
        return self.text_dir / "text_chunks.json"

    @property
    def chunk_image_links_path(self) -> Path:
        return self.linked_dir / "chunk_image_links.json"

    @property
    def embeddings_npy_path(self) -> Path:
        return self.embeddings_dir / "chunk_embeddings.npy"

    @property
    def embeddings_meta_path(self) -> Path:
        return self.embeddings_dir / "chunk_embeddings_metadata.json"

    @property
    def embeddings_manifest_path(self) -> Path:
        return self.embeddings_dir / "embedding_run.json"

    @property
    def output_dirs(self) -> tuple[Path, ...]:
        return (
            self.raw_images_dir,
            self.manifests_dir,
            self.filtered_keep_dir,
            self.filtered_discard_dir,
            self.text_dir,
            self.linked_dir,
            self.embeddings_dir,
        )

    def ensure_output_dirs(self) -> None:
        for directory in self.output_dirs:
            directory.mkdir(parents=True, exist_ok=True)

    @property
    def documents_dir(self) -> Path:
        """Root used by the API for isolated, per-document artifacts."""
        return self.data_dir / "documents"

    @property
    def frontend_dist_dir(self) -> Path:
        packaged_frontend = Path(__file__).resolve().parent / "static"
        if (packaged_frontend / "index.html").is_file():
            return packaged_frontend
        return self.project_root / "frontend" / "dist"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings.from_env()
