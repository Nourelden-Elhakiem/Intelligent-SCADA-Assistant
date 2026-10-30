"""Sequential, resumable orchestration of document-ingestion stages."""

from __future__ import annotations

import logging
from collections.abc import Callable
from contextlib import suppress
from pathlib import Path
from typing import Any, cast

from intelligent_scada.artifacts import (
    ArtifactError,
    json_digest,
    load_embeddings,
    read_json,
    sha256_file,
    stage_matches,
    write_json,
    write_stage_manifest,
)
from intelligent_scada.chunking.toc_chunker import create_chunks
from intelligent_scada.config import Settings
from intelligent_scada.contracts import (
    ChunkImageLink,
    CleanPage,
    FilteredImageRecord,
    ImageRecord,
    PdfStructure,
    TextChunk,
)
from intelligent_scada.database.models import validate_embedding_alignment
from intelligent_scada.database.repository import DatabaseRepository
from intelligent_scada.embeddings.embedding_service import EmbeddingService
from intelligent_scada.ingestion.image_extractor import extract_images
from intelligent_scada.ingestion.image_filter import filter_images
from intelligent_scada.ingestion.pdf_analyzer import analyze_pdf
from intelligent_scada.ingestion.text_cleaner import clean_pages
from intelligent_scada.ingestion.text_extractor import extract_page_text
from intelligent_scada.linking.image_text_linker import link_images_to_chunks

LOGGER = logging.getLogger(__name__)
ProgressCallback = Callable[[str, float, str], None]


