from __future__ import annotations

import os
import uuid
from pathlib import Path

import numpy as np
import pytest

from intelligent_scada.database.connection import transaction
from intelligent_scada.database.repository import DatabaseRepository
from intelligent_scada.retrieval.retriever import Retriever

pytestmark = pytest.mark.database


@pytest.fixture
def database(tmp_path):
    conn_str = os.getenv("TEST_PG_CONN_STR")
    if not conn_str:
        pytest.skip("TEST_PG_CONN_STR is not configured; use a dedicated test database")
    repository = DatabaseRepository(conn_str)
    repository.apply_schema(Path(__file__).resolve().parents[1] / 'database/schema.sql')
    keys = [f'test-{uuid.uuid4()}' for _ in range(2)]
    yield conn_str, repository, keys, tmp_path
    for key in keys:
        repository.delete_document(key)


def chunk(index, text):
    return {'chunk_id': f'chunk_{index:06d}', 'chunk_index': index, 'text': text,
            'char_count': len(text), 'word_count': len(text.split()), 'page_start': 1,
            'page_end': 1, 'source_pages': [1], 'toc_level': 1, 'section_title': 'Synthetic',
            'section_path': ['Synthetic'], 'section_start_page': 1, 'section_end_page': 1,
            'part_index': 1, 'part_count': 1}


def ingest(database, key, texts, **overrides):
    _, repository, _, image_dir = database
    options = dict(document_key=key, document_name='Synthetic Test', source_filename='fixture.pdf',
                   source_sha256='synthetic-source', embedding_model='synthetic@revision',
                   embedding_dimension=768, chunks=[chunk(i, text) for i, text in enumerate(texts)],
                   embeddings=np.eye(len(texts), 768, dtype=np.float32), images=[], links=[],
                   image_dir=image_dir)
    options.update(overrides)
    return repository.ingest_document(**options)


def stored_rows(database, key):
    with transaction(database[0]) as connection, connection.cursor() as cursor:
        cursor.execute('SELECT c.text FROM chunks c JOIN documents d ON d.id=c.document_id '
                       'WHERE d.document_key=%s ORDER BY c.chunk_index', (key,))
        return [row[0] for row in cursor.fetchall()]


def test_replacement_empty_guard_and_document_isolation(database):
    _, _, (a, b), _ = database
    ingest(database, a, ['old', 'old second'])
    ingest(database, b, ['independent'])
    assert ingest(database, a, ['replacement']) == {'chunks': 1, 'images': 0, 'chunk_images': 0}
    assert stored_rows(database, a) == ['replacement']
    assert stored_rows(database, b) == ['independent']
    with pytest.raises(ValueError, match='empty'):
        ingest(database, a, [])
    assert stored_rows(database, a) == ['replacement']


def test_replacement_rolls_back_on_invalid_link(database):
    from psycopg2.errors import ForeignKeyViolation
    key = database[2][0]
    ingest(database, key, ['original'])
    with pytest.raises(ForeignKeyViolation):
        ingest(database, key, ['replacement'], links=[{'chunk_id': 'chunk_000000',
            'images': [{'filename': 'missing.png'}]}])
    assert stored_rows(database, key) == ['original']


def test_real_cosine_order_scope_and_model_mismatch(database):
    conn_str, _, (a, b), _ = database
    vectors = np.eye(2, 768, dtype=np.float32)[::-1].copy()
    ingest(database, a, ['orthogonal', 'nearest'], embeddings=vectors)
    ingest(database, b, ['other document nearest'])
    class Encoder:
        model_identity = 'synthetic@revision'
        expected_dimension = 768
        def encode(self, *args, **kwargs):
            return np.eye(1, 768, dtype=np.float32)
    encoder = Encoder()
    results = Retriever(conn_str, encoder).retrieve('alarm', a)
    assert [r['text'] for r in results] == ['nearest', 'orthogonal']
    assert results[0]['score'] == pytest.approx(1)
    assert results[1]['score'] == pytest.approx(0)
    encoder.model_identity = 'other@revision'
    with pytest.raises(ValueError, match='re-ingest'):
        Retriever(conn_str, encoder).retrieve('alarm', a)


def test_document_deletion_cascades_transcripts(database):
    conn_str, repository, (key, _), _ = database
    ingest(database, key, ['fixture'])
    session_id = str(uuid.uuid4())
    with transaction(conn_str) as connection, connection.cursor() as cursor:
        cursor.execute('INSERT INTO chat_sessions(session_id,document_id) '
                       'SELECT %s,id FROM documents WHERE document_key=%s', (session_id, key))
        cursor.execute("INSERT INTO chat_messages(session_id,role,content) VALUES (%s,'user','fixture')",
                       (session_id,))
    repository.delete_document(key)
    with transaction(conn_str) as connection, connection.cursor() as cursor:
        cursor.execute('SELECT COUNT(*) FROM chat_messages WHERE session_id=%s', (session_id,))
        assert cursor.fetchone()[0] == 0
        cursor.execute('SELECT COUNT(*) FROM chat_sessions WHERE session_id=%s', (session_id,))
        assert cursor.fetchone()[0] == 0
