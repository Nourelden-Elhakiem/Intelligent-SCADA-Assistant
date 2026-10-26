"""Backward-compatible constants for the original notebooks.

New code should import :class:`intelligent_scada.config.Settings` directly.
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from intelligent_scada.config import Settings  # noqa: E402

_settings = Settings.from_env(project_root=PROJECT_ROOT)

DATA_DIR = _settings.data_dir
PDF_DIR = _settings.pdf_dir
RAW_IMAGES_DIR = _settings.raw_images_dir
MANIFESTS_DIR = _settings.manifests_dir
FILTERED_DIR = _settings.data_dir / "filtered"
FILTERED_KEEP_DIR = _settings.filtered_keep_dir
FILTERED_DISCARD_DIR = _settings.filtered_discard_dir
TEXT_DIR = _settings.text_dir
LINKED_DIR = _settings.linked_dir
EMBEDDINGS_DIR = _settings.embeddings_dir
PDF_FILENAME = _settings.pdf_filename
PDF_PATH = _settings.pdf_path
DOCUMENT_NAME = _settings.document_name
OUTPUT_IMAGE_FORMAT = _settings.output_image_format
IMAGE_FILENAME_TEMPLATE = _settings.image_filename_template
IMAGE_MANIFEST_PATH = _settings.image_manifest_path
FILTER_MANIFEST_PATH = _settings.filter_manifest_path
PDF_STRUCTURE_PATH = _settings.pdf_structure_path
RAW_TEXT_PATH = _settings.raw_text_path
CLEAN_TEXT_PATH = _settings.clean_text_path
TEXT_CHUNKS_PATH = _settings.text_chunks_path
CHUNK_IMAGE_LINKS_PATH = _settings.chunk_image_links_path
EMBEDDINGS_NPY_PATH = _settings.embeddings_npy_path
EMBEDDINGS_META_PATH = _settings.embeddings_meta_path
EMBEDDING_MODEL_NAME = _settings.embedding_model_name
EMBEDDING_DIMENSION = _settings.embedding_dimension
ENV_PATH = PROJECT_ROOT / ".env"
HEADER_FOOTER_PATTERNS = list(_settings.header_footer_patterns)
PAGE_NUMBER_PATTERN = _settings.page_number_pattern
CHUNK_TARGET_SIZE = _settings.chunk_target_size
CHUNK_MAX_SIZE = _settings.chunk_max_size
CHUNK_OVERLAP = _settings.chunk_overlap
SKIP_SECTIONS = list(_settings.skip_sections)
MIN_WIDTH = _settings.min_width
MIN_HEIGHT = _settings.min_height
MIN_COMBINED_WIDTH = _settings.min_combined_width
MIN_COMBINED_HEIGHT = _settings.min_combined_height
BLANK_STD_THRESHOLD = _settings.blank_std_threshold
BLANK_BRIGHTNESS_LOW = _settings.blank_brightness_low
BLANK_BRIGHTNESS_HIGH = _settings.blank_brightness_high
OUTPUT_DIRS = list(_settings.output_dirs)
