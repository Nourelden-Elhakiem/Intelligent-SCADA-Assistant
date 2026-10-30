"""Automatic image filtering and manual-review manifest reconciliation."""

from __future__ import annotations

import logging
import shutil
from collections import Counter
from pathlib import Path
from typing import Literal

import numpy as np
from PIL import Image

from intelligent_scada.artifacts import write_json
from intelligent_scada.config import Settings
from intelligent_scada.contracts import FilteredImageRecord, ImageRecord

LOGGER = logging.getLogger(__name__)


def is_too_small(width: int, height: int, settings: Settings) -> bool:
    if width < settings.min_width or height < settings.min_height:
        return True
    return width < settings.min_combined_width and height < settings.min_combined_height


def blank_or_solid_reason(image_path: Path, settings: Settings) -> str | None:
    with Image.open(image_path) as image:
        pixels = np.asarray(image.convert("L"), dtype=np.float32)
    mean_value = float(pixels.mean())
    standard_deviation = float(pixels.std())

    if standard_deviation >= settings.blank_std_threshold:
        return None
    if mean_value > settings.blank_brightness_high:
        return "blank_white"
    if mean_value < settings.blank_brightness_low:
        return "blank_black"
    return "solid_color"


def filter_images(
    manifest: list[ImageRecord],
    raw_images_dir: Path,
    keep_dir: Path,
    discard_dir: Path,
    output_manifest_path: Path,
    settings: Settings,
) -> list[FilteredImageRecord]:
    """Classify images using the original size, duplicate, and blank checks."""
    keep_dir.mkdir(parents=True, exist_ok=True)
    discard_dir.mkdir(parents=True, exist_ok=True)
    seen_md5: dict[str, str] = {}
    filtered: list[FilteredImageRecord] = []
    reasons_counter: Counter[str] = Counter()

    for entry in manifest:
        image_path = raw_images_dir / entry["filename"]
        if not image_path.exists():
            LOGGER.warning("Image listed in manifest is missing: %s", image_path)
            continue

        reasons: list[str] = []
        if is_too_small(entry["width"], entry["height"], settings):
            reasons.append("too_small")

        md5 = entry["md5"]
        if md5 in seen_md5:
            reasons.append("duplicate")
        else:
            seen_md5[md5] = entry["filename"]

        # Preserve notebook behavior: blank analysis only runs if no earlier reason exists.
        if not reasons:
            blank_reason = blank_or_solid_reason(image_path, settings)
            if blank_reason:
                reasons.append(blank_reason)

        decision: Literal["keep", "discard", "missing"] = "discard" if reasons else "keep"
        destination = discard_dir if decision == "discard" else keep_dir
        counterpart = keep_dir if decision == "discard" else discard_dir
        shutil.copy2(image_path, destination / entry["filename"])
        # Prevent stale copies from making manual review ambiguous.
        (counterpart / entry["filename"]).unlink(missing_ok=True)

        reasons_counter.update(reasons)
        filtered.append({**entry, "decision": decision, "reasons": reasons})

    write_json(output_manifest_path, filtered)
    LOGGER.info(
        "Filtered %s images: %s kept, %s discarded (%s)",
        len(filtered),
        sum(item["decision"] == "keep" for item in filtered),
        sum(item["decision"] == "discard" for item in filtered),
        dict(reasons_counter),
    )
    return filtered


def rebuild_manual_review_manifest(
    original_manifest: list[ImageRecord],
    keep_dir: Path,
    discard_dir: Path,
    output_manifest_path: Path,
) -> list[FilteredImageRecord]:
    """Rebuild decisions from manually reviewed folders.

    This preserves the original manual-review schema. A conflict is reported and
    resolved as keep, matching the notebook's historical behavior.
    """
    keep_files = {path.name for path in keep_dir.iterdir() if path.is_file()}
    discard_files = {path.name for path in discard_dir.iterdir() if path.is_file()}
    conflicts = keep_files & discard_files
    if conflicts:
        LOGGER.warning(
            "%s files exist in both review folders; treating them as keep",
            len(conflicts),
        )

    reviewed: list[FilteredImageRecord] = []
    for entry in original_manifest:
        filename = entry["filename"]
        decision: Literal["keep", "discard", "missing"]
        if filename in keep_files:
            decision = "keep"
        elif filename in discard_files:
            decision = "discard"
        else:
            decision = "missing"
        reviewed.append({**entry, "decision": decision, "source": "manual_review"})

    write_json(output_manifest_path, reviewed)
    return reviewed
