import numpy as np

from intelligent_scada.retrieval.retriever import rank_embeddings


def test_cosine_ranking_is_descending_and_stable() -> None:
    query = np.array([1.0, 0.0], dtype=np.float32)
    candidates = np.array([[0.0, 1.0], [1.0, 0.0], [0.5, 0.5]], dtype=np.float32)

    ranked = rank_embeddings(query, candidates, top_k=3)

    assert [index for index, _ in ranked] == [1, 2, 0]
    assert ranked[0][1] == 1.0


def test_retriever_rejects_model_mismatch_before_cosine_query(monkeypatch):
    from contextlib import contextmanager

    import pytest

    from intelligent_scada.retrieval.retriever import Retriever

    statements = []

    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def execute(self, sql, params):
            statements.append(sql)

        def fetchone(self):
            return ('old-model@revision', 768)

    class Connection:
        def cursor(self):
            return Cursor()

    @contextmanager
    def transaction(_):
        yield Connection()

    class Encoder:
        model_identity = 'new-model@revision'
        expected_dimension = 768

        def encode(self, texts, **kwargs):
            return np.eye(1, 768, dtype=np.float32)

    monkeypatch.setattr('intelligent_scada.retrieval.retriever.transaction', transaction)
    with pytest.raises(ValueError, match='re-ingest'):
        Retriever(None, Encoder()).retrieve('alarm', 'manual')
    assert len(statements) == 1
    assert '<=>' not in statements[0]
