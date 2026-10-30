"""Semantic embedding generation."""

from intelligent_scada.embeddings.embedding_service import (
    EmbeddingService,
    build_embedding_metadata,
    prepare_embedding_inputs,
)

__all__ = ["EmbeddingService", "build_embedding_metadata", "prepare_embedding_inputs"]