class Pipeline:
    def __init__(
        self,
        settings: Settings,
        progress_callback: ProgressCallback | None = None,
    ) -> None:
        settings.validate()
        self.settings = settings
        self.progress_callback = progress_callback
        self.settings.ensure_output_dirs()

    def _report(self, stage: str, progress: float, message: str) -> None:
        LOGGER.info("%s: %s", stage, message)
        if self.progress_callback is not None:
            self.progress_callback(stage, max(0.0, min(progress, 1.0)), message)

    def _manifest(self, stage: str) -> Path:
        return self.settings.manifests_dir / f"pipeline_{stage}.json"

    def _matches(self, stage: str, inputs: dict[str, Any], outputs: list[Path]) -> bool:
        return stage_matches(self._manifest(stage), inputs, outputs, root=self.settings.data_dir)

    def _stamp(self, stage: str, inputs: dict[str, Any], outputs: list[Path]) -> None:
        write_stage_manifest(self._manifest(stage), inputs, outputs, root=self.settings.data_dir)

    def _require(self, stage: str, inputs: dict[str, Any], outputs: list[Path]) -> None:
        if not self._matches(stage, inputs, outputs):
            raise ArtifactError(
                f"{stage} artifacts are stale or unverified; run ingest --resume to rebuild"
            )

    def _pdf_inputs(self, pdf_path: Path, stage: str, *, enabled: bool = True) -> dict[str, Any]:
        settings = self.settings
        fields = {
            "images": ("output_image_format", "image_filename_template", "min_width", "min_height",
                       "min_combined_width", "min_combined_height", "blank_std_threshold",
                       "blank_brightness_high", "blank_brightness_low"),
            "text": ("header_footer_patterns", "page_number_pattern"),
            "structure": (),
        }[stage]
        return {"source_sha256": sha256_file(pdf_path), "enabled": enabled,
                "settings": {key: getattr(settings, key) for key in fields}}

    def _chunk_inputs(self, structure: PdfStructure, pages: list[CleanPage]) -> dict[str, Any]:
        fields = ("chunk_target_size", "chunk_max_size", "chunk_overlap",
                  "chunking_strategy", "skip_sections")
        return {"structure": json_digest(structure), "pages": json_digest(pages),
                "settings": {key: getattr(self.settings, key) for key in fields}}

    @staticmethod
    def _link_inputs(chunks: list[TextChunk], images: list[FilteredImageRecord]) -> dict[str, Any]:
        return {"chunks": json_digest(chunks), "images": json_digest(images)}

    def _embedding_inputs(self, chunks: list[TextChunk]) -> dict[str, Any]:
        return {"chunks": json_digest(chunks), "model": self.settings.embedding_model_name,
                "revision": self.settings.embedding_model_revision,
                "dimension": self.settings.embedding_dimension, "normalized": True,
                "batch_size": self.settings.embedding_batch_size}

    def _review_is_valid(
        self, reviewed: Any, originals: list[ImageRecord]
    ) -> bool:
        if not isinstance(reviewed, list) or not reviewed or len(reviewed) != len(originals):
            return False
        for item, original in zip(reviewed, originals, strict=True):
            if not isinstance(item, dict) or item.get("source") != "manual_review":
                return False
            if any(item.get(key) != value for key, value in original.items()):
                return False
            decision = item.get("decision")
            if decision not in {"keep", "discard", "missing"}:
                return False
            if decision != "missing":
                folder = (self.settings.filtered_keep_dir if decision == "keep"
                          else self.settings.filtered_discard_dir)
                chosen = folder / original["filename"]
                raw = self.settings.raw_images_dir / original["filename"]
                if not chosen.is_file() or sha256_file(chosen) != sha256_file(raw):
                    return False
        return True

    def extract_images(
        self, pdf_path: Path, *, resume: bool = False, force: bool = False
    ) -> list[FilteredImageRecord]:
        inputs = self._pdf_inputs(pdf_path, "images")
        outputs = [self.settings.image_manifest_path, self.settings.filter_manifest_path]
        if resume and not force and self._matches("images", inputs, outputs):
            LOGGER.info("Resuming after image extraction/filtering")
            return cast(
                list[FilteredImageRecord], read_json(self.settings.filter_manifest_path)
            )

        reviewed: Any = None
        if not force and self.settings.filter_manifest_path.exists():
            with suppress(ArtifactError):
                reviewed = read_json(self.settings.filter_manifest_path)
        manifest = extract_images(
            pdf_path,
            self.settings.raw_images_dir,
            self.settings.image_manifest_path,
            output_format=self.settings.output_image_format,
            filename_template=self.settings.image_filename_template,
        )
        if self._review_is_valid(reviewed, manifest):
            filtered = cast(list[FilteredImageRecord], reviewed)
            write_json(self.settings.filter_manifest_path, filtered)
        else:
            filtered = filter_images(
                manifest,
            self.settings.raw_images_dir,
            self.settings.filtered_keep_dir,
            self.settings.filtered_discard_dir,
            self.settings.filter_manifest_path,
                self.settings,
            )
        outputs.extend(self.settings.raw_images_dir / item["filename"] for item in manifest)
        for item in filtered:
            if item["decision"] != "missing":
                folder = (self.settings.filtered_keep_dir if item["decision"] == "keep"
                          else self.settings.filtered_discard_dir)
                outputs.append(folder / item["filename"])
        self._stamp("images", inputs, outputs)
        return filtered

    def analyze_pdf(
        self, pdf_path: Path, *, resume: bool = False, force: bool = False
    ) -> PdfStructure:
        inputs = self._pdf_inputs(pdf_path, "structure")
        outputs = [self.settings.pdf_structure_path]
        if resume and not force and self._matches("structure", inputs, outputs):
            LOGGER.info("Resuming after PDF analysis")
            return cast(PdfStructure, read_json(self.settings.pdf_structure_path))
        structure = analyze_pdf(pdf_path, self.settings.pdf_structure_path)
        self._stamp("structure", inputs, outputs)
        return structure

    def extract_text(
        self, pdf_path: Path, *, resume: bool = False, force: bool = False
    ) -> list[CleanPage]:
        inputs = self._pdf_inputs(pdf_path, "text")
        outputs = [self.settings.raw_text_path, self.settings.clean_text_path]
        if resume and not force and self._matches("text", inputs, outputs):
            LOGGER.info("Resuming after text extraction/cleaning")
            return cast(list[CleanPage], read_json(self.settings.clean_text_path))

        raw_pages = extract_page_text(pdf_path, self.settings.raw_text_path)
        pages = clean_pages(
            raw_pages,
            self.settings.clean_text_path,
            header_footer_patterns=self.settings.header_footer_patterns,
            page_number_pattern=self.settings.page_number_pattern,
        )
        self._stamp("text", inputs, outputs)
        return pages

    def chunk(
        self,
        structure: PdfStructure | None = None,
        pages: list[CleanPage] | None = None,
        *,
        resume: bool = False,
        force: bool = False,
    ) -> list[TextChunk]:
        if structure is None:
            structure = cast(PdfStructure, read_json(self.settings.pdf_structure_path))
        if pages is None:
            pages = cast(list[CleanPage], read_json(self.settings.clean_text_path))
        inputs = self._chunk_inputs(structure, pages)
        outputs = [self.settings.text_chunks_path]
        if resume and not force and self._matches("chunks", inputs, outputs):
            return cast(list[TextChunk], read_json(self.settings.text_chunks_path))
        chunks = create_chunks(
            structure,
            pages,
            self.settings.text_chunks_path,
            target=self.settings.chunk_target_size,
            maximum=self.settings.chunk_max_size,
            overlap=self.settings.chunk_overlap,
            strategy=cast(Any, self.settings.chunking_strategy),
            skip_sections=self.settings.skip_sections,
        )
        self._stamp("chunks", inputs, outputs)
        return chunks

    def link_images(
        self,
        chunks: list[TextChunk] | None = None,
        images: list[FilteredImageRecord] | None = None,
        *,
        resume: bool = False,
        force: bool = False,
    ) -> list[ChunkImageLink]:
        if chunks is None:
            chunks = cast(list[TextChunk], read_json(self.settings.text_chunks_path))
        if images is None:
            if self.settings.filter_manifest_path.exists():
                images = cast(
                    list[FilteredImageRecord],
                    read_json(self.settings.filter_manifest_path),
                )
            else:
                images = []
        inputs = self._link_inputs(chunks, images)
        outputs = [self.settings.chunk_image_links_path]
        if resume and not force and self._matches("links", inputs, outputs):
            return cast(list[ChunkImageLink], read_json(self.settings.chunk_image_links_path))
        links = link_images_to_chunks(images, chunks, self.settings.chunk_image_links_path)
        self._stamp("links", inputs, outputs)
        return links

    def embed(
        self,
        chunks: list[TextChunk] | None = None,
        *,
        resume: bool = False,
        force: bool = False,
        show_progress: bool = True,
    ) -> None:
        outputs = [
            self.settings.embeddings_npy_path,
            self.settings.embeddings_meta_path,
            self.settings.embeddings_manifest_path,
        ]
        if chunks is None:
            chunks = cast(list[TextChunk], read_json(self.settings.text_chunks_path))
        if not chunks:
            raise ArtifactError("Cannot embed an empty chunk set")
        inputs = self._embedding_inputs(chunks)
        if resume and not force and self._matches("embeddings", inputs, outputs):
            LOGGER.info("Resuming after embedding generation")
            return
        service = EmbeddingService(
            self.settings.embedding_model_name,
            expected_dimension=self.settings.embedding_dimension,
            batch_size=self.settings.embedding_batch_size,
            hf_token=self.settings.hf_token,
            revision=self.settings.embedding_model_revision,
        )
        service.embed_chunks(
            chunks,
            self.settings.embeddings_npy_path,
            self.settings.embeddings_meta_path,
            self.settings.embeddings_manifest_path,
            show_progress=show_progress,
        )
        self._stamp("embeddings", inputs, outputs)

    def index(self, pdf_path: Path, *, replace: bool = True) -> dict[str, int]:
        structure = cast(PdfStructure, read_json(self.settings.pdf_structure_path))
        pages = cast(list[CleanPage], read_json(self.settings.clean_text_path))
        chunks = cast(list[TextChunk], read_json(self.settings.text_chunks_path))
        if not chunks:
            raise ArtifactError("Cannot index an empty chunk set")
        self._require("structure", self._pdf_inputs(pdf_path, "structure"),
                      [self.settings.pdf_structure_path])
        self._require("text", self._pdf_inputs(pdf_path, "text"),
                      [self.settings.raw_text_path, self.settings.clean_text_path])
        self._require("chunks", self._chunk_inputs(structure, pages),
                      [self.settings.text_chunks_path])
        images: list[FilteredImageRecord] = []
        if self.settings.filter_manifest_path.exists():
            images = cast(list[FilteredImageRecord], read_json(self.settings.filter_manifest_path))
            manifest = read_json(self._manifest("images"))
            enabled = manifest.get("inputs", {}).get("enabled")
            if not isinstance(enabled, bool) or (not enabled and images):
                raise ArtifactError("Invalid image stage provenance")
            self._require("images", self._pdf_inputs(pdf_path, "images", enabled=enabled),
                          [self.settings.image_manifest_path, self.settings.filter_manifest_path])
        links: list[ChunkImageLink] = []
        if self.settings.chunk_image_links_path.exists() or images:
            self._require("links", self._link_inputs(chunks, images),
                          [self.settings.chunk_image_links_path])
            links = cast(list[ChunkImageLink], read_json(self.settings.chunk_image_links_path))
        self._require("embeddings", self._embedding_inputs(chunks), [
            self.settings.embeddings_npy_path, self.settings.embeddings_meta_path,
            self.settings.embeddings_manifest_path,
        ])
        embeddings = load_embeddings(self.settings.embeddings_npy_path)
        metadata = read_json(self.settings.embeddings_meta_path)
        run = read_json(self.settings.embeddings_manifest_path)
        validate_embedding_alignment(
            chunks, embeddings, self.settings.embedding_dimension, metadata=metadata,
            manifest=run, expected_model=self.settings.embedding_model_name,
            expected_revision=self.settings.embedding_model_revision,
        )
        if (run.get("embeddings_sha256") != sha256_file(self.settings.embeddings_npy_path)
                or run.get("metadata_sha256") != sha256_file(self.settings.embeddings_meta_path)):
            raise ArtifactError("Embedding content hashes do not match the run manifest")
        repository = DatabaseRepository(self.settings.pg_conn_str)
        repository.apply_schema(self.settings.database_schema_path)
        return repository.ingest_document(
            document_key=self.settings.document_key,
            document_name=self.settings.document_name,
            source_filename=pdf_path.name,
            source_sha256=sha256_file(pdf_path),
            embedding_model=run["model_identity"],
            embedding_dimension=self.settings.embedding_dimension,
            chunks=chunks,
            embeddings=embeddings,
            images=images,
            links=links,
            image_dir=self.settings.filtered_keep_dir,
            replace=replace,
        )

    def ingest(
        self,
        pdf_path: Path,
        *,
        resume: bool = False,
        force: bool = False,
        include_images: bool = True,
        include_index: bool = True,
    ) -> dict[str, object]:
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF not found: {pdf_path}")

        self._report("starting", 0.01, "Preparing document ingestion")
        images: list[FilteredImageRecord] = []
        if include_images:
            self._report("images", 0.05, "Extracting and filtering images")
            images = self.extract_images(pdf_path, resume=resume, force=force)
        else:
            write_json(self.settings.image_manifest_path, [])
            write_json(self.settings.filter_manifest_path, [])
            self._stamp("images", self._pdf_inputs(pdf_path, "images", enabled=False),
                        [self.settings.image_manifest_path, self.settings.filter_manifest_path])

        self._report("structure", 0.20, "Analyzing PDF structure and table of contents")
        structure = self.analyze_pdf(pdf_path, resume=resume, force=force)
        self._report("text", 0.34, "Extracting and cleaning page text")
        pages = self.extract_text(pdf_path, resume=resume, force=force)
        self._report("chunking", 0.50, "Building TOC-aware semantic chunks")
        chunks = self.chunk(structure, pages, resume=resume, force=force)
        self._report("linking", 0.65, "Linking images to text chunks")
        links = self.link_images(chunks, images, resume=resume, force=force)
        self._report("embeddings", 0.72, "Generating semantic embeddings")
        self.embed(chunks, resume=resume, force=force)
        if include_index:
            self._report("indexing", 0.92, "Writing records to PostgreSQL and pgvector")
        database_counts = self.index(pdf_path) if include_index else None

        result: dict[str, object] = {
            "pdf": pdf_path.name,
            "pages": structure["total_pages"],
            "images": len(images),
            "chunks": len(chunks),
            "chunk_image_links": sum(link["image_count"] for link in links),
            "database": database_counts,
        }
        self._report("completed", 1.0, "Document ingestion completed")
        return result
