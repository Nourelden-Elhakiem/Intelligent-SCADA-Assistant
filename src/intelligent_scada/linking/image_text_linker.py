"""Link filtered images to chunks using one-based page overlap."""

from __future__ import annotations

import logging
from collections import defaultdict
from pathlib import Path

from intelligent_scada.artifacts import write_json
from intelligent_scada.contracts import (
    ChunkImageLink,
    FilteredImageRecord,
    LinkedImage,
    TextChunk,
)

LOGGER = logging.getLogger(__name__)


def link_images_to_chunks(
    filter_manifest: list[FilteredImageRecord],
    chunks: list[TextChunk],
    output_path: Path | None = None,
) -> list[ChunkImageLink]:
    page_to_images: dict[int, list[LinkedImage]] = defaultdict(list)
    for image in filter_manifest:
        if image.get("decision") != "keep":
            continue
        page_to_images[image["page"]].append(
            {
                "filename": image["filename"],
                "page": image["page"],
                "width": image["width"],
                "height": image["height"],
                "file_size_bytes": image["file_size_bytes"],
            }
        )

    links: list[ChunkImageLink] = []
    for chunk in chunks:
        matched_images = [
            image for page in chunk["source_pages"] for image in page_to_images.get(page, [])
        ]
        links.append(
            {
                "chunk_id": chunk["chunk_id"],
                "section_title": chunk["section_title"],
                "section_path": chunk["section_path"],
                "page_start": chunk["page_start"],
                "page_end": chunk["page_end"],
                "source_pages": chunk["source_pages"],
                "image_count": len(matched_images),
                "images": matched_images,
            }
        )

    if output_path is not None:
        write_json(output_path, links)
    LOGGER.info(
        "Linked images to %s of %s chunks",
        sum(record["image_count"] > 0 for record in links),
        len(links),
    )
    return links
