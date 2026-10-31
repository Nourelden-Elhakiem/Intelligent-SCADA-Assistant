import numpy as np

from intelligent_scada.chunking.toc_chunker import create_chunks
from intelligent_scada.database.models import serialize_chunk_row
from intelligent_scada.embeddings.embedding_service import (
    build_embedding_metadata,
    prepare_embedding_inputs,
)
from intelligent_scada.ingestion.text_cleaner import clean_pages


def test_clean_pages_to_retrieval_ready_records(tmp_path) -> None:
    raw_pages = [
        {
            "page": 1,
            "raw_text": "Configure\nSystem Guide\nPage 1 of 1\nSet port 443.",
            "raw_char_count": 54,
            "raw_word_count": 10,
        }
    ]
    clean = clean_pages(raw_pages, tmp_path / "clean.json")
    structure = {
        "total_pages": 1,
        "toc_entries": 1,
        "toc": [{"level": 1, "title": "Configure", "page": 1}],
        "empty_pages": [],
        "page_stats": [],
        "heading_candidates_count": 0,
    }

    chunks = create_chunks(structure, clean, tmp_path / "chunks.json")
    texts = prepare_embedding_inputs(chunks)
    metadata = build_embedding_metadata(chunks)
    row = serialize_chunk_row(chunks[0], np.zeros(768, dtype=np.float32))

    assert texts == ["Section: Configure\n\nConfigure\nSet port 443."]
    assert metadata[0]["source_pages"] == [1]
    assert row[0] == metadata[0]["chunk_id"]
