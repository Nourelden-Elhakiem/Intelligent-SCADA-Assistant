from pathlib import Path

import numpy as np
import pytest

from intelligent_scada.artifacts import (
    ArtifactError,
    load_embeddings,
    read_json,
    save_embeddings,
    stage_matches,
    write_json,
    write_stage_manifest,
)


def test_atomic_json_failure_keeps_previous_file(tmp_path, monkeypatch):
    target = tmp_path / 'value.json'
    write_json(target, {'value': 'original'})
    original_replace = Path.replace

    def fail_replace(self, other):
        if other == target:
            raise OSError('simulated replacement failure')
        return original_replace(self, other)

    monkeypatch.setattr(Path, 'replace', fail_replace)
    with pytest.raises(OSError):
        write_json(target, {'value': 'changed'})
    assert read_json(target) == {'value': 'original'}
    assert list(tmp_path.iterdir()) == [target]


def test_stage_requires_complete_matching_inputs_and_outputs(tmp_path):
    output = tmp_path / 'text.json'
    extra = tmp_path / 'raw.json'
    manifest = tmp_path / 'stage.json'
    write_json(output, ['hello'])
    write_json(extra, ['raw'])
    inputs = {'source': 'abc', 'settings': {'limit': 2}}
    assert not stage_matches(manifest, inputs, [output], root=tmp_path)
    write_stage_manifest(manifest, inputs, [output, extra], root=tmp_path)
    assert stage_matches(manifest, inputs, [output], root=tmp_path)
    assert not stage_matches(manifest, {'source': 'def'}, [output], root=tmp_path)
    extra.unlink()
    assert not stage_matches(manifest, inputs, [output], root=tmp_path)
    write_json(extra, ['raw'])
    write_json(output, ['modified'])
    assert not stage_matches(manifest, inputs, [output], root=tmp_path)


def test_corrupt_and_pickle_artifacts_fail_safely(tmp_path):
    path = tmp_path / 'vectors.npy'
    path.write_bytes(b'not an array')
    with pytest.raises(ArtifactError):
        load_embeddings(path)
    np.save(path, np.array([{'unsafe': True}], dtype=object))
    with pytest.raises(ArtifactError):
        load_embeddings(path)
    vectors = np.eye(2, dtype=np.float32)
    save_embeddings(path, vectors)
    np.testing.assert_array_equal(load_embeddings(path), vectors)
    json_path = tmp_path / 'bad.json'
    json_path.write_text('{')
    with pytest.raises(ArtifactError):
        read_json(json_path)
