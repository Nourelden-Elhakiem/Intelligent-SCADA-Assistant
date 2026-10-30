import pytest

from intelligent_scada.embeddings.embedding_service import (
    build_embedding_metadata,
    prepare_embedding_inputs,
)


def _chunk(text: str = "Section: Configure\n\nUseful text") -> dict[str, object]:
    return {
        "chunk_id": "chunk_000000",
        "chunk_index": 0,
        "text": text,
        "char_count": len(text),
        "word_count": len(text.split()),
        "page_start": 1,
        "page_end": 1,
        "source_pages": [1],
        "toc_level": 1,
        "section_title": "Configure",
        "section_path": ["Configure"],
        "section_start_page": 1,
        "section_end_page": 1,
        "part_index": 1,
        "part_count": 1,
    }


def test_embedding_inputs_preserve_section_prefix_and_metadata() -> None:
    chunk = _chunk()
    assert prepare_embedding_inputs([chunk]) == [chunk["text"]]
    metadata = build_embedding_metadata([chunk])
    assert metadata[0]["chunk_id"] == "chunk_000000"
    assert "text" not in metadata[0]


def test_empty_embedding_input_is_rejected() -> None:
    with pytest.raises(ValueError, match="empty text"):
        prepare_embedding_inputs([_chunk(" ")])


def test_embedding_content_digest_changes_with_text():
    from intelligent_scada.embeddings.embedding_service import chunk_content_digest
    assert chunk_content_digest([_chunk('first')]) != chunk_content_digest([_chunk('second')])


@pytest.mark.parametrize('invalid', ['shape', 'nan', 'zero'])
def test_encoder_rejects_invalid_vectors(invalid, monkeypatch):
    import numpy as np

    from intelligent_scada.embeddings.embedding_service import EmbeddingService

    vector = np.zeros((1, 768), dtype=np.float32)
    if invalid == 'shape':
        vector = vector[:, :10]
    elif invalid == 'nan':
        vector[0, 0] = np.nan

    class Model:
        def encode(self, *args, **kwargs):
            return vector

    service = EmbeddingService('test', expected_dimension=768, batch_size=1)
    monkeypatch.setattr(service, '_load_model', lambda: Model())
    with pytest.raises(ValueError):
        service.encode(['text'])
