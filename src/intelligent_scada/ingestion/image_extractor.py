"""Extract embedded PDF images while preserving the notebook manifest schema."""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path

import fitz

from intelligent_scada.artifacts import write_json
from intelligent_scada.contracts import ImageRecord

LOGGER = logging.getLogger(__name__)


def extract_images(
    pdf_path: Path,
    raw_images_dir: Path,
    manifest_path: Path,
    *,
    output_format: str = "png",
    filename_template: str = ("page{page:04d}_img{index:03d}_w{width:04d}_h{height:04d}.{ext}"),
) -> list[ImageRecord]:
    """Extract images in deterministic page/image order and save the manifest."""
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    raw_images_dir.mkdir(parents=True, exist_ok=True)
    manifest: list[ImageRecord] = []
    skipped = 0

    with fitz.open(pdf_path) as document:
        total_pages = document.page_count
        for page_index in range(total_pages):
            page = document[page_index]
            for image_index, image_info in enumerate(page.get_images(full=True)):
                xref = image_info[0]
                try:
                    base = document.extract_image(xref)
                    image_bytes = base["image"]
                    width = int(base["width"])
                    height = int(base["height"])
                    source_ext = str(base.get("ext", output_format))

                    filename = filename_template.format(
                        page=page_index + 1,
                        index=image_index + 1,
                        width=width,
                        height=height,
                        ext=output_format,
                    )
                    output_path = raw_images_dir / filename

                    pixmap = fitz.Pixmap(document, xref)
                    if pixmap.colorspace and pixmap.colorspace.n > 3:
                        pixmap = fitz.Pixmap(fitz.csRGB, pixmap)
                    if pixmap.alpha:
                        pixmap = fitz.Pixmap(pixmap, 0)
                    pixmap.save(str(output_path))

                    manifest.append(
                        {
                            "filename": filename,
                            "page": page_index + 1,
                            "img_index": image_index + 1,
                            "xref": xref,
                            "width": width,
                            "height": height,
                            "source_ext": source_ext,
                            "file_size_bytes": output_path.stat().st_size,
                            "md5": hashlib.md5(image_bytes).hexdigest(),
                        }
                    )
                except Exception as exc:
                    skipped += 1
                    LOGGER.warning(
                        "Skipped image on page %s at index %s: %s",
                        page_index + 1,
                        image_index + 1,
                        exc,
                    )

    write_json(manifest_path, manifest)
    LOGGER.info(
        "Extracted %s images from %s pages; skipped %s",
        len(manifest),
        total_pages,
        skipped,
    )
    return manifest
