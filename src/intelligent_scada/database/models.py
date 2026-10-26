"""Serialization from artifact records to database row values."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any, cast

import numpy as np
import numpy.typing as npt

from intelligent_scada.artifacts import json_digest
from intelligent_scada.contracts import (
    ChunkImageLink,
    EmbeddingMetadata,
    FilteredImageRecord,
    TextChunk,
)


def serialize_chunk_row(
    chunk: TextChunk, embedding: npt.NDArray[np.float32]
) -> tuple[object, ...]:
    return (
        chunk["chunk_id"],
        chunk["chunk_index"],
        chunk["text"],
        chunk["page_start"],
        chunk["page_end"],
        json.dumps(chunk["source_pages"]),
        chunk["toc_level"],
        chunk["section_title"],
        json.dumps(chunk["section_path"], ensure_ascii=False),
        chunk["section_start_page"],
        chunk["section_end_page"],
        chunk["part_index"],
        chunk["part_count"],
        chunk["char_count"],
        chunk["word_count"],
        str(embedding.tolist()),
    )


def serialize_image_row(image: FilteredImageRecord, image_path: Path) -> tuple[object, ...]:
    return (
        image["filename"],
        image["page"],
        image["width"],
        image["height"],
        image["file_size_bytes"],
        image_path.as_posix(),
        image.get("md5", ""),
        image["decision"],
    )


def serialize_link_rows(
    links: Iterable[ChunkImageLink],
) -> list[tuple[str, str, str]]:
    return [
        (record["chunk_id"], image["filename"], "page_overlap")
        for record in links
        for image in record["images"]
    ]


def validate_embedding_alignment(
    chunks: Sequence[TextChunk],
    embeddings: npt.NDArray[np.float32],
    expected_dimension: int,
    *,
    metadata: Sequence[EmbeddingMetadata] | None = None,
    manifest: Mapping[str, Any] | None = None,
    expected_model: str | None = None,
    expected_revision: str | None = None,
) -> None:
    if embeddings.shape != (len(chunks), expected_dimension):
        raise ValueError(
            f"Embedding/chunk mismatch: embeddings={embeddings.shape}, "
            f"chunks={len(chunks)}, expected_dimension={expected_dimension}"
        )
    if not np.isfinite(embeddings).all():
        raise ValueError("Embeddings contain nonfinite values")
    if len({chunk["chunk_id"] for chunk in chunks}) != len(chunks):
        raise ValueError("Chunk identifiers must be unique")
    for index, chunk in enumerate(chunks):
        if chunk["chunk_index"] != index:
            raise ValueError(
                f"Chunk order mismatch at row {index}: chunk_index={chunk['chunk_index']}"
            )
    if metadata is None and manifest is None:
        return
    if metadata is None or manifest is None or len(metadata) != len(chunks):
        raise ValueError("Embedding metadata and manifest must align with all chunks")
    for chunk, record in zip(chunks, metadata, strict=True):
        expected = {key: cast(Mapping[str, Any], chunk)[key] for key in EmbeddingMetadata.__annotations__}
        if record != expected:
            raise ValueError("Embedding metadata does not match the ordered chunks")
    digest = json_digest([[chunk["chunk_id"], chunk["text"]] for chunk in chunks])
    if manifest.get("artifact_version") != 2 or manifest.get("chunk_content_sha256") != digest:
        raise ValueError("Embedding content provenance is missing or stale; rebuild artifacts")
    if manifest.get("chunk_count") != len(chunks) or manifest.get("embedding_dimension") != expected_dimension:
        raise ValueError("Embedding manifest shape does not match the data")
    if manifest.get("normalized") is not True or manifest.get("dtype") != "float32":
        raise ValueError("Embedding manifest must describe normalized float32 vectors")
    if not np.allclose(np.linalg.norm(embeddings, axis=1), 1.0, atol=1e-4):
        raise ValueError("Embedding vectors are not normalized")
    if expected_model is not None and manifest.get("model_name") != expected_model:
        raise ValueError("Embedding model changed; rebuild artifacts")
    if expected_revision is not None and manifest.get("requested_revision") != expected_revision:
        raise ValueError("Embedding revision changed; rebuild artifacts")
    name = manifest.get("model_name")
    revision = manifest.get("model_revision")
    identity = f"{name}@{revision}" if revision else name
    if not isinstance(name, str) or not name or manifest.get("model_identity") != identity:
        raise ValueError("Invalid embedding model identity")
