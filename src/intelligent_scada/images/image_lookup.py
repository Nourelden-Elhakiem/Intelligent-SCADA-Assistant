"""Look up optional visual references for retrieved chunks."""

from __future__ import annotations

from pathlib import Path

from intelligent_scada.contracts import LinkedImage
from intelligent_scada.database.connection import transaction


class ImageLookup:
    def __init__(self, conn_str: str | None, *, data_root: Path) -> None:
        self.conn_str = conn_str
        self.data_root = data_root.resolve()

    def for_chunks(
        self, document_key: str, chunk_ids: list[str], *, limit: int = 12
    ) -> list[LinkedImage]:
        if not chunk_ids:
            return []
        with transaction(self.conn_str) as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                    SELECT DISTINCT
                        i.filename, i.page, i.width, i.height, i.file_size_bytes
                    FROM chunk_images ci
                    JOIN documents d ON d.id = ci.document_id
                    JOIN images i
                      ON i.document_id = ci.document_id
                     AND i.filename = ci.image_filename
                    WHERE d.document_key = %s AND ci.chunk_id = ANY(%s)
                    ORDER BY i.page, i.filename
                    LIMIT %s
                    """,
                (document_key, chunk_ids, limit),
            )
            rows = cursor.fetchall()
        return [
            {
                "filename": row[0],
                "page": int(row[1]),
                "width": int(row[2]),
                "height": int(row[3]),
                "file_size_bytes": int(row[4]),
            }
            for row in rows
        ]

    def resolve_path(self, document_key: str, filename: str) -> Path | None:
        """Resolve a DB-owned image path within the configured data directory."""
        with transaction(self.conn_str) as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                    SELECT i.image_path
                    FROM images i
                    JOIN documents d ON d.id = i.document_id
                    WHERE d.document_key = %s AND i.filename = %s
                """,
                (document_key, filename),
            )
            row = cursor.fetchone()

        if not row or not row[0]:
            return None

        stored_path = str(row[0]).strip()
        data_root = self.data_root

        # 1. Prefer the stored path when it is already valid in the current environment.
        direct_path = Path(stored_path)
        if direct_path.is_file():
            resolved = direct_path.resolve()
            try:
                resolved.relative_to(data_root)
            except ValueError:
                return None
            return resolved

        # 2. Normalize Windows paths and remap the project's `data/` subtree
        #    onto the current runtime's SCADA_DATA_DIR.
        normalized = stored_path.replace("\\", "/")
        marker = "/data/"

        marker_index = normalized.lower().rfind(marker)
        if marker_index == -1:
            return None

        relative_path = normalized[marker_index + len(marker) :].lstrip("/")
        if not relative_path:
            return None

        candidate = (data_root / relative_path).resolve()

        try:
            candidate.relative_to(data_root)
        except ValueError:
            return None

        return candidate if candidate.is_file() else None
