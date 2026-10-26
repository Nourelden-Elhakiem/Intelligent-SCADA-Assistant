from pathlib import Path

import numpy as np

from intelligent_scada.database.models import (
    serialize_chunk_row,
    serialize_image_row,
    validate_embedding_alignment,
)


def test_database_serialization_preserves_json_and_vector_fields() -> None:
    chunk = {
        "chunk_id": "chunk_000000",
        "chunk_index": 0,
        "text": "text",
        "char_count": 4,
        "word_count": 1,
        "page_start": 2,
        "page_end": 3,
        "source_pages": [2, 3],
        "toc_level": 2,
        "section_title": "Ports",
        "section_path": ["Configure", "Ports"],
        "section_start_page": 2,
        "section_end_page": 3,
        "part_index": 1,
        "part_count": 1,
    }
    embedding = np.zeros(768, dtype=np.float32)
    row = serialize_chunk_row(chunk, embedding)

    assert row[0] == "chunk_000000"
    assert row[5] == "[2, 3]"
    assert "Configure" in row[8]
    assert row[-1].startswith("[0.0")
    validate_embedding_alignment([chunk], embedding.reshape(1, -1), 768)


def test_image_path_is_serialized_portably() -> None:
    image = {
        "filename": "diagram.png",
        "page": 2,
        "img_index": 1,
        "xref": 1,
        "width": 300,
        "height": 200,
        "source_ext": "png",
        "file_size_bytes": 100,
        "md5": "abc",
        "decision": "keep",
    }
    row = serialize_image_row(image, Path("data/filtered/keep/diagram.png"))
    assert row[5] == "data/filtered/keep/diagram.png"


def test_embedding_provenance_rejects_content_order_model_and_nonfinite():
    import copy

    import pytest
    from test_embeddings import _chunk

    from intelligent_scada.embeddings.embedding_service import (
        build_embedding_metadata,
        chunk_content_digest,
    )
    chunks = [_chunk('first'), _chunk('second')]
    chunks[1].update(chunk_id='chunk_000001', chunk_index=1)
    vectors = np.eye(2, 768, dtype=np.float32)
    metadata = build_embedding_metadata(chunks)
    manifest = {'artifact_version': 2, 'chunk_content_sha256': chunk_content_digest(chunks),
                'chunk_count': 2, 'embedding_dimension': 768, 'normalized': True,
                'dtype': 'float32', 'model_name': 'synthetic', 'model_revision': 'revision',
                'model_identity': 'synthetic@revision'}
    validate_embedding_alignment(chunks, vectors, 768, metadata=metadata,
                                 manifest=manifest, expected_model='synthetic')
    changed = copy.deepcopy(chunks)
    changed[0]['text'] = 'other'
    for invalid_chunks, invalid_metadata, invalid_manifest, model in [
        (changed, metadata, manifest, 'synthetic'),
        (chunks, list(reversed(metadata)), manifest, 'synthetic'),
        (chunks, metadata, {**manifest, 'artifact_version': 1}, 'synthetic'),
        (chunks, metadata, manifest, 'different'),
    ]:
        with pytest.raises(ValueError):
            validate_embedding_alignment(invalid_chunks, vectors, 768,
                metadata=invalid_metadata, manifest=invalid_manifest, expected_model=model)
    vectors[0, 0] = np.nan
    with pytest.raises(ValueError, match='nonfinite'):
        validate_embedding_alignment(chunks, vectors, 768)
