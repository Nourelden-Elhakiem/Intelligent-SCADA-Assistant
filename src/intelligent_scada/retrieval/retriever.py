"""Semantic retrieval using the ingestion embedding model and pgvector cosine distance."""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

import numpy as np
import numpy.typing as npt

from intelligent_scada.config import validate_document_key
from intelligent_scada.contracts import RetrievalResult
from intelligent_scada.database.connection import transaction
from intelligent_scada.embeddings.embedding_service import EmbeddingService


def rank_embeddings(
    query_embedding: npt.NDArray[np.float32],
    candidate_embeddings: npt.NDArray[np.float32],
    *,
    top_k: int,
) -> list[tuple[int, float]]:
    """Return candidate indices ranked by cosine similarity."""
    if query_embedding.ndim != 1 or candidate_embeddings.ndim != 2:
        raise ValueError("Expected a 1D query and a 2D candidate matrix")
    if candidate_embeddings.shape[1] != query_embedding.shape[0]:
        raise ValueError("Query and candidate embedding dimensions do not match")
    if top_k <= 0:
        raise ValueError("top_k must be positive")

    query_norm = np.linalg.norm(query_embedding)
    candidate_norms = np.linalg.norm(candidate_embeddings, axis=1)
    denominator = candidate_norms * query_norm
    scores = np.divide(
        candidate_embeddings @ query_embedding,
        denominator,
        out=np.full(candidate_embeddings.shape[0], -1.0, dtype=np.float32),
        where=denominator != 0,
    )
    ranked = np.argsort(-scores, kind="stable")[:top_k]
    return [(int(index), float(scores[index])) for index in ranked]


def _json_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        parsed = json.loads(value)
        return parsed if isinstance(parsed, list) else []
    return []


class Retriever:
    def __init__(
        self,
        conn_str: str | None,
        embedding_service: EmbeddingService,
        *,
        max_top_k: int = 12,
    ) -> None:
        self.conn_str = conn_str
        self.embedding_service = embedding_service
        self.max_top_k = max_top_k

    def retrieve(
        self, query: str, document_key: str, *, top_k: int = 6
    ) -> list[RetrievalResult]:
        if not query.strip():
            raise ValueError("Retrieval query cannot be empty")
        validate_document_key(document_key)
        top_k = max(1, min(top_k, self.max_top_k))
        model_identity = self.embedding_service.model_identity

        with transaction(self.conn_str) as connection, connection.cursor() as cursor:
            # Hold document metadata stable until the cosine query completes.
            cursor.execute(
                "SELECT embedding_model, embedding_dimension FROM documents "
                "WHERE document_key = %s FOR SHARE", (document_key,),
            )
            document = cursor.fetchone()
            if document is None:
                raise LookupError("Document is not indexed")
            if (document[0] != model_identity
                    or document[1] != self.embedding_service.expected_dimension):
                raise ValueError("Embedding model or dimension differs from the index; re-ingest the document")
            query_vector = self.embedding_service.encode([query], show_progress=False)[0]
            vector_value = str(query_vector.tolist())
            cursor.execute(
                """
                    SELECT
                        c.chunk_id, c.text, c.page_start, c.page_end,
                        c.source_pages, c.section_title, c.section_path,
                        1 - (c.embedding <=> %s::vector) AS score
                    FROM chunks c
                    JOIN documents d ON d.id = c.document_id
                    WHERE d.document_key = %s AND c.embedding IS NOT NULL
                    ORDER BY c.embedding <=> %s::vector, c.chunk_index
                    LIMIT %s
                    """,
                (vector_value, document_key, vector_value, top_k),
            )
            rows: Sequence[tuple[Any, ...]] = cursor.fetchall()

        return [
            {
                "chunk_id": row[0],
                "text": row[1],
                "page_start": row[2],
                "page_end": row[3],
                "source_pages": [int(page) for page in _json_list(row[4])],
                "section_title": row[5] or "",
                "section_path": [str(item) for item in _json_list(row[6])],
                "score": float(row[7]),
            }
            for row in rows
        ]
