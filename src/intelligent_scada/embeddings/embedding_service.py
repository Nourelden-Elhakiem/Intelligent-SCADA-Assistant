"""Sentence-transformer embedding generation and artifact validation."""

from __future__ import annotations

import hashlib
import logging
import re
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TypeAlias, cast

import numpy as np
import numpy.typing as npt

from intelligent_scada.artifacts import json_digest, save_embeddings, sha256_file, write_json
from intelligent_scada.contracts import EmbeddingMetadata, TextChunk

LOGGER = logging.getLogger(__name__)
FloatArray: TypeAlias = npt.NDArray[np.float32]


def prepare_embedding_inputs(chunks: Sequence[TextChunk]) -> list[str]:
    if not chunks:
        raise ValueError("Cannot embed an empty chunk set")
    texts = [chunk["text"] for chunk in chunks]
    empty = [index for index, text in enumerate(texts) if not text.strip()]
    if empty:
        raise ValueError(f"Chunks contain empty text at indices: {empty[:10]}")
    return texts


def build_embedding_metadata(chunks: Sequence[TextChunk]) -> list[EmbeddingMetadata]:
    return [
        {
            "chunk_id": chunk["chunk_id"],
            "chunk_index": chunk["chunk_index"],
            "char_count": chunk["char_count"],
            "word_count": chunk["word_count"],
            "page_start": chunk["page_start"],
            "page_end": chunk["page_end"],
            "source_pages": chunk["source_pages"],
            "toc_level": chunk["toc_level"],
            "section_title": chunk["section_title"],
            "section_path": chunk["section_path"],
            "part_index": chunk["part_index"],
            "part_count": chunk["part_count"],
        }
        for chunk in chunks
    ]


def chunk_id_digest(chunks: Sequence[TextChunk]) -> str:
    payload = "\n".join(chunk["chunk_id"] for chunk in chunks).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def chunk_content_digest(chunks: Sequence[TextChunk]) -> str:
    return json_digest([[chunk["chunk_id"], chunk["text"]] for chunk in chunks])


class EmbeddingService:
    """Lazy wrapper around SentenceTransformer using centrally supplied settings."""

    def __init__(
        self,
        model_name: str,
        *,
        expected_dimension: int,
        batch_size: int,
        hf_token: str | None = None,
        device: str | None = None,
        revision: str | None = None,
    ) -> None:
        self.model_name = model_name
        self.expected_dimension = expected_dimension
        self.batch_size = batch_size
        self.hf_token = hf_token
        self.device = device
        self.revision = revision
        self._resolved_revision = revision
        self._model: Any = None

    def _load_model(self) -> Any:
        if self._model is not None:
            return self._model
        import torch
        from huggingface_hub import hf_hub_download
        from sentence_transformers import SentenceTransformer

        if not Path(self.model_name).is_dir():
            # Pin every model file to one immutable Hub snapshot. Do not resolve
            # the cache symlink: its parent identifies the downloaded revision.
            config_path = Path(hf_hub_download(
                self.model_name, "config.json", revision=self.revision, token=self.hf_token,
            ))
            commit = config_path.parent.name
            if not re.fullmatch(r"[0-9a-f]{40}", commit):
                raise ValueError("Could not resolve the embedding model to an immutable Hub revision")
            self._resolved_revision = commit
        selected_device = self.device or ("cuda" if torch.cuda.is_available() else "cpu")
        self._model = SentenceTransformer(
            self.model_name,
            device=selected_device,
            token=self.hf_token,
            revision=self._resolved_revision,
        )
        dimension = int(self._model.get_sentence_embedding_dimension())
        if dimension != self.expected_dimension:
            raise ValueError(
                f"Embedding dimension mismatch: model={dimension}, "
                f"configured={self.expected_dimension}"
            )
        LOGGER.info("Loaded %s on %s", self.model_name, selected_device)
        return self._model

    @property
    def model_revision(self) -> str | None:
        """Record the resolved Hub commit when available, or the requested revision."""
        model = self._load_model()
        if self._resolved_revision:
            return self._resolved_revision
        first_module = getattr(model, "_first_module", None)
        transformer = first_module() if callable(first_module) else model
        config = getattr(getattr(transformer, "auto_model", None), "config", None)
        commit = getattr(config, "_commit_hash", None)
        return commit if isinstance(commit, str) and commit else self.revision

    @property
    def model_identity(self) -> str:
        revision = self.model_revision
        return f"{self.model_name}@{revision}" if revision else self.model_name

    def encode(self, texts: Sequence[str], *, show_progress: bool = True) -> FloatArray:
        if not texts:
            return cast(
                FloatArray,
                np.empty((0, self.expected_dimension), dtype=np.float32),
            )
        model = self._load_model()
        embeddings = model.encode(
            list(texts),
            show_progress_bar=show_progress,
            batch_size=self.batch_size,
            normalize_embeddings=True,
        )
        array = cast(FloatArray, np.asarray(embeddings, dtype=np.float32))
        expected_shape = (len(texts), self.expected_dimension)
        if array.shape != expected_shape:
            raise ValueError(
                f"Unexpected embedding shape: {array.shape}; expected {expected_shape}"
            )
        if not np.isfinite(array).all():
            raise ValueError("Embeddings must contain only finite values")
        if not np.allclose(np.linalg.norm(array, axis=1), 1.0, atol=1e-4):
            raise ValueError("The embedding model must return nonzero normalized vectors")
        return array

    def embed_chunks(
        self,
        chunks: Sequence[TextChunk],
        embeddings_path: Path,
        metadata_path: Path,
        run_manifest_path: Path,
        *,
        show_progress: bool = True,
    ) -> FloatArray:
        texts = prepare_embedding_inputs(chunks)
        embeddings = self.encode(texts, show_progress=show_progress)
        metadata = build_embedding_metadata(chunks)
        save_embeddings(embeddings_path, embeddings)
        write_json(metadata_path, metadata)
        write_json(
            run_manifest_path,
            {
                "artifact_version": 2,
                "model_name": self.model_name,
                "requested_revision": self.revision,
                "model_revision": self.model_revision,
                "model_identity": self.model_identity,
                "embedding_dimension": self.expected_dimension,
                "normalized": True,
                "dtype": str(embeddings.dtype),
                "chunk_count": len(chunks),
                "chunk_id_sha256": chunk_id_digest(chunks),
                "chunk_content_sha256": chunk_content_digest(chunks),
                "embeddings_sha256": sha256_file(embeddings_path),
                "metadata_sha256": sha256_file(metadata_path),
                "created_at": datetime.now(UTC).isoformat(),
            },
        )
        return embeddings
