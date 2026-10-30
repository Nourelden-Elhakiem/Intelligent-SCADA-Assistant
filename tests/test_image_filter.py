from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
from PIL import Image

from intelligent_scada.config import Settings
from intelligent_scada.ingestion.image_filter import filter_images


def _record(path: Path, page: int, md5: str) -> dict[str, object]:
    with Image.open(path) as image:
        width, height = image.size
    return {
        "filename": path.name,
        "page": page,
        "img_index": 1,
        "xref": page,
        "width": width,
        "height": height,
        "source_ext": "png",
        "file_size_bytes": path.stat().st_size,
        "md5": md5,
    }


def test_image_filtering_rules_and_output_manifest(tmp_path: Path) -> None:
    raw = tmp_path / "raw"
    raw.mkdir()
    keep = tmp_path / "keep"
    discard = tmp_path / "discard"

    white = raw / "white.png"
    small = raw / "small.png"
    useful = raw / "useful.png"
    Image.new("RGB", (300, 200), "white").save(white)
    Image.new("RGB", (40, 40), "blue").save(small)
    pixels = np.indices((200, 300)).sum(axis=0) % 2 * 255
    Image.fromarray(pixels.astype(np.uint8), mode="L").save(useful)

    manifest = [
        _record(white, 1, hashlib.md5(b"white").hexdigest()),
        _record(small, 2, hashlib.md5(b"small").hexdigest()),
        _record(useful, 3, hashlib.md5(b"useful").hexdigest()),
    ]
    settings = Settings(project_root=tmp_path, data_dir=tmp_path / "data")

    filtered = filter_images(manifest, raw, keep, discard, tmp_path / "filter.json", settings)

    assert [item["decision"] for item in filtered] == ["discard", "discard", "keep"]
    assert filtered[0]["reasons"] == ["blank_white"]
    assert filtered[1]["reasons"] == ["too_small"]
    assert (keep / "useful.png").exists()
