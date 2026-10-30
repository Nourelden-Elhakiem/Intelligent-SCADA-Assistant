from dataclasses import replace

import numpy as np
import pytest
from test_pdf_ingestion import make_pdf

from intelligent_scada.artifacts import ArtifactError, read_json, write_json
from intelligent_scada.embeddings.embedding_service import EmbeddingService
from intelligent_scada.pipeline import Pipeline


@pytest.fixture
def encoder(monkeypatch):
    class Model:
        calls = 0

        def encode(self, texts, **kwargs):
            self.calls += 1
            result = np.zeros((len(texts), 768), dtype=np.float32)
            result[:, 0] = 1
            return result

    model = Model()
    monkeypatch.setattr(EmbeddingService, '_load_model', lambda self: model)
    return model


def test_resume_reuses_only_verified_artifacts(settings, tmp_path, encoder):
    pdf = make_pdf(tmp_path / 'source.pdf', text='First source alarm text.')
    pipeline = Pipeline(settings)
    pipeline.ingest(pdf, include_images=False, include_index=False)
    assert encoder.calls == 1
    pipeline.ingest(pdf, resume=True, include_images=False, include_index=False)
    assert encoder.calls == 1
    pdf.unlink()
    make_pdf(pdf, text='Second source voltage text.')
    pipeline.ingest(pdf, resume=True, include_images=False, include_index=False)
    assert encoder.calls == 2
    assert 'Second source' in read_json(settings.text_chunks_path)[0]['text']
    assert 'First source' not in read_json(settings.text_chunks_path)[0]['text']
    settings.raw_text_path.unlink()
    pipeline.extract_text(pdf, resume=True)
    assert settings.raw_text_path.exists()
    changed = Pipeline(replace(settings, header_footer_patterns=('Second source voltage text.',)))
    changed.extract_text(pdf, resume=True)
    assert not read_json(settings.clean_text_path)[0]['clean_text']


def test_index_rejects_mutated_artifacts_before_database(settings, tmp_path, encoder, monkeypatch):
    pdf = make_pdf(tmp_path / 'source.pdf')
    pipeline = Pipeline(settings)
    pipeline.ingest(pdf, include_images=False, include_index=False)
    touched = []
    monkeypatch.setattr('intelligent_scada.pipeline.DatabaseRepository',
                        lambda *args: touched.append(True))
    chunks = read_json(settings.text_chunks_path)
    chunks[0]['text'] = 'Changed content with identical identifier'
    write_json(settings.text_chunks_path, chunks)
    with pytest.raises(ArtifactError, match='chunks'):
        pipeline.index(pdf)
    assert touched == []


def test_index_checks_embedding_metadata_even_with_fresh_stage_hash(settings, tmp_path, encoder):
    pdf = make_pdf(tmp_path / 'source.pdf')
    pipeline = Pipeline(settings)
    pipeline.ingest(pdf, include_images=False, include_index=False)
    metadata = read_json(settings.embeddings_meta_path)
    metadata[0]['source_pages'] = [99]
    write_json(settings.embeddings_meta_path, metadata)
    pipeline._stamp('embeddings', pipeline._embedding_inputs(read_json(settings.text_chunks_path)), [
        settings.embeddings_npy_path, settings.embeddings_meta_path,
        settings.embeddings_manifest_path,
    ])
    with pytest.raises(ValueError, match='metadata'):
        pipeline.index(pdf)


def test_empty_or_unversioned_artifacts_cannot_replace_index(settings, tmp_path, encoder):
    pdf = make_pdf(tmp_path / 'source.pdf')
    pipeline = Pipeline(settings)
    pipeline.ingest(pdf, include_images=False, include_index=False)
    pipeline._manifest('text').unlink()
    with pytest.raises(ArtifactError, match='unverified'):
        pipeline.index(pdf)
    with pytest.raises(ArtifactError, match='empty'):
        pipeline.embed([])
    write_json(settings.text_chunks_path, [])
    with pytest.raises(ArtifactError, match='empty'):
        pipeline.index(pdf)


def test_valid_index_carries_verified_model_identity(settings, tmp_path, encoder, monkeypatch):
    pdf = make_pdf(tmp_path / 'source.pdf')
    pipeline = Pipeline(settings)
    pipeline.ingest(pdf, include_images=False, include_index=False)
    calls = []

    class Repository:
        def __init__(self, *_):
            pass

        def apply_schema(self, *_):
            calls.append('schema')

        def ingest_document(self, **kwargs):
            calls.append(kwargs)
            return {'chunks': len(kwargs['chunks'])}

    monkeypatch.setattr('intelligent_scada.pipeline.DatabaseRepository', Repository)
    assert pipeline.index(pdf) == {'chunks': 1}
    assert calls[1]['embedding_model'] == settings.embedding_model_name
    assert calls[1]['source_sha256']
