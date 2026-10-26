"""Idempotent, document-scoped PostgreSQL ingestion."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt

from intelligent_scada.config import DEFAULT_EMBEDDING_DIMENSION, validate_document_key
from intelligent_scada.contracts import (
    ChunkImageLink,
    FilteredImageRecord,
    TextChunk,
)
from intelligent_scada.database.connection import transaction
from intelligent_scada.database.models import (
    serialize_chunk_row,
    serialize_image_row,
    serialize_link_rows,
    validate_embedding_alignment,
)

LOGGER = logging.getLogger(__name__)


class DatabaseRepository:
    def __init__(self, conn_str: str | None) -> None:
        self.conn_str = conn_str

    def apply_schema(self, schema_path: Path) -> None:
        sql = schema_path.read_text(encoding="utf-8")
        with transaction(self.conn_str) as connection, connection.cursor() as cursor:
            cursor.execute(sql)
        LOGGER.info("Database schema applied from %s", schema_path)

    def ping(self) -> bool:
        with transaction(self.conn_str) as connection, connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            row = cursor.fetchone()
        return bool(row and row[0] == 1)

    @staticmethod
    def _upsert_document(
        cursor: Any,
        *,
        document_key: str,
        document_name: str,
        source_filename: str,
        source_sha256: str | None,
        embedding_model: str,
        embedding_dimension: int,
    ) -> int:
        cursor.execute(
            """
            INSERT INTO documents (
                document_key, document_name, source_filename, source_sha256,
                embedding_model, embedding_dimension
            ) VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (document_key) DO UPDATE SET
                document_name = EXCLUDED.document_name,
                source_filename = EXCLUDED.source_filename,
                source_sha256 = EXCLUDED.source_sha256,
                embedding_model = EXCLUDED.embedding_model,
                embedding_dimension = EXCLUDED.embedding_dimension,
                updated_at = NOW()
            RETURNING id;
            """,
            (
                document_key,
                document_name,
                source_filename,
                source_sha256,
                embedding_model,
                embedding_dimension,
            ),
        )
        return int(cursor.fetchone()[0])

    def ingest_document(
        self,
        *,
        document_key: str,
        document_name: str,
        source_filename: str,
        source_sha256: str | None,
        embedding_model: str,
        embedding_dimension: int,
        chunks: Sequence[TextChunk],
        embeddings: npt.NDArray[np.float32],
        images: Sequence[FilteredImageRecord],
        links: Sequence[ChunkImageLink],
        image_dir: Path,
        replace: bool = True,
    ) -> dict[str, int]:
        from psycopg2.extras import execute_values

        validate_document_key(document_key)
        if not chunks:
            raise ValueError("Refusing to replace a document with an empty chunk set")
        if embedding_dimension != DEFAULT_EMBEDDING_DIMENSION:
            raise ValueError("The database requires 768-dimensional embeddings")
        if not embedding_model.strip():
            raise ValueError("Embedding model identity is required")
        validate_embedding_alignment(chunks, embeddings, embedding_dimension)
        kept_images = [image for image in images if image["decision"] == "keep"]

        with transaction(self.conn_str) as connection, connection.cursor() as cursor:
            # Also protect command-line writers, which do not use the API job registry.
            cursor.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (document_key,))
            if not replace:
                cursor.execute(
                    "SELECT source_sha256, embedding_model, embedding_dimension "
                    "FROM documents WHERE document_key = %s FOR UPDATE", (document_key,),
                )
                existing = cursor.fetchone()
                if existing and tuple(existing) != (source_sha256, embedding_model, embedding_dimension):
                    raise ValueError("Appending requires the same PDF and embedding model; replace instead")
            document_id = self._upsert_document(
                cursor,
                document_key=document_key,
                document_name=document_name,
                source_filename=source_filename,
                source_sha256=source_sha256,
                embedding_model=embedding_model,
                embedding_dimension=embedding_dimension,
            )
            if replace:
                cursor.execute("DELETE FROM chunks WHERE document_id = %s", (document_id,))
                cursor.execute("DELETE FROM images WHERE document_id = %s", (document_id,))

            chunk_rows = [
                (document_id, *serialize_chunk_row(chunk, embeddings[index]))
                for index, chunk in enumerate(chunks)
            ]
            execute_values(
                cursor,
                """
                    INSERT INTO chunks (
                        document_id, chunk_id, chunk_index, text,
                        page_start, page_end, source_pages,
                        toc_level, section_title, section_path,
                        section_start_page, section_end_page, part_index, part_count,
                        char_count, word_count, embedding
                    ) VALUES %s
                    ON CONFLICT (document_id, chunk_id) DO UPDATE SET
                        chunk_index = EXCLUDED.chunk_index,
                        text = EXCLUDED.text,
                        page_start = EXCLUDED.page_start,
                        page_end = EXCLUDED.page_end,
                        source_pages = EXCLUDED.source_pages,
                        toc_level = EXCLUDED.toc_level,
                        section_title = EXCLUDED.section_title,
                        section_path = EXCLUDED.section_path,
                        section_start_page = EXCLUDED.section_start_page,
                        section_end_page = EXCLUDED.section_end_page,
                        part_index = EXCLUDED.part_index,
                        part_count = EXCLUDED.part_count,
                        char_count = EXCLUDED.char_count,
                        word_count = EXCLUDED.word_count,
                        embedding = EXCLUDED.embedding,
                        updated_at = NOW()
                    """,
                chunk_rows,
                template=(
                    "(%s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, "
                    "%s::jsonb, %s, %s, %s, %s, %s, %s, %s::vector)"
                ),
                page_size=200,
            )

            image_rows = [
                (document_id, *serialize_image_row(image, image_dir / image["filename"]))
                for image in kept_images
            ]
            if image_rows:
                execute_values(
                    cursor,
                    """
                        INSERT INTO images (
                            document_id, filename, page, width, height,
                            file_size_bytes, image_path, md5, decision
                        ) VALUES %s
                        ON CONFLICT (document_id, filename) DO UPDATE SET
                            page = EXCLUDED.page,
                            width = EXCLUDED.width,
                            height = EXCLUDED.height,
                            file_size_bytes = EXCLUDED.file_size_bytes,
                            image_path = EXCLUDED.image_path,
                            md5 = EXCLUDED.md5,
                            decision = EXCLUDED.decision,
                            updated_at = NOW()
                        """,
                    image_rows,
                    page_size=500,
                )

            link_rows = [
                (document_id, chunk_id, filename, reason)
                for chunk_id, filename, reason in serialize_link_rows(links)
            ]
            if link_rows:
                execute_values(
                    cursor,
                    """
                        INSERT INTO chunk_images (
                            document_id, chunk_id, image_filename, link_reason
                        ) VALUES %s
                        ON CONFLICT (document_id, chunk_id, image_filename)
                        DO UPDATE SET link_reason = EXCLUDED.link_reason
                        """,
                    link_rows,
                    page_size=500,
                )

        counts = {
            "chunks": len(chunks),
            "images": len(kept_images),
            "chunk_images": len(serialize_link_rows(links)),
        }
        LOGGER.info("Indexed %s: %s", document_key, counts)
        return counts

    def delete_document(self, document_key: str) -> bool:
        with transaction(self.conn_str) as connection, connection.cursor() as cursor:
            cursor.execute("DELETE FROM documents WHERE document_key = %s", (document_key,))
            return bool(cursor.rowcount > 0)

    def list_documents(self) -> list[dict[str, Any]]:
        """Return indexed manuals with aggregate counts for the application UI."""
        with transaction(self.conn_str) as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                    SELECT
                        d.document_key, d.document_name, d.source_filename,
                        d.embedding_model, d.embedding_dimension,
                        (SELECT COUNT(*) FROM chunks c WHERE c.document_id = d.id)
                            AS chunk_count,
                        (SELECT COUNT(*) FROM images i WHERE i.document_id = d.id)
                            AS image_count,
                        d.created_at, d.updated_at
                    FROM documents d
                    ORDER BY d.updated_at DESC, d.document_name
                """
            )
            rows = cursor.fetchall()
        return [
            {
                "document_key": row[0],
                "document_name": row[1],
                "source_filename": row[2],
                "embedding_model": row[3],
                "embedding_dimension": int(row[4]),
                "chunk_count": int(row[5]),
                "image_count": int(row[6]),
                "created_at": row[7],
                "updated_at": row[8],
            }
            for row in rows
        ]

    def get_document(self, document_key: str) -> dict[str, Any] | None:
        with transaction(self.conn_str) as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                    SELECT
                        d.document_key, d.document_name, d.source_filename,
                        d.embedding_model, d.embedding_dimension,
                        (SELECT COUNT(*) FROM chunks c WHERE c.document_id = d.id)
                            AS chunk_count,
                        (SELECT COUNT(*) FROM images i WHERE i.document_id = d.id)
                            AS image_count,
                        d.created_at, d.updated_at
                    FROM documents d
                    WHERE d.document_key = %s
                """,
                (document_key,),
            )
            row = cursor.fetchone()
        if row is None:
            return None
        return {
            "document_key": row[0],
            "document_name": row[1],
            "source_filename": row[2],
            "embedding_model": row[3],
            "embedding_dimension": int(row[4]),
            "chunk_count": int(row[5]),
            "image_count": int(row[6]),
            "created_at": row[7],
            "updated_at": row[8],
        }
